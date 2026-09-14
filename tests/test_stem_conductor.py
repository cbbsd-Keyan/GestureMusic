from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from audio.stem_conductor import StemConductorSession, StemEvent, layer_levels


class Output:
    def __init__(self): self.calls = []
    def write_short(self, *args): self.calls.append(('control', args))
    def set_instrument(self, *args): self.calls.append(('program', args))
    def note_on(self, *args): self.calls.append(('on', args))
    def note_off(self, *args): self.calls.append(('off', args))
    def close(self): self.calls.append(('close', ()))


class Midi:
    def __init__(self): self.output = Output()
    def init(self): pass
    def quit(self): pass
    def Output(self, device): return self.output


class Reader:
    def close(self): pass


class Wand:
    def __init__(self): self.paused = True; self.rms = 0.; self.tempo = 1.
    def poll(self, reader, now): pass


class StemConductorTests(unittest.TestCase):
    def test_energy_grows_from_keyboard_to_full_ensemble(self):
        self.assertGreater(layer_levels(.1, True)['keyboard'], 0)
        self.assertEqual(layer_levels(.1, True)['drums'], 0)
        self.assertGreater(layer_levels(.9, True)['drums'], 0)
        self.assertEqual(sum(layer_levels(.9, False).values()), 0)

    def test_session_emits_transport_edges_and_original_note_events(self):
        midi = Midi()
        wand = Wand()
        events = [
            StemEvent(0., 'program', 0, 30, 0, 'guitar'),
            StemEvent(.1, 'note_on', 0, 60, 90, 'guitar'),
            StemEvent(.2, 'note_off', 0, 60, 0, 'guitar'),
        ]
        session = StemConductorSession(
            'unused.mid', midi_module=midi, reader_factory=lambda **_: Reader(),
            wand_factory=lambda: wand, event_loader=lambda _: events,
        )
        session.midi_path = Path(__file__)
        session.start()
        origin = session.last_tick
        wand.paused = False
        wand.rms = 4.
        self.assertEqual(session.update(origin + .15), 'wand_started')
        self.assertIn(('program', (30, 0)), midi.output.calls)
        self.assertIn(('on', (60, 90, 0)), midi.output.calls)
        wand.paused = True
        self.assertEqual(session.update(origin + .16), 'wand_paused')
        session.close()
