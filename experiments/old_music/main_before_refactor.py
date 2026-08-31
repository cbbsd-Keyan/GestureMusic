import pygame.midi
import socket
import time
import msvcrt
from collections import deque

# =========================
# UDP
# =========================

UDP_PORT = 4210

sock = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM
)

sock.bind(
    ("0.0.0.0", UDP_PORT)
)

# 非阻塞读取
sock.setblocking(False)

# =========================
# MIDI
# =========================

pygame.midi.init()
player = pygame.midi.Output(1)

CHORD_CHANNEL = 0
BASS_CHANNEL = 1
MELODY_CHANNEL = 2
DRUM_CHANNEL = 9

player.set_instrument(0, CHORD_CHANNEL)
player.set_instrument(32, BASS_CHANNEL)
player.set_instrument(0, MELODY_CHANNEL)

# =========================
# 音乐数据
# =========================

chords = [
    [60, 64, 67],  # C
    [57, 60, 64],  # Am
    [53, 57, 60],  # F
    [55, 59, 62],  # G
]

chord_names = ["C", "Am", "F", "G"]

bass_notes = [
    36,  # C2
    33,  # A1
    29,  # F1
    31,  # G1
]

melody_notes = [
    [60, 64, 67],  # C
    [57, 60, 64],  # Am
    [53, 57, 60],  # F
    [55, 59, 62],  # G
]

drum_pattern = [
    36,  # kick
    42,  # hihat
    38,  # snare
    42,  # hihat
]

# =========================
# 当前状态
# =========================

beat = 0

roll = 0.0
height = 1       # 0 LOW / 1 MID / 2 HIGH

current_chord = None
current_bass = None
last_melody = None

# =========================
# Tempo
# =========================

last_beat_time = None

# 保存最近4次有效拍间隔
beat_intervals = deque(maxlen=4)

bpm = None

MIN_BPM = 60
MAX_BPM = 180

MIN_INTERVAL = 60.0 / MAX_BPM
MAX_INTERVAL = 60.0 / MIN_BPM


# =========================
# roll → 旋律档位
# =========================

def roll_to_height(value):
    if value < -15:
        return 0
    elif value > 15:
        return 2
    else:
        return 1

def update_tempo():
    global last_beat_time
    global bpm

    now = time.perf_counter()

    # 第一拍只能记录时间
    if last_beat_time is None:
        last_beat_time = now
        return

    interval = now - last_beat_time
    last_beat_time = now

    # 停得太久，认为重新开始
    if interval > 1.5:
        beat_intervals.clear()
        bpm = None
        return

    # 明显异常的间隔不参与计算
    if interval < MIN_INTERVAL or interval > MAX_INTERVAL:
        return

    beat_intervals.append(interval)

    # 至少有两个间隔以后再显示
    if len(beat_intervals) >= 2:
        avg_interval = sum(beat_intervals) / len(beat_intervals)
        bpm = 60.0 / avg_interval

# =========================
# 真正播放“一拍”
# =========================

def play_beat():

    global beat
    global current_chord
    global current_bass
    global last_melody

    chord_index = (beat // 4) % 4
    beat_in_bar = beat % 4

    # ---------- 换和弦 ----------

    if beat_in_bar == 0:

        if current_chord is not None:
            for note in current_chord:
                player.note_off(
                    note,
                    65,
                    CHORD_CHANNEL
                )

        if current_bass is not None:
            player.note_off(
                current_bass,
                80,
                BASS_CHANNEL
            )

        current_chord = chords[chord_index]
        current_bass = bass_notes[chord_index]

        for note in current_chord:
            player.note_on(
                note,
                60,
                CHORD_CHANNEL
            )

        player.note_on(
            current_bass,
            75,
            BASS_CHANNEL
        )

    # ---------- 鼓 ----------

    drum_note = drum_pattern[beat_in_bar]

    player.note_on(
        drum_note,
        105,
        DRUM_CHANNEL
    )

    player.note_off(
        drum_note,
        105,
        DRUM_CHANNEL
    )

    # ---------- 旋律 ----------

    if last_melody is not None:
        player.note_off(
            last_melody,
            90,
            MELODY_CHANNEL
        )

    melody_note = melody_notes[chord_index][height]

    # 右倾 HIGH 再高一个八度
    if height == 2:
        melody_note += 12

    player.note_on(
        melody_note,
        90,
        MELODY_CHANNEL
    )

    last_melody = melody_note

    bpm_text = "---" if bpm is None else f"{bpm:5.1f}"

    print(
        f"BEAT {beat + 1:2d} | "
        f"BPM {bpm_text} | "
        f"Chord {chord_names[chord_index]:2s} | "
        f"Roll {roll:6.1f}° | "
        f"{['LOW', 'MID', 'HIGH'][height]:4s} | "
        f"Melody {melody_note}"
    )

    beat += 1


# =========================
# 主程序
# =========================

print("===== Gesture Music V4 =====")
print()
print("真实下挥 -> 下一拍")
print("左倾     -> 低旋律")
print("水平     -> 中旋律")
print("右倾     -> 高旋律")
print("Q        -> 退出")
print()


try:

    while True:

        # Q 仍然留作退出
        if msvcrt.kbhit():
            key = msvcrt.getwch()

            if key.lower() == "q":
                break

        try:

            data, address = sock.recvfrom(1024)

            line = (
                data.decode(errors="ignore")
                .strip()
            )

        except BlockingIOError:

            time.sleep(0.001)

            continue

        if not line:
            continue

        # =========================
        # 姿态
        # =========================

        if line.startswith("TILT,"):

            try:
                _, value = line.split(",")

                roll = float(value)

                new_height = roll_to_height(roll)

                if new_height != height:

                    height = new_height

                    print(
                        f"Roll {roll:6.1f}° -> "
                        f"{['LOW', 'MID', 'HIGH'][height]}"
                    )

            except ValueError:
                pass

        # =========================
        # 下挥
        # =========================

        elif line == "BEAT":
            update_tempo()
            play_beat()


finally:

    if current_chord:
        for note in current_chord:
            player.note_off(
                note,
                65,
                CHORD_CHANNEL
            )

    if current_bass:
        player.note_off(
            current_bass,
            80,
            BASS_CHANNEL
        )

    if last_melody:
        player.note_off(
            last_melody,
            90,
            MELODY_CHANNEL
        )

    sock.close()
    player.close()
    pygame.midi.quit()

    print("\n程序结束")