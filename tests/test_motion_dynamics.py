"""动作动态配器验收：固定旋律，只改变动作的时间顺序。"""
import contextlib
import copy
import hashlib
import io
import json
import csv
import importlib.util
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import live_demo
from energy_timeline import build_energy_timeline, load_energy_timeline
from motion_dynamics import MotionDynamics
from arrangement import build_arranged_events
from composer_events import extract_swing_events, compose_events
from composer_rule import compose, validate_score


def motion(values, duration=24.):
    return [[i * 10., 0., 0., 9.80665, 0., values(min(i / 100., duration)), 0.]
            for i in range(round(duration * 100) + 1)]


def score():
    return {"bpm": 120, "bars": 12, "key": "C", "title": "固定旋律",
            "chords": [{"bar": b, "symbol": "C"} for b in range(12)],
            "melody": [{"bar": b, "start": p, "dur": 2, "note": 72, "velocity": 80}
                       for b in range(12) for p in (0, 8)]}


class MotionDynamicsTests(unittest.TestCase):
    def render(self, values, mode="song", plain=False):
        timeline = build_energy_timeline(motion(values))
        s = score()
        controller = MotionDynamics(s, timeline, mode)
        events, _, bpm = build_arranged_events(s, 0.5, dynamics=controller, plain=plain)
        return s, controller, events, bpm

    def test_strength_order_controls_drums_and_velocity_without_changing_pitch_or_speed(self):
        for levels, expected in [((1.5, 5.5, 1.5), (False, True, False)),
                                 ((5.5, 1.5, 5.5), (True, False, True))]:
            with self.subTest(levels=levels):
                _, controller, events, bpm = self.render(lambda t: levels[min(2, int(t / 8))])
                drums = [sum(kind == "drum" and k * 8 <= t - controller.intro_seconds < (k+1)*8
                             for t, kind, _, _ in events) for k in range(3)]
                self.assertEqual(tuple(n > 0 for n in drums), expected)
                means = []
                for k in range(3):
                    velocities = [v for t, kind, _, v in events if kind == "melody_on"
                                  and k*8+1 <= t-controller.intro_seconds < (k+1)*8-1]
                    means.append(sum(velocities)/len(velocities))
                self.assertEqual(means[1] > means[0], expected[1])
                self.assertEqual(means[1] > means[2], expected[1])
                self.assertEqual({n for _, kind, n, _ in events if kind == "melody_on"}, {72})
                self.assertEqual(bpm, 120)

    def test_gradual_rise_and_threshold_jitter(self):
        _, controller, events, _ = self.render(lambda t: 1.5 + 4*t/24, plain=True)
        velocities = [v for _, kind, _, v in events if kind == "melody_on"]
        self.assertTrue(all(b >= a for a, b in zip(velocities, velocities[1:])))
        self.assertGreater(velocities[-1], velocities[0])
        _, controller, _, _ = self.render(lambda t: 1 + 5*(.32 if int(t/2)%2 == 0 else .34))
        self.assertEqual({c["tier"] for c in controller.bar_controls}, {"calm"})

    def test_rest_stops_all_body_parts_and_every_note_has_an_end(self):
        _, controller, events, _ = self.render(lambda t: 0. if 8 <= t < 16 else 5.5)
        left, right = controller.intro_seconds + 9, controller.intro_seconds + 15
        for t, kind, _, _ in events:
            self.assertFalse(left < t < right and (kind.endswith("_on") or kind == "drum"))
        balance = {}
        for _, kind, data, _ in events:
            if kind == "drum":
                continue
            key = (kind.split("_")[0], tuple(data) if isinstance(data, list) else data)
            balance[key] = balance.get(key, 0) + (1 if kind.endswith("_on") else -1)
            self.assertGreaterEqual(balance[key], 0)
        self.assertTrue(all(n == 0 for n in balance.values()))
        _, _, silent, _ = self.render(lambda t: 0.)
        self.assertEqual(silent, [])

    def test_event_mapping_preserves_source_seconds_and_mutes_padding(self):
        timeline = build_energy_timeline(motion(lambda t: 5.5, duration=5.))
        s = score()
        controller = MotionDynamics(s, timeline, "events")
        events, _, _ = build_arranged_events(s, .9, dynamics=controller)
        self.assertAlmostEqual(controller.source_time(16), 2.)
        ons = [t for t, kind, _, _ in events if kind.endswith("_on")]
        self.assertIn(controller.intro_seconds + 2., ons)
        # 最后两个起音是独立尾声；补齐部分不再生成主体音符。
        self.assertTrue(all(t <= controller.intro_seconds + 5 for t in ons[:-2]))
        self.assertLessEqual(max(ons), controller.intro_seconds + 5 + controller.grid_s)
        song = MotionDynamics(s, timeline, "song")
        self.assertAlmostEqual(song.source_time(96), 2.5)
        self.assertEqual(controller.report()["body_start_s"], 2.)

    def test_cadence_survives_final_rest_and_padding(self):
        for mode, duration, stop in (("song", 24., 16.), ("events", 5., 5.),
                                     ("song", 24., 24.)):
            with self.subTest(mode=mode, duration=duration, stop=stop):
                s = score()
                timeline = build_energy_timeline(motion(lambda t: 5.5 if t < stop else 0., duration))
                controller = MotionDynamics(s, timeline, mode)
                events, _, _ = build_arranged_events(s, .9, dynamics=controller)
                # 尾声始终为最后和弦三拍、根音四拍，且不受停手截断。
                onset = max(t for t, kind, _, _ in events if kind.endswith("_on"))
                tail = [(t, kind, data, v) for t, kind, data, v in events if t >= onset]
                self.assertEqual(sum(kind == "chord_on" for _, kind, _, _ in tail), 1)
                self.assertIn((onset, "bass_on", 36), [(t, k, d) for t, k, d, _ in tail])
                self.assertIn(onset + 12 * controller.grid_s,
                              [t for t, k, _, _ in tail if k == "chord_off"])
                self.assertIn(onset + 16 * controller.grid_s,
                              [t for t, k, _, _ in tail if k == "bass_off"])
                if stop < duration or mode == "events":
                    body_end = max(t for t, k, _, _ in events
                                   if k.endswith("_off") and t <= onset)
                    self.assertAlmostEqual(onset, body_end)
                    self.assertLess(onset, controller.intro_seconds + 24.)
                else:
                    self.assertAlmostEqual(onset, controller.intro_seconds + 24.)

    def test_local_detector_keeps_gentle_events_next_to_strong_events(self):
        for amplitudes in ((1., 10., 1.), (1., 1., 1.)):
            rows = motion(lambda t: .1 + amplitudes[min(2, int(t/5))]
                          * math.exp(-((t % 1 - .5)/.08)**2), duration=15.)
            events = extract_swing_events([r[1:] for r in rows])
            self.assertEqual([sum(k*5 <= t < (k+1)*5 for t,_,_ in events) for k in range(3)], [5,5,5])
        noise = motion(lambda t: .1 + .03*math.sin(20*t), duration=15.)
        self.assertEqual(extract_swing_events([r[1:] for r in noise]), [])

    def test_timeline_shared_calibration_and_validation(self):
        rows = motion(lambda t: 2. if t < 12 else 6.)
        timeline = build_energy_timeline(rows, anchor_rms=8.)
        self.assertAlmostEqual(timeline["points"][20]["energy"], .25)
        self.assertAlmostEqual(timeline["points"][-20]["energy"], .75)
        for kwargs in ({"step_s": float("inf")}, {"anchor_rms": 0.}, {"window_s": float("nan")}):
            with self.assertRaises(ValueError):
                build_energy_timeline(rows, **kwargs)
        for invalid in (rows[::-1], [[0., 1.], [10., 2.]]):
            with self.assertRaises(ValueError):
                build_energy_timeline(invalid)

    def test_legacy_arrangement_unchanged_for_existing_scores(self):
        s = json.loads((ROOT / "reports/batch_FINAL/pV3_p1_1.json").read_text(encoding="utf-8"))
        expected = {
            (.1, False): "4f9b4da01b9e0ce09c3f3c7c0589d2472e59faefdcb8df73be1bb56b6a529a2c",
            (.1, True): "f7e018306cd9d045caf129fb8c007dff33230a2ce8ddcaa5361080443667a51d",
            (.5, False): "80799ac8805b4b055323696a4e40d036599025d502f291b72e935cc3de43df77",
            (.5, True): "bc082efecf9a6c1cbebe92cd1be5530a51f9dac36e586bd6a5f826c449e3d043",
            (.9, False): "94d58343d9aad47adb5c419265741faf54902ac1a86c709a203826f099b86284",
            (.9, True): "9b7ba6fb854e061d3cadb020b572453d6c3226029cc3ef7dc3950c12d988bc39",
        }
        for (energy, plain), digest in expected.items():
            events = build_arranged_events(s, energy, plain=plain)
            self.assertEqual(hashlib.sha256(json.dumps(events, sort_keys=True).encode()).hexdigest(), digest)

    def test_real_dataset_rule_and_event_dynamics(self):
        for path in sorted((ROOT / "data/batch_2026_09_w1").glob("*/*.csv")):
            timeline = load_energy_timeline(path)
            profile = live_demo.build_profile_json(live_demo.analyze(path), path.parent.name, "ruler_v1")
            for s, mode in ((compose(profile, seed=42), "song"),
                            (compose_events(path, profile)[0], "events")):
                with self.subTest(path=path, mode=mode):
                    if s is None:
                        continue
                    self.assertEqual(validate_score(s), [])
                    before = copy.deepcopy(s)
                    controller = MotionDynamics(s, timeline, mode)
                    events, _, _ = build_arranged_events(s, .5, dynamics=controller)
                    self.assertEqual(s, before)
                    self.assertTrue(all(math.isfinite(t) and t >= 0 for t, _, _, _ in events))
                    self.assertEqual([e[0] for e in events], sorted(e[0] for e in events))

    def test_demo_archives_mapping_and_reuses_personal_timeline(self):
        csv = ROOT / "data/batch_2026_09_w1/s00/vigorous_001.csv"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch.object(live_demo, "LIVE_DIR", out), patch.object(live_demo, "show_motion_chart"), \
                 patch.object(sys, "argv", ["live_demo.py", "--csv", str(csv), "--events", "--dry-run"]), \
                 contextlib.redirect_stdout(io.StringIO()):
                live_demo.main()
            session = next(out.iterdir())
            report = json.loads((session / "dynamics.json").read_text(encoding="utf-8"))
            self.assertEqual(report["mapping"], "events")
            timeline = load_energy_timeline(session / "input.csv")
            self.assertEqual(timeline["normalization"], "personal")
            playback = json.loads((session / "playback.json").read_text(encoding="utf-8"))
            self.assertTrue(playback["events"])
            (session / "input.csv").write_bytes(b"wrong session")
            with self.assertRaises(ValueError):
                load_energy_timeline(session / "input.csv")

    def test_llm_result_uses_song_mapping_and_fatal_result_falls_back(self):
        csv = ROOT / "data/batch_2026_09_w1/s00/vigorous_001.csv"
        for returned, title in ((score(), "固定旋律"), ({"melody": []}, None)):
            with self.subTest(valid=title is not None), tempfile.TemporaryDirectory() as tmp:
                output = io.StringIO()
                with patch.object(live_demo, "LIVE_DIR", Path(tmp)), \
                     patch.object(live_demo, "show_motion_chart"), \
                     patch("client.call_llm", return_value=(returned, {"model": "mock", "latency_s": 0})), \
                     patch.object(sys, "argv", ["live_demo.py", "--csv", str(csv), "--llm", "--dry-run"]), \
                     contextlib.redirect_stdout(output):
                    live_demo.main()
                session = next(Path(tmp).iterdir())
                report = json.loads((session / "dynamics.json").read_text(encoding="utf-8"))
                actual = json.loads((session / "score.json").read_text(encoding="utf-8"))
                self.assertEqual(report["mapping"], "song")
                if title:
                    self.assertEqual(actual["title"], title)
                else:
                    self.assertIn("自动切换规则作曲", output.getvalue())
                    self.assertTrue(actual["melody"])

    def test_static_demo_does_not_emit_dynamic_report(self):
        csv = ROOT / "data/batch_2026_09_w1/s00/gentle_001.csv"
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(live_demo, "LIVE_DIR", Path(tmp)), patch.object(live_demo, "show_motion_chart"), \
                 patch.object(sys, "argv", ["live_demo.py", "--csv", str(csv), "--static-energy", "--dry-run"]), \
                 contextlib.redirect_stdout(io.StringIO()):
                live_demo.main()
            session = next(Path(tmp).iterdir())
            self.assertFalse((session / "dynamics.json").exists())
            self.assertTrue((session / "playback.json").exists())

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"), "图形验收需要matplotlib")
    def test_render_motion_chart_with_register_and_dynamic_panels(self):
        out = Path(tempfile.mkdtemp(prefix="gesture-chart-qa-"))
        path = out / "input.csv"
        rows = motion(lambda t: (1.5, 5.5, 1.5)[min(2, int(t/8))])
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["time_ms", "ax", "ay", "az", "gx", "gy", "gz"])
            writer.writerows(rows)
        profile = live_demo.build_profile_json(live_demo.analyze(path), "test", "ruler_v1")
        timeline = build_energy_timeline(rows)
        controller = MotionDynamics(score(), timeline)
        build_arranged_events(score(), .5, dynamics=controller)
        png = out / "motion.png"
        live_demo.show_motion_chart(path, profile, .5, "保底换算", png, interactive=False,
                                    register_times=[(i, (i % 3)-1) for i in range(24)],
                                    register_mode="vision", dynamics=controller, timeline=timeline)
        self.assertGreater(png.stat().st_size, 1000)
        print("CHART_QA", png)


if __name__ == "__main__":
    unittest.main()
