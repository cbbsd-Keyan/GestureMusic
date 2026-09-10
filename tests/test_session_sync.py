"""时间对齐与相机线程回归；不使用真实摄像头、UDP或墙上时钟。"""
import contextlib
import io
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import live_demo
import beacon_tracker
from beacon_tracker import BeaconTracker
from session_clock import SessionClock


class SessionSyncTests(unittest.TestCase):
    def test_delayed_first_packet_does_not_shift_whole_session(self):
        clock = SessionClock()
        for device, received in [(10000., 500.1), (10500., 500.52), (11000., 501.)]:
            clock.observe(device, received)
        sync = clock.summary()
        self.assertAlmostEqual(sync["host_origin_monotonic"], 500.)
        self.assertAlmostEqual(sync["receive_offset_span_s"], 0.1)
        tracker = BeaconTracker()
        tracker.box = (0, 0, 100, 100)
        tracker.positions = [(499.99, 0, 100), (500.5, 100, 0), (501.01, 0, 100)]
        self.assertEqual(tracker.levels(sync["host_origin_monotonic"], sync["duration_s"]),
                         [(0.5, 1)])

    def test_duplicates_are_ignored_and_rollback_or_invalid_clock_rejected(self):
        clock = SessionClock()
        self.assertTrue(clock.observe(1000., 500.))
        self.assertFalse(clock.observe(1000., 500.1))
        self.assertEqual(clock.summary()["samples"], 1)
        self.assertEqual(clock.summary()["duplicate_samples"], 1)
        for device, received in [(999., 500.2), (float("nan"), 500.2),
                                 (1010., float("inf"))]:
            with self.subTest(device=device, received=received), self.assertRaises(ValueError):
                clock.observe(device, received)

    def test_recording_rejects_device_restart(self):
        reader = Mock()
        reader.read.side_effect = [None, "1000,1,2,3,4,5,6", "0,1,2,3,4,5,6"]
        with patch.object(live_demo.time, "monotonic", return_value=500.), \
             self.assertRaisesRegex(ValueError, "时间戳倒退"):
            live_demo.record_swing(reader, 15.)

    def test_start_after_calibration_reuses_worker_and_clears_old_samples(self):
        tracker = BeaconTracker()
        tracker._thread = Mock()
        tracker._thread.is_alive.return_value = True
        tracker._running = True
        tracker.box = (0, 0, 100, 100)
        tracker.positions = [(499., 0, 0)]
        with patch.object(tracker, "_open") as opener:
            self.assertTrue(tracker.start())
        opener.assert_not_called()
        self.assertEqual(tracker.positions, [])
        self.assertEqual(tracker.box, (0, 0, 100, 100))

    def test_calibration_success_keeps_capture_alive_and_interrupt_stops_it(self):
        tracker = BeaconTracker()
        def start():
            tracker._running = True
            tracker.positions = [(float(i), i * 5, i * 4) for i in range(30)]
            return True
        with patch.object(tracker, "start", side_effect=start), \
             patch.object(tracker, "stop") as stop, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(tracker.calibrate(seconds=0.))
        stop.assert_not_called()
        self.assertIsNotNone(tracker.box)
        with patch.object(tracker, "start", side_effect=KeyboardInterrupt), \
             patch.object(tracker, "stop") as stop, self.assertRaises(KeyboardInterrupt):
            tracker.calibrate()
        stop.assert_called_once()

    def test_blocked_camera_times_out_without_concurrent_release(self):
        tracker = BeaconTracker()
        camera = Mock()
        entered = threading.Event()
        finish = threading.Event()
        def read():
            entered.set()
            finish.wait(2.)
            return True, object()
        camera.read.side_effect = read
        def open_camera():
            tracker.cap = camera
            return True
        try:
            with patch.object(tracker, "_open", side_effect=open_camera), \
                 patch.object(beacon_tracker, "CAMERA_TIMEOUT", 0.02):
                self.assertFalse(tracker.start())
                self.assertTrue(entered.wait(1.))
                tracker.stop()
                self.assertIn("未及时", tracker.error)
                camera.release.assert_not_called()
        finally:
            finish.set()
            if tracker._thread is not None:
                tracker._thread.join(timeout=2.)
            tracker.stop()
        camera.release.assert_called_once()
        self.assertIsNone(tracker.cap)
        self.assertEqual(tracker.positions, [])

    def test_slow_frame_is_not_used_as_current_position(self):
        tracker = BeaconTracker()
        tracker.cap = Mock()
        tracker.cap.read.side_effect = [(True, object()), (False, None)]
        tracker._running = True
        with patch.object(beacon_tracker.time, "monotonic", side_effect=[100., 100.5, 100.6, 100.7]), \
             patch.object(tracker, "detect") as detect:
            tracker._loop()
        detect.assert_not_called()
        self.assertEqual(tracker.positions, [])

    def test_camera_open_timeout_does_not_block_main_thread(self):
        tracker = BeaconTracker()
        camera = Mock()
        finish = threading.Event()
        entered = threading.Event()
        def open_camera():
            entered.set()
            finish.wait(2.)
            tracker.cap = camera
            return True
        try:
            with patch.object(tracker, "_open", side_effect=open_camera), \
                 patch.object(beacon_tracker, "CAMERA_TIMEOUT", 0.02):
                self.assertFalse(tracker.start())
                self.assertTrue(entered.wait(1.))
                tracker.stop()
                camera.release.assert_not_called()
        finally:
            finish.set()
            if tracker._thread is not None:
                tracker._thread.join(timeout=2.)
            tracker.stop()
        camera.read.assert_not_called()
        camera.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
