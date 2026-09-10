"""视觉音区、会话对齐、故障回退测试；所有硬件均使用替身。"""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import live_demo
import composer_events
from beacon_tracker import BeaconTracker

CSV = ROOT / "data/batch_2026_09_w1/s00/vigorous_001.csv"


class VisionFlowTests(unittest.TestCase):
    def test_visual_register_changes_notes_and_missing_samples_preserve_default(self):
        profile = live_demo.build_profile_json(live_demo.analyze(CSV), "s00", "ruler_v1")
        profile["energy"]["normalized"] = 0.5
        profile["tempo"] = {"bpm": 90, "confidence": "high"}
        detected = [(0.5, 1., 50), (1., 2., 100), (1.5, 3., 150)]
        with patch.object(composer_events, "extract_swing_events", return_value=detected):
            plain, _ = composer_events.compose_events(CSV, profile)
            visual, info = composer_events.compose_events(
                CSV, profile, vision_levels=[(0.5, -1), (1., 1)]
            )
            empty, empty_info = composer_events.compose_events(CSV, profile, vision_levels=[])
        self.assertEqual(plain["melody"][0]["note"], 69)
        self.assertEqual(visual["melody"][0]["note"], 57)
        self.assertEqual([n["note"] for n in plain["melody"]][1:3], [60, 57])
        self.assertEqual([n["note"] for n in visual["melody"]][1:3], [72, 69])
        self.assertEqual(visual["melody"][3:], plain["melody"][3:])
        self.assertEqual(info["vision"], {"低": 1, "中": 0, "高": 1, "未匹配": 1})
        self.assertEqual(empty, plain)
        self.assertEqual(empty_info["vision"]["未匹配"], 3)
        for a, b in zip(visual["melody"], plain["melody"]):
            self.assertEqual({k: v for k, v in a.items() if k != "note"},
                             {k: v for k, v in b.items() if k != "note"})

    def test_modes_are_exclusive_at_function_and_cli_boundaries(self):
        with self.assertRaisesRegex(ValueError, "不能同时"):
            composer_events.compose_events(CSV, {}, use_posture=True, vision_levels=[])
        for flags in (["--vision"], ["--events", "--vision", "--posture"]):
            with self.subTest(flags=flags), \
                 patch.object(sys, "argv", ["live_demo.py", *flags]), \
                 patch.object(live_demo, "UDPReader") as reader, \
                 contextlib.redirect_stderr(io.StringIO()), \
                 self.assertRaises(SystemExit) as exc:
                live_demo.main()
            self.assertEqual(exc.exception.code, 2)
            reader.assert_not_called()

    def test_tracker_converts_absolute_clock_to_csv_origin(self):
        tracker = BeaconTracker()
        tracker.box = (0, 0, 100, 100)
        tracker.positions = [(500.5, 0, 100), (501., 50, 50), (501.5, 100, 0)]
        self.assertEqual(tracker.levels(origin=500.), [(0.5, -1), (1., 0), (1.5, 1)])

    def test_recording_discards_old_packets_and_anchors_first_valid_row(self):
        reader = Mock()
        reader.read.side_effect = ["old packet", None, "ALIVE", "1000,1,2,3,4,5,6"]
        timing = {}
        with patch.object(live_demo.time, "monotonic",
                          side_effect=[100., 100., 100.1, 100.2, 100.3, 100.4, 102.]):
            rows = live_demo.record_swing(reader, 1., timing)
        self.assertEqual(rows, [[1000., 1., 2., 3., 4., 5., 6.]])
        self.assertEqual(timing["first_sample_monotonic"], 100.3)
        self.assertEqual(timing["host_origin_monotonic"], 100.3)
        self.assertEqual(timing["samples"], 1)

    def capture(self, tracker, interrupt=False):
        args = argparse.Namespace(subject="s00", vision=True, beacon="bright", camera=0, mirror=False)
        rows = live_demo.load_rows(CSV)
        def record(reader, seconds, timing):
            if interrupt:
                raise KeyboardInterrupt()
            timing["first_sample_monotonic"] = 500.
            timing.update(host_origin_monotonic=500., samples=len(rows),
                          duration_s=(rows[-1][0] - rows[0][0]) / 1000.,
                          receive_offset_span_s=0.)
            return rows
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(live_demo, "LIVE_DIR", Path(tmp)), \
             patch.object(live_demo, "UDPReader") as reader_type, \
             patch.object(live_demo, "check_board", return_value=True), \
             patch("beacon_tracker.BeaconTracker", return_value=tracker), \
             patch("builtins.input", return_value=""), \
             patch.object(live_demo, "record_swing", side_effect=record), \
             contextlib.redirect_stdout(io.StringIO()):
            try:
                _, vision = live_demo.capture_session(args)
                return vision
            finally:
                reader_type.return_value.close.assert_called_once()
                tracker.stop.assert_called()

    def test_capture_success_failure_and_interrupt_release_resources(self):
        tracker = Mock(error=None)
        tracker.calibrate.return_value = True
        tracker.start.return_value = True
        tracker.levels.return_value = [(0.5, 1)]
        self.assertEqual(self.capture(tracker)["levels"], [(0.5, 1)])
        rows = live_demo.load_rows(CSV)
        tracker.levels.assert_called_once_with(
            origin=500., duration=(rows[-1][0] - rows[0][0]) / 1000.)
        tracker = Mock(error="摄像头打不开")
        tracker.calibrate.return_value = False
        self.assertEqual(self.capture(tracker)["levels"], [])
        tracker.start.assert_not_called()
        tracker = Mock(error=None)
        tracker.calibrate.return_value = True
        tracker.start.return_value = True
        with self.assertRaises(KeyboardInterrupt):
            self.capture(tracker, interrupt=True)

    def test_capture_start_and_mid_recording_failures_fall_back(self):
        for during_recording in (False, True):
            with self.subTest(during_recording=during_recording):
                tracker = Mock(error=None)
                tracker.calibrate.return_value = True
                if during_recording:
                    tracker.start.return_value = True
                    def stop():
                        tracker.error = "摄像头断开"
                    tracker.stop.side_effect = stop
                else:
                    def start():
                        tracker.error = "摄像头打不开"
                        return False
                    tracker.start.side_effect = start
                vision = self.capture(tracker)
                self.assertEqual(vision["levels"], [])
                self.assertTrue(vision["error"])

    def test_replay_visual_session_without_camera(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "input.csv"
            csv_path.write_bytes(CSV.read_bytes())
            levels = [[t, (i % 3) - 1] for i, (t, _, _) in enumerate(
                composer_events.extract_swing_events(live_demo.resample(live_demo.load_rows(CSV))))]
            vision = {"version": 1, "time_reference": "csv_start", "levels": levels,
                      "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest()}
            (root / "vision.json").write_text(json.dumps(vision), encoding="utf-8")
            log = io.StringIO()
            with patch.object(sys, "argv", ["live_demo.py", "--events", "--vision",
                                           "--csv", str(csv_path), "--dry-run"]), \
                 patch.object(live_demo, "LIVE_DIR", root / "out"), \
                 patch.object(live_demo, "show_motion_chart"), \
                 patch("beacon_tracker.BeaconTracker") as tracker, \
                 contextlib.redirect_stdout(log):
                live_demo.main()
            tracker.assert_not_called()
            self.assertIn("[视觉音区(试验)]", log.getvalue())
            self.assertIn("未匹配0", log.getvalue())
            saved = list((root / "out").glob("*/vision.json"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(live_demo.load_vision(saved[0].with_name("input.csv")), vision)
            csv_path.write_bytes(b"different recording")
            with self.assertRaisesRegex(ValueError, "不匹配"):
                live_demo.load_vision(csv_path)

    def test_tracker_read_failure_is_reported_and_released(self):
        tracker = BeaconTracker()
        camera = Mock()
        camera.read.return_value = (False, None)
        tracker.cap = camera
        tracker._running = True
        tracker._loop()
        self.assertIn("读取失败", tracker.error)
        camera.release.assert_called_once()
        self.assertIsNone(tracker.cap)

    def test_camera_open_failure_and_missing_dependency(self):
        camera = Mock()
        camera.isOpened.return_value = False
        cv2 = Mock()
        cv2.VideoCapture.return_value = camera
        tracker = BeaconTracker()
        with patch.dict(sys.modules, {"cv2": cv2}):
            self.assertFalse(tracker._open())
        camera.release.assert_called_once()
        self.assertIsNone(tracker.cap)
        with patch.dict(sys.modules, {"cv2": None}):
            self.assertFalse(tracker._open())
        self.assertIn("requirements-vision.txt", tracker.error)


if __name__ == "__main__":
    unittest.main()
