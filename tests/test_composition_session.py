from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import csv
import json
from unittest.mock import patch

import composition_session
from composition_session import CalibrationSession, ComposeSession, MidiPreview


class FakeReader:
    def __init__(self, lines=()):
        self.lines = list(lines)
        self.closed = False

    def read(self):
        return self.lines.pop(0) if self.lines else None

    def close(self):
        self.closed = True


class FakeClock:
    def __init__(self):
        self.seen = []

    def observe(self, stamp, received):
        if self.seen and stamp <= self.seen[-1][0]:
            return False
        self.seen.append((stamp, received))
        return True


class CompositionSessionTests(unittest.TestCase):
    @staticmethod
    def _write_motion_csv(path, gyro):
        with open(path, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            writer.writerow(('time_ms', 'ax', 'ay', 'az', 'gx', 'gy', 'gz'))
            for index in range(501):
                writer.writerow((index * 10, 0., 0., 9.80665, gyro, 0., 0.))

    def test_recording_accepts_only_finite_increasing_seven_column_samples(self):
        reader = FakeReader()
        session = ComposeSession(reader_factory=lambda **kw: reader, clock_factory=FakeClock)
        session.start_recording(now=1.)
        reader.lines = ['junk', '0,0,0,0,nan,0,0', '0,0,0,0,1,0,0',
                        '10,0,0,0,2,0,0', '10,0,0,0,3,0,0']
        self.assertIsNone(session.poll_recording(now=1.1))
        self.assertEqual([row[0] for row in session.rows], [0., 10.])

    def test_recording_limit_and_short_capture_rejection_release_udp(self):
        reader = FakeReader()
        session = ComposeSession(reader_factory=lambda **kw: reader, clock_factory=FakeClock)
        session.start_recording(now=0.)
        self.assertEqual(session.poll_recording(now=15.), 'recording_limit')
        path, error = session.finish_recording(now=15.)
        self.assertIsNone(path)
        self.assertIn('数据太少', error)
        self.assertTrue(reader.closed)
        self.assertIsNone(session.reader)

    def test_generation_completion_is_reported_once(self):
        session = ComposeSession()
        session.worker = type('Finished', (), {'is_alive': lambda self: False})()
        session.result = object()
        self.assertEqual(session.poll_generation()[0], 'generation_complete')
        self.assertIsNone(session.poll_generation())

    def test_preview_dispatches_events_and_closes_engine(self):
        class Engine:
            def __init__(self, **kw): self.calls = []; self.closed = False
            def play_melody(self, *args): self.calls.append(('on', args))
            def stop_melody(self, *args): self.calls.append(('off', args))
            def close(self): self.closed = True
        created = []
        def factory(**kw):
            item = Engine(**kw); created.append(item); return item
        preview = MidiPreview([(0., 'melody_on', 60, 80), (0., 'melody_off', 60, 0)],
                              engine_factory=factory)
        preview.start()
        preview.thread.join(1)
        self.assertEqual(preview.poll(), ('preview_finished', None))
        self.assertEqual([call[0] for call in created[0].calls], ['on', 'off'])
        self.assertTrue(created[0].closed)

    def test_calibration_anchor_uses_vigorous_only_and_saves_only_after_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vigorous = root / 'vigorous.csv'
            gentle = root / 'gentle.csv'
            free = root / 'free.csv'
            self._write_motion_csv(vigorous, 10.)
            self._write_motion_csv(gentle, 2.)
            self._write_motion_csv(free, 80.)

            session = CalibrationSession(subject='tester')
            session.paths = {'vigorous': vigorous, 'gentle': gentle, 'free': free}
            with self.assertRaises(RuntimeError):
                session.save_baseline()
            report = session.build_report()
            self.assertAlmostEqual(report['anchor_rms'], 10., places=3)
            self.assertAlmostEqual(report['segments']['gentle']['normalized'], .2, places=3)
            self.assertEqual(report['segments']['free']['normalized'], 1.)

            live_dir = root / 'live'
            with patch.object(composition_session, 'LIVE_DIR', live_dir):
                baseline_path, report_path = session.save_baseline()
            self.assertTrue(baseline_path.exists())
            self.assertTrue(report_path.exists())
            saved = json.loads(baseline_path.read_text(encoding='utf-8'))
            self.assertEqual(saved['anchor_rms'], 10.)
            self.assertEqual(saved['calibration_report'], report_path.name)


if __name__ == '__main__':
    unittest.main()
