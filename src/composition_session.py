"""Menu-controlled recording, rule composition and MIDI preview sessions."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import sys
import threading
import time

BASE = Path(__file__).resolve().parent
for directory in (BASE / 'features', BASE / 'music', BASE / 'input'):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from input.recorder import Recorder
from input.session_clock import SessionClock
from input.udp_reader import UDPReader

LIVE_DIR = BASE.parent / 'reports' / 'live_demo'
MIN_RECORD_SECONDS = 3.
MAX_RECORD_SECONDS = 15.
MIN_RECORD_SAMPLES = 300


@dataclass
class CompositionResult:
    csv_path: Path
    out_dir: Path
    score: dict
    profile: dict
    events: list
    play_bpm: float
    static_energy: bool


def _save_rows(rows, subject, scene='live'):
    """Keep the established CSV layout and personal-anchor lookup location."""
    recorder = Recorder(out_dir=LIVE_DIR / '_sessions', subject_id=subject)
    recorder.start()
    for row in rows:
        recorder.feed(row)
    recorder.stop()
    saved = recorder.save(scene=scene)
    if saved is None:
        raise ValueError('没有可保存的动作数据')
    csv_path = saved['csv']

    anchor_source = BASE.parent / 'data' / 'batch_2026_09_w1' / subject / 'baseline.json'
    anchor_target = csv_path.parent / 'baseline.json'
    if anchor_source.exists() and not anchor_target.exists():
        shutil.copy(anchor_source, anchor_target)
    return csv_path


def generate_rule_composition(csv_path, subject, static_energy=False):
    """Production rule path only; no LLM, event trial, posture or vision branch."""
    from profile import analyze, build_profile_json
    from composer_rule import compose
    from arrangement import build_arranged_events
    from live_demo import resolve_energy, show_motion_chart

    analysis = analyze(csv_path)
    if 'error' in analysis:
        raise ValueError(f"画像失败：{analysis['error']}")
    profile = build_profile_json(analysis, subject, 'live')
    energy, energy_source = resolve_energy(profile, csv_path, subject)
    profile['energy']['normalized'] = energy
    timeline = None
    dynamics = None
    if not static_energy:
        from energy_timeline import load_energy_timeline
        try:
            timeline = load_energy_timeline(csv_path)
            if timeline.get('anchor_rms'):
                energy = max(0., min(1., profile['energy']['gyro_rms'] / timeline['anchor_rms']))
                profile['energy']['normalized'] = energy
                energy_source = '本人校准（时间线）'
        except (ValueError, OSError, TypeError, KeyError) as exc:
            # Dynamic mode may fall back only when its existing input is unavailable.
            timeline = None
            dynamics = None
            profile['dynamic_fallback'] = str(exc)

    score = compose(profile, seed=int(time.time()) % 100000)
    if timeline is not None:
        from motion_dynamics import MotionDynamics
        try:
            dynamics = MotionDynamics(score, timeline, mode='song')
        except (ValueError, TypeError, KeyError) as exc:
            timeline = None
            profile['dynamic_fallback'] = str(exc)
    events, _, play_bpm = build_arranged_events(score, energy, dynamics=dynamics)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out_dir = LIVE_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy(csv_path, out_dir / 'input.csv')
    for name, content in (('profile.json', profile), ('score.json', score),
                          ('playback.json', {'version': 1, 'play_bpm': play_bpm, 'events': events})):
        (out_dir / name).write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding='utf-8')
    if dynamics is not None:
        (out_dir / 'energy_timeline.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding='utf-8')
        (out_dir / 'dynamics.json').write_text(json.dumps(dynamics.report(), ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        show_motion_chart(csv_path, profile, energy, energy_source, out_dir / 'motion.png',
                          interactive=False, dynamics=dynamics, timeline=timeline)
    except Exception as exc:
        (out_dir / 'motion_chart_error.txt').write_text(str(exc), encoding='utf-8')
    return CompositionResult(Path(csv_path), out_dir, score, profile, events, play_bpm, static_energy)


class ComposeSession:
    def __init__(self, subject='s00', static_energy=False, reader_factory=UDPReader, clock_factory=SessionClock):
        self.subject = subject
        self.static_energy = static_energy
        self.reader_factory = reader_factory
        self.clock_factory = clock_factory
        self.reader = None
        self.clock = None
        self.rows = []
        self.recording = False
        self.started_at = None
        self.worker = None
        self.result = None
        self.error = None

    def prepare(self):
        if self.reader is None:
            self.reader = self.reader_factory(port=4210)

    def start_recording(self, now=None, max_seconds=MAX_RECORD_SECONDS):
        self.prepare()
        for _ in range(10000):
            if self.reader.read() is None:
                break
        else:
            raise RuntimeError('UDP积压无法清空，请检查指挥棒数据流')
        self.rows = []
        self.clock = self.clock_factory()
        self.started_at = time.monotonic() if now is None else now
        self.max_record_seconds = max_seconds
        self.recording = True

    def poll_recording(self, now=None):
        if not self.recording:
            return None
        now = time.monotonic() if now is None else now
        for _ in range(200):
            line = self.reader.read()
            if line is None:
                break
            try:
                values = [float(value) for value in line.split(',')]
            except ValueError:
                continue
            if len(values) != 7 or not all(math.isfinite(value) for value in values):
                continue
            if self.clock.observe(values[0], now):
                self.rows.append(values)
        return 'recording_limit' if now - self.started_at >= self.max_record_seconds else None

    def finish_recording(self, now=None, scene='live', min_seconds=MIN_RECORD_SECONDS,
                         min_samples=MIN_RECORD_SAMPLES):
        if not self.recording:
            return None, '录制尚未开始'
        now = time.monotonic() if now is None else now
        self.recording = False
        elapsed = now - self.started_at
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        if elapsed < min_seconds or len(self.rows) < min_samples:
            return None, f'数据太少：{elapsed:.1f}秒、{len(self.rows)}点'
        try:
            return _save_rows(self.rows, self.subject, scene=scene), None
        except Exception as exc:
            return None, str(exc)

    def cancel_recording(self):
        self.recording = False
        self.rows = []
        if self.reader is not None:
            self.reader.close()
            self.reader = None

    def start_generation(self, csv_path):
        if self.worker is not None and self.worker.is_alive():
            raise RuntimeError('已有作曲任务正在进行')
        self.result = None
        self.error = None
        def generate():
            try:
                self.result = generate_rule_composition(csv_path, self.subject, self.static_energy)
            except Exception as exc:
                self.error = str(exc)
        self.worker = threading.Thread(target=generate, daemon=True)
        self.worker.start()

    def poll_generation(self):
        if self.worker is None or self.worker.is_alive():
            return None
        self.worker = None  # Completion is an edge, not a repeatedly reported state.
        if self.error:
            return 'generation_error', self.error
        return 'generation_complete', self.result

    def close(self):
        self.cancel_recording()


class CalibrationSession:
    """Three visible calibration captures; only vigorous determines the anchor."""
    SCENES = ('vigorous', 'gentle', 'free')
    RECORD_SECONDS = 5.
    MIN_SECONDS = 4.5
    MIN_SAMPLES = 450

    def __init__(self, subject='s00', capture_factory=ComposeSession):
        self.subject = subject
        self.capture_factory = capture_factory
        self.capture = capture_factory(subject=subject)
        self.index = 0
        self.paths = {}
        self.report = None

    @property
    def scene(self):
        return self.SCENES[self.index]

    def start_segment(self, now=None):
        self.capture.start_recording(now=now, max_seconds=self.RECORD_SECONDS)

    def poll_segment(self, now=None):
        return self.capture.poll_recording(now=now)

    def finish_segment(self, now=None):
        path, error = self.capture.finish_recording(
            now=now, scene=self.scene, min_seconds=self.MIN_SECONDS,
            min_samples=self.MIN_SAMPLES,
        )
        if error:
            return None, error
        self.paths[self.scene] = Path(path)
        if self.index < len(self.SCENES) - 1:
            self.index += 1
            return 'next_segment', None
        return 'review', None

    def build_report(self):
        if set(self.paths) != set(self.SCENES):
            raise ValueError('三段校准数据尚未录全')
        from calibrate import calculate_anchor
        from profile import analyze
        anchor, vigorous_windows = calculate_anchor(self.paths['vigorous'])
        if not math.isfinite(anchor) or anchor <= 0:
            raise ValueError('最大自然挥动未产生有效能量基准')
        segments = {}
        for scene, path in self.paths.items():
            analysis = analyze(path)
            if 'error' in analysis:
                raise ValueError(f'{scene} 数据分析失败：{analysis["error"]}')
            rms = float(analysis['gyro_rms'])
            segments[scene] = {
                'csv': str(path), 'gyro_rms': rms,
                'normalized': max(0., min(1., rms / anchor)),
            }
        self.report = {
            'version': 1, 'subject_id': self.subject,
            'method': 'vigorous_1s_rms_p95', 'anchor_rms': round(float(anchor), 3),
            'vigorous_windows_rms': [round(float(value), 3) for value in vigorous_windows],
            'segments': segments,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'note': 'gentle与free仅用于反馈，不参与anchor_rms计算。',
        }
        return self.report

    def save_baseline(self):
        if self.report is None:
            raise RuntimeError('请先生成校准结果')
        target_dir = LIVE_DIR / '_sessions' / self.subject
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        report_path = target_dir / f'calibration_{stamp}.json'
        report_path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding='utf-8')
        baseline = {
            'subject_id': self.subject, 'anchor_rms': self.report['anchor_rms'],
            'created_at': self.report['created_at'], 'method': self.report['method'],
            'calibration_report': report_path.name,
        }
        temporary = target_dir / 'baseline.json.tmp'
        temporary.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(target_dir / 'baseline.json')
        return target_dir / 'baseline.json', report_path

    def cancel(self):
        self.capture.cancel_recording()


class MidiPreview:
    """Stop-safe MIDI preview of already generated arrangement events."""
    def __init__(self, events, device_id=1, engine_factory=None):
        self.events = events
        self.device_id = device_id
        self.engine_factory = engine_factory
        self.stop_event = threading.Event()
        self.done = threading.Event()
        self.error = None
        self.thread = None

    def start(self):
        if self.thread is not None:
            raise RuntimeError('试听已启动')
        def play():
            engine = None
            try:
                if self.engine_factory is None:
                    from midi_engine import MidiEngine
                    self.engine_factory = MidiEngine
                engine = self.engine_factory(device_id=self.device_id)
                start = time.perf_counter()
                for event_time, kind, data, velocity in self.events:
                    while True:
                        wait = event_time - (time.perf_counter() - start)
                        if wait <= 0 or self.stop_event.wait(min(wait, .01)):
                            break
                    if self.stop_event.is_set():
                        break
                    if kind == 'melody_on': engine.play_melody(data, velocity)
                    elif kind == 'melody_off': engine.stop_melody(data)
                    elif kind == 'chord_on': engine.play_chord(data, velocity)
                    elif kind == 'chord_off': engine.stop_chord(data)
                    elif kind == 'bass_on': engine.play_bass(data, velocity)
                    elif kind == 'bass_off': engine.stop_bass(data)
                    elif kind == 'drum': engine.play_drum(data, velocity)
            except Exception as exc:
                self.error = str(exc)
            finally:
                if engine is not None:
                    engine.close()
                self.done.set()
        self.thread = threading.Thread(target=play, daemon=True)
        self.thread.start()

    def poll(self):
        if not self.done.is_set():
            return None
        return ('preview_error', self.error) if self.error else ('preview_finished', None)

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
