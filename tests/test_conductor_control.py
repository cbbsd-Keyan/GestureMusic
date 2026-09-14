from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tempo_player import ConductorControl


class FakeWand:
    def __init__(self):
        self.moving = False
        self.polls = []

    def poll(self, reader, now):
        self.polls.append((reader, now))

    def apply(self, playback):
        playback.paused = not self.moving
        playback.target = 1.1 if self.moving else 1.


class FakePlayback:
    paused = True
    target = 1.


class ConductorControlTests(unittest.TestCase):
    def test_wand_motion_emits_start_and_stop_edges(self):
        wand = FakeWand(); playback = FakePlayback(); control = ConductorControl()
        self.assertIsNone(control.update(wand, 'reader', playback, 1.))
        wand.moving = True
        self.assertEqual(control.update(wand, 'reader', playback, 2.), 'wand_started')
        self.assertIsNone(control.update(wand, 'reader', playback, 3.))
        wand.moving = False
        self.assertEqual(control.update(wand, 'reader', playback, 4.), 'wand_paused')

    def test_manual_pause_holds_transport_until_resume(self):
        wand = FakeWand(); wand.moving = True; playback = FakePlayback(); control = ConductorControl()
        control.update(wand, None, playback, 0.)
        control.pause(playback)
        self.assertTrue(playback.paused)
        self.assertIsNone(control.update(wand, None, playback, 1.))
        control.resume()
        self.assertEqual(control.update(wand, None, playback, 2.), 'wand_started')


if __name__ == '__main__':
    unittest.main()
