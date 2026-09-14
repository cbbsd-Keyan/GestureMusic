"""Simulated sensor tests: no UDP port or audio device required."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from audio.wand_control import WandControl


class WandTests(unittest.TestCase):
    def feed(self, c, start, end, mag):
        for tick in range(round(start*100), round(end*100)):
            now = tick/100
            c.ingest(f'{tick*10},0,0,9.8,{mag},0,0', now)
            if tick % 10 == 0:
                c.update(now)
        c.update(end-.01)

    def test_wait_move_stop_resume(self):
        c = WandControl(); c.update(0)
        self.assertTrue(c.paused)
        self.feed(c, 0, 1, 2.)
        self.assertFalse(c.paused)
        self.feed(c, 1, 3.5, 0.)
        self.assertTrue(c.paused)
        self.feed(c, 3.5, 4., 2.)
        self.assertFalse(c.paused)

    def test_volume_control_keeps_playback_speed_unchanged(self):
        c = WandControl()
        self.feed(c, 0, 2, 1.)
        soft = c.volume
        self.feed(c, 2, 4, 5.)
        self.assertGreater(c.volume, soft)
        self.assertLessEqual(c.volume, 1.)
        p = SimpleNamespace(paused=True, volume=0., target=1.1)
        p.set_volume = lambda v: setattr(p, 'volume', v)
        c.apply(p)
        self.assertFalse(p.paused)
        self.assertEqual(p.target, 1.1)
        c.enabled = False
        p.paused = True; p.volume = .42
        c.apply(p)
        self.assertTrue(p.paused)
        self.assertEqual(p.volume, .42)

    def test_any_gesture_rate_keeps_fixed_speed(self):
        c = WandControl()
        for tick in range(300):
            now = tick / 100
            mag = 4. if tick in (20, 57, 180) else 0.
            c.ingest(f'{tick*10},0,0,0,{mag},0,0', now)
            if tick % 10 == 0:
                c.update(now)
        c.update(2.99)
        self.assertEqual(c.tempo_status, 'FIXED')
        self.assertEqual(c.tempo, 1.)

    def test_bad_and_duplicate_packets_do_not_mask_disconnect(self):
        c = WandControl(); self.feed(c, 0, 1, 2.)
        for line in ('bad', '1000,0,0,0,nan,0,0', '1000,0,0,0,inf,0,0',
                     '990,0,0,0,2,0,0', '980,0,0,0,2,0,0'):
            self.assertFalse(c.ingest(line, 1.1))
        c.update(2.)
        self.assertTrue(c.paused)
        self.assertEqual(c.status, 'DISCONNECTED')
        # A rebooted board has a smaller device timestamp.
        self.assertTrue(c.ingest('10,0,0,0,0,0,0', 2.1))
        c.update(2.1)
        self.assertTrue(c.paused)
        self.assertEqual(c.status, 'QUIET')
        self.assertTrue(c.ingest('20,0,0,0,2,0,0', 2.2))
        c.update(2.2)
        self.assertFalse(c.paused)

    def test_batch_poll_keeps_fixed_speed(self):
        c = WandControl()
        lines = iter(f'{i*10},0,0,0,{3 if i in (10,60) else 0},0,0' for i in range(100))
        reader = SimpleNamespace(read=lambda: next(lines, None))
        c.poll(reader, 1.)
        self.assertEqual(c.tempo, 1.)
        self.assertEqual(c.tempo_status, 'FIXED')
        c.poll(reader, 2.1)
        self.assertEqual(c.status, 'DISCONNECTED')

    def test_reconnect_without_intermediate_poll_drops_old_motion(self):
        c = WandControl(); self.feed(c, 0, 1, 3.)
        self.assertFalse(c.paused)
        self.assertFalse(c.ingest('990,0,0,0,3,0,0', 2.1))
        c.ingest('2100,0,0,0,0,0,0', 2.1)
        c.update(2.1)
        self.assertTrue(c.paused)


if __name__ == '__main__':
    unittest.main()
