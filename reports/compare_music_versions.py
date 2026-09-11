"""Offline comparison: same CSV, calibration, seed and score across revisions."""
import copy
import json
import pathlib
import shutil
import statistics
import subprocess
import sys
import types
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src/features'), str(ROOT / 'src/music')]
import profile
import composer_rule
import composer_events
import arrangement
from energy_timeline import build_energy_timeline
from motion_dynamics import MotionDynamics

OUT = ROOT / 'reports/regression_comparison'
OUT.mkdir(exist_ok=True)

def old_module(name, path):
    source = subprocess.check_output(['git', 'show', '392c0a6:' + path], cwd=ROOT)
    target = OUT / 'old' / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source)
    mod = types.ModuleType(name)
    mod.__file__ = str(target)
    exec(compile(source, str(target), 'exec'), mod.__dict__)
    return mod

old_profile = old_module('old_profile', 'src/features/profile.py')
old_rule = old_module('old_rule', 'src/music/composer_rule.py')
old_events = old_module('old_events', 'src/music/composer_events.py')
old_arrangement = old_module('old_arrangement', 'src/music/arrangement.py')
for path in ['src/live_demo.py', 'src/music/arrangement.py', 'src/music/composer_events.py',
             'src/music/composer_rule.py', 'src/music/motion_dynamics.py', 'src/features/energy_timeline.py']:
    target = OUT / 'before_audit' / path
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, target)

def summary(result):
    events, tier, bpm = result
    counts = Counter(k for _, k, _, _ in events)
    velocities = [v for _, k, _, v in events if k == 'melody_on']
    return dict(bpm=round(bpm, 3), initial_tier=tier, counts=dict(counts),
                melody_velocity=round(sum(velocities)/len(velocities), 2) if velocities else 0)

results = []
raw_checks = []
names = ['20260911_022612_712156', '20260911_023726_869508',
         '20260911_130645_966222', '20260911_130817_413311',
         '20260911_140222_681851', '20260911_140722_799225', '20260911_140937_742111']
for name in names:
    folder = ROOT / 'reports/live_demo' / name
    path = folder / 'input.csv'
    archived = json.loads((folder / 'profile.json').read_text(encoding='utf-8'))
    raw = profile.analyze(path)
    assert raw == old_profile.analyze(path)
    rows = profile.load_rows(path)
    low_rotation = [r for r in rows if profile.gyro_mag(r[1:]) < .5]
    raw_checks.append(dict(session=name, samples=len(rows), gyro_rms=raw['gyro_rms'],
        low_rotation_samples=len(low_rotation),
        low_rotation_accel_median=statistics.median(profile.accel_mag(r[1:]) for r in low_rotation)
            if low_rotation else None,
        gyro_axis_near_limit=sum(abs(v)>=17.4 for r in rows for v in r[4:7])))
    # Recompute raw features; restore recorded calibration, not today's directory state.
    p = profile.build_profile_json(raw, 's00', 'audit')
    p['energy']['normalized'] = archived['energy']['normalized']
    assert p['energy']['gyro_rms'] == archived['energy']['gyro_rms']
    n = p['energy']['normalized']
    anchor = None
    saved = folder / 'energy_timeline.json'
    if saved.exists():
        anchor = json.loads(saved.read_text(encoding='utf-8')).get('anchor_rms')
    elif n:
        anchor = p['energy']['gyro_rms'] / n
    timeline = build_energy_timeline(profile.load_rows(path), anchor_rms=anchor)
    level, energy = old_rule.energy_level(p)
    assert (level, energy) == composer_rule.energy_level(p)
    for mode in ['song', 'events']:
        old_score = old_rule.compose(p, seed=42) if mode == 'song' else old_events.compose_events(path, p)[0]
        new_score = composer_rule.compose(p, seed=42) if mode == 'song' else composer_events.compose_events(path, p)[0]
        if old_score is None or new_score is None:
            continue
        controller = MotionDynamics(new_score, timeline, mode)
        variants = {
            'old_full': old_arrangement.build_arranged_events(old_score, energy),
            'new_composer_old_arranger': old_arrangement.build_arranged_events(new_score, energy),
            'current_static': arrangement.build_arranged_events(new_score, energy),
            'current_dynamic': arrangement.build_arranged_events(new_score, energy, dynamics=controller),
        }
        record = dict(session=name, mode=mode, rms=raw['gyro_rms'], energy=energy, level=level,
                      anchor=anchor, old_melody=len(old_score['melody']), new_melody=len(new_score['melody']),
                      tiers=dict(Counter(b['tier'] for b in controller.bar_controls)),
                      variants={k: summary(v) for k,v in variants.items()})
        results.append(record)
        dest=OUT/name/mode
        dest.mkdir(parents=True, exist_ok=True)
        for key,value in variants.items():
            (dest/(key+'.json')).write_text(json.dumps(dict(events=value[0], bpm=value[2]),ensure_ascii=False),encoding='utf-8')
        print(name, mode, 'level', level, 'melody', record['old_melody'], record['new_melody'],
              'old/new', record['variants']['old_full'], record['variants']['current_dynamic'])
(OUT/'comparison.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
(OUT/'raw_checks.json').write_text(json.dumps(raw_checks,indent=2),encoding='utf-8')
