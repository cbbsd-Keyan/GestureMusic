"""validator 和声吸附开关的回归。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src" / "llm"))

from validator import validate_and_fix


def make_score(melody, chords=None):
    return {
        "bpm": 90,
        "bars": 4,
        "chords": chords or [{"bar": 0, "symbol": "C"}],
        "melody": melody,
    }


class HarmonySnapTests(unittest.TestCase):

    def test_off_by_default_no_change(self):
        s = make_score([{"bar": 0, "note": 61, "start": 0, "dur": 2, "velocity": 70}])
        out, fixes, _ = validate_and_fix(s)
        self.assertEqual(out["melody"][0]["note"], 61)
        self.assertFalse(any("吸附" in f for f in fixes))

    def test_strong_beat_snapped_to_nearest_chord_tone(self):
        # C和弦(60,64,67): 强拍 61 -> 最近 60
        s = make_score([{"bar": 0, "note": 61, "start": 0, "dur": 2, "velocity": 70}])
        out, fixes, _ = validate_and_fix(s, snap_harmony=True)
        self.assertEqual(out["melody"][0]["note"], 60)
        self.assertTrue(any("和弦音吸附1处" in f for f in fixes))

    def test_long_note_snapped(self):
        # C和弦: dur=4 的非和弦音 66 -> 67
        s = make_score([{"bar": 0, "note": 66, "start": 4, "dur": 4, "velocity": 70}])
        out, _, _ = validate_and_fix(s, snap_harmony=True)
        self.assertEqual(out["melody"][0]["note"], 67)

    def test_short_passing_tone_untouched(self):
        # 短时值非强拍 = 合法经过音, 不动
        s = make_score([{"bar": 0, "note": 62, "start": 3, "dur": 2, "velocity": 70}])
        out, fixes, _ = validate_and_fix(s, snap_harmony=True)
        self.assertEqual(out["melody"][0]["note"], 62)
        self.assertFalse(any("吸附" in f for f in fixes))

    def test_chord_tone_on_strong_beat_untouched(self):
        s = make_score([{"bar": 0, "note": 64, "start": 0, "dur": 2, "velocity": 70}])
        out, _, _ = validate_and_fix(s, snap_harmony=True)
        self.assertEqual(out["melody"][0]["note"], 64)

    def test_unknown_symbol_and_missing_bar_skipped(self):
        s = make_score(
            [{"bar": 0, "note": 61, "start": 0, "dur": 2, "velocity": 70},
             {"bar": 2, "note": 61, "start": 0, "dur": 2, "velocity": 70}],
            chords=[{"bar": 0, "symbol": "Xx"}, ],
        )
        out, fixes, _ = validate_and_fix(s, snap_harmony=True)
        self.assertEqual(out["melody"][0]["note"], 61)
        self.assertEqual(out["melody"][1]["note"], 61)
        self.assertFalse(any("吸附" in f for f in fixes))

    def test_range_safety(self):
        # 音域边缘: 83 不属于C和弦 pcs, 最近和弦音 84(E) 在域内
        s = make_score([{"bar": 0, "note": 83, "start": 0, "dur": 2, "velocity": 70}])
        out, _, _ = validate_and_fix(s, snap_harmony=True)
        self.assertEqual(out["melody"][0]["note"], 84)

    def test_tie_break_downward(self):
        # 65(C和弦): 距64为1、距67为2 -> 吸到64(向上)。
        # 用 62: 距60为2、距64为2 平局 -> 向下到60
        s = make_score([{"bar": 0, "note": 62, "start": 0, "dur": 2, "velocity": 70}])
        out, _, _ = validate_and_fix(s, snap_harmony=True)
        self.assertEqual(out["melody"][0]["note"], 60)


if __name__ == "__main__":
    unittest.main()
