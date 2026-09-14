"""MIDI-track conductor session: transport and four stem layers."""
from dataclasses import dataclass
from pathlib import Path
import ctypes
from ctypes import wintypes
import time

from audio.wand_control import WandControl
from input.udp_reader import UDPReader


TRACK_GROUPS = {
    0: 'guitar', 1: 'keyboard', 2: 'bass', 3: 'keyboard',
    4: 'drums', 5: 'drums', 6: 'drums', 7: 'drums', 8: 'drums', 9: 'drums',
}
GROUP_CHANNELS = {
    'keyboard': (2, 6), 'bass': (4,), 'guitar': (0,), 'drums': (9,),
}


class _WindowsMidiOutput:
    """Windows winmm MIDI output, used when pygame is not installed."""
    MIDI_MAPPER = 0xFFFFFFFF

    def __init__(self, device=None):
        self.winmm = ctypes.WinDLL('winmm', use_last_error=True)
        self.winmm.midiOutOpen.argtypes = (
            ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
            ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD,
        )
        self.winmm.midiOutOpen.restype = wintypes.UINT
        self.winmm.midiOutShortMsg.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        self.winmm.midiOutShortMsg.restype = wintypes.UINT
        self.winmm.midiOutReset.argtypes = (wintypes.HANDLE,)
        self.winmm.midiOutReset.restype = wintypes.UINT
        self.winmm.midiOutClose.argtypes = (wintypes.HANDLE,)
        self.winmm.midiOutClose.restype = wintypes.UINT
        self.handle = wintypes.HANDLE()
        device_id = self.MIDI_MAPPER if device is None else device
        result = self.winmm.midiOutOpen(ctypes.byref(self.handle), device_id, 0, 0, 0)
        if result:
            raise OSError(f'Windows MIDI 输出设备无法打开（错误码 {result}）')

    def write_short(self, status, data1=0, data2=0):
        message = (int(status) & 0xFF) | ((int(data1) & 0x7F) << 8) | ((int(data2) & 0x7F) << 16)
        result = self.winmm.midiOutShortMsg(self.handle, message)
        if result:
            raise OSError(f'Windows MIDI 消息发送失败（错误码 {result}）')

    def set_instrument(self, program, channel):
        self.write_short(0xC0 | channel, program, 0)

    def note_on(self, note, velocity, channel):
        self.write_short(0x90 | channel, note, velocity)

    def note_off(self, note, velocity, channel):
        self.write_short(0x80 | channel, note, velocity)

    def close(self):
        if self.handle:
            self.winmm.midiOutReset(self.handle)
            self.winmm.midiOutClose(self.handle)
            self.handle = wintypes.HANDLE()


@dataclass(frozen=True)
class StemEvent:
    time_s: float
    kind: str
    channel: int
    data1: int
    data2: int
    group: str


def _vlq(data, index):
    value = 0
    while True:
        if index >= len(data):
            raise ValueError('MIDI 可变长度字段不完整')
        byte = data[index]
        index += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, index


def read_stem_events(path):
    """Read the source MIDI's original tracks without re-composing anything."""
    data = Path(path).read_bytes()
    if data[:4] != b'MThd' or len(data) < 14:
        raise ValueError('不是标准 MIDI 文件')
    header_size = int.from_bytes(data[4:8], 'big')
    track_count = int.from_bytes(data[10:12], 'big')
    ticks_per_beat = int.from_bytes(data[12:14], 'big')
    if header_size < 6 or not ticks_per_beat or ticks_per_beat & 0x8000:
        raise ValueError('不支持的 MIDI 时间基')

    cursor = 8 + header_size
    raw = []
    for track_index in range(track_count):
        if data[cursor:cursor + 4] != b'MTrk':
            raise ValueError(f'第 {track_index + 1} 条轨道损坏')
        end = cursor + 8 + int.from_bytes(data[cursor + 4:cursor + 8], 'big')
        index = cursor + 8
        tick = 0
        running_status = None
        while index < end:
            delta, index = _vlq(data, index)
            tick += delta
            first = data[index]
            if first & 0x80:
                status = first
                index += 1
                if status < 0xF0:
                    running_status = status
            else:
                if running_status is None:
                    raise ValueError('MIDI 运行状态无前导状态字节')
                status = running_status
            if status == 0xFF:
                meta_type = data[index]
                index += 1
                length, index = _vlq(data, index)
                payload = data[index:index + length]
                index += length
                if meta_type == 0x51 and len(payload) == 3:
                    raw.append((tick, 0, 'tempo', 0, int.from_bytes(payload, 'big'), 0, None))
            elif status in (0xF0, 0xF7):
                length, index = _vlq(data, index)
                index += length
            else:
                message_type = status >> 4
                channel = status & 0x0F
                width = 1 if message_type in (0xC, 0xD) else 2
                values = data[index:index + width]
                index += width
                group = TRACK_GROUPS.get(track_index)
                if message_type == 0xC:
                    raw.append((tick, 1, 'program', channel, values[0], 0, group))
                elif message_type == 0x8:
                    raw.append((tick, 1, 'note_off', channel, values[0], values[1], group))
                elif message_type == 0x9:
                    kind = 'note_off' if values[1] == 0 else 'note_on'
                    raw.append((tick, 1, kind, channel, values[0], values[1], group))
        cursor = end

    raw.sort(key=lambda item: (item[0], item[1]))
    elapsed = 0.
    current_tick = 0
    tempo_us = 500000
    events = []
    for tick, _, kind, channel, data1, data2, group in raw:
        elapsed += (tick - current_tick) * tempo_us / ticks_per_beat / 1_000_000
        current_tick = tick
        if kind == 'tempo':
            tempo_us = data1
        elif group is not None:
            events.append(StemEvent(elapsed, kind, channel, data1, data2, group))
    return events


def _fade(energy, start, end):
    return max(0., min(1., (energy - start) / (end - start)))


def layer_levels(energy, playing):
    """A calm keyboard base grows to the complete rock arrangement."""
    if not playing:
        return {group: 0 for group in GROUP_CHANNELS}
    return {
        'keyboard': round(127 * (.28 + .72 * energy)),
        'bass': round(127 * _fade(energy, .12, .42)),
        'guitar': round(127 * _fade(energy, .34, .64)),
        'drums': round(127 * _fade(energy, .56, .86)),
    }


class StemConductorSession:
    """Same lifecycle as ConductorSession, backed by the source MIDI tracks."""
    def __init__(self, midi_path, device=1, midi_module=None, reader_factory=UDPReader,
                 wand_factory=WandControl, event_loader=read_stem_events):
        self.midi_path = Path(midi_path)
        self.device = device
        self.midi_module = midi_module
        self.reader_factory = reader_factory
        self.wand_factory = wand_factory
        self.event_loader = event_loader
        self.events = []
        self.output = None
        self.reader = None
        self.wand = None
        self.event_index = 0
        self.song_time = 0.
        self.last_tick = None
        self.was_playing = False
        self.manual_paused = False
        self.levels = {group: 0 for group in GROUP_CHANNELS}

    def start(self):
        if self.output is not None:
            raise RuntimeError('分轨指挥已启动')
        if not self.midi_path.exists():
            raise FileNotFoundError(f'卡农 MIDI 文件不存在：{self.midi_path}')
        self.events = self.event_loader(self.midi_path)
        if not self.events:
            raise ValueError('MIDI 中没有可播放的分轨音符')
        try:
            if self.midi_module is None:
                try:
                    import pygame.midi
                    self.midi_module = pygame.midi
                except ImportError:
                    # The Windows MIDI mapper is available without Python packages.
                    self.output = _WindowsMidiOutput()
            if self.output is None:
                self.midi_module.init()
                self.output = self.midi_module.Output(self.device)
            self.reader = self.reader_factory(port=4210)
            self.wand = self.wand_factory()
            self.last_tick = time.monotonic()
        except Exception:
            self.close()
            raise

    def _all_notes_off(self):
        if self.output is not None:
            for channel in range(16):
                self.output.write_short(0xB0 | channel, 123, 0)

    def _set_levels(self, levels):
        for group, channels in GROUP_CHANNELS.items():
            for channel in channels:
                self.output.write_short(0xB0 | channel, 7, levels[group])
        self.levels = levels

    def update(self, now=None):
        if self.output is None:
            return None
        now = time.monotonic() if now is None else now
        delta = max(0., now - self.last_tick)
        self.last_tick = now
        self.wand.poll(self.reader, now)
        playing = not self.manual_paused and not self.wand.paused
        was_playing = self.was_playing
        if playing:
            self.song_time += delta
        elif was_playing:
            self._all_notes_off()
        self.was_playing = playing
        energy = max(0., min(1., (self.wand.rms - .5) / 4.))
        self._set_levels(layer_levels(energy, playing))
        while playing and self.event_index < len(self.events):
            event = self.events[self.event_index]
            if event.time_s > self.song_time:
                break
            if event.kind == 'program':
                self.output.set_instrument(event.data1, event.channel)
            elif event.kind == 'note_on':
                self.output.note_on(event.data1, event.data2, event.channel)
            else:
                self.output.note_off(event.data1, event.data2, event.channel)
            self.event_index += 1
        if self.event_index >= len(self.events):
            return 'conductor_finished'
        if playing:
            return 'wand_started' if not was_playing else None
        return 'wand_paused' if was_playing else None

    def pause(self):
        self.manual_paused = True
        self.was_playing = False
        self._all_notes_off()

    def resume(self):
        self.manual_paused = False
        self.was_playing = False

    def snapshot(self):
        return {
            'energy': self.wand.rms if self.wand else 0.,
            'position': self.song_time, 'layers': self.levels,
        }

    def close(self):
        self._all_notes_off()
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        if self.output is not None:
            self.output.close()
            self.output = None
        if self.midi_module is not None:
            self.midi_module.quit()
