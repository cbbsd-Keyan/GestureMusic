"""离线事件流程回归；不连接开发板、MIDI 或模型 API。"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import live_demo
import composer_events
from composer_rule import validate_score
from arrangement import build_arranged_events

CSV = ROOT / "data/batch_2026_09_w1/s00/vigorous_001.csv"


class EventFlowTests(unittest.TestCase):
    def test_dataset_regression(self):
        paths = sorted((ROOT / "data/batch_2026_09_w1").glob("*/*.csv"))
        self.assertTrue(paths)
        for path in paths:
            profile = live_demo.build_profile_json(
                live_demo.analyze(path), path.parent.name, "ruler_v1"
            )
            detected = composer_events.extract_swing_events(
                live_demo.resample(live_demo.load_rows(path))
            )
            modes = [(False, None), (True, None),
                     (False, [(t, (i % 3) - 1) for i, (t, _, _) in enumerate(detected)])]
            for posture, vision in modes:
                with self.subTest(csv=str(path), posture=posture, vision=vision is not None):
                    score, info = composer_events.compose_events(
                        path, profile, use_posture=posture, vision_levels=vision
                    )
                    if len(detected) < 3:
                        self.assertIsNone(score)
                        continue
                    self.assertEqual(validate_score(score), [])
                    counts = info["counts"]
                    self.assertEqual(sum(counts.values()), len(detected))
                    self.assertEqual(
                        len(score["melody"]),
                        counts["轻"] + 2 * counts["中"] + 4 * counts["重"],
                    )
                    if posture and len(detected) >= 6:
                        self.assertEqual(sum(info["posture"].values()), len(detected))
                    else:
                        self.assertIsNone(info["posture"])
                    if vision is not None:
                        self.assertEqual(info["vision"]["未匹配"], 0)
                        self.assertEqual(sum(info["vision"].values()), len(detected))
                    events, _, _ = build_arranged_events(score, 0.5)
                    self.assertTrue(events)

    def run_demo(self, *flags):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(live_demo, "LIVE_DIR", Path(tmp)), \
                 patch.object(live_demo, "show_motion_chart"), \
                 patch.object(sys, "argv", ["live_demo.py", "--csv", str(CSV),
                                           "--dry-run", *flags]), \
                 contextlib.redirect_stdout(output):
                live_demo.main()
            scores = list(Path(tmp).glob("*/score.json"))
            self.assertEqual(len(scores), 1)
            score = json.loads(scores[0].read_text(encoding="utf-8"))
        return score, output.getvalue()

    def test_plain_and_posture_entrypoints(self):
        plain, log = self.run_demo("--events")
        self.assertIn("下挥落音(试验)", log)
        posture, log = self.run_demo("--events", "--posture")
        self.assertIn("[姿态音区(试验)]", log)
        self.assertEqual(len(plain["melody"]), len(posture["melody"]))
        self.assertTrue(any(a["note"] != b["note"] for a, b in
                            zip(plain["melody"], posture["melody"])))

    def test_too_few_events_falls_back_even_with_llm_flag(self):
        with patch.object(composer_events, "extract_swing_events", return_value=[]):
            score, log = self.run_demo("--events", "--llm")
        self.assertIn("自动用规则作曲", log)
        self.assertIn("[作曲] 规则作曲", log)
        self.assertNotIn("大模型", log)
        self.assertTrue(score["melody"])

    def test_posture_with_three_events_uses_default_register(self):
        with patch.object(composer_events, "extract_swing_events",
                          return_value=[(0.5, 1.0, 50), (1.0, 2.0, 100),
                                        (1.5, 3.0, 150)]):
            score, log = self.run_demo("--events", "--posture")
        self.assertIn("挥动不足6次", log)
        self.assertEqual(score["title"], "下挥落音")

    def test_posture_requires_events_before_any_recording(self):
        with patch.object(sys, "argv", ["live_demo.py", "--posture"]), \
             patch.object(live_demo, "UDPReader") as reader, \
             contextlib.redirect_stderr(io.StringIO()), \
             self.assertRaises(SystemExit) as error:
            live_demo.main()
        self.assertEqual(error.exception.code, 2)
        reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
