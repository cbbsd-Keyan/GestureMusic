"""动作能量的时间序列；所有窗口使用同一个个人基准或固定兜底尺度。"""
import json
import hashlib
import math
from pathlib import Path

from profile import load_rows, resample, TARGET_HZ, ACTIVE_THRESHOLD


def build_energy_timeline(rows, anchor_rms=None, step_s=0.1, window_s=1.0):
    if len(rows) < 2 or any(len(row) != 7 or not all(math.isfinite(v) for v in row) for row in rows):
        raise ValueError("能量时间线需要至少两条有限数值的动作数据")
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise ValueError("能量时间线要求严格递增的动作时间戳")
    if not (math.isfinite(step_s) and math.isfinite(window_s) and step_s >= 1 / TARGET_HZ and window_s > 0):
        raise ValueError("窗口和步长必须大于0")
    if anchor_rms is not None and (not math.isfinite(anchor_rms) or anchor_rms <= 0):
        raise ValueError("个人能量基准必须为正数")
    duration = (rows[-1][0] - rows[0][0]) / 1000.0
    uniform = resample(rows)
    if not uniform:
        raise ValueError("动作数据时长不足")
    squared = [sum(v * v for v in row[3:6]) for row in uniform]
    sums, active = [0.0], [0]
    for value in squared:
        sums.append(sums[-1] + value)
        active.append(active[-1] + int(value > ACTIVE_THRESHOLD ** 2))
    times = [i * step_s for i in range(int(duration / step_s) + 1)]
    if times[-1] < duration:
        times.append(duration)
    points = []
    half = max(1, round(window_s * TARGET_HZ / 2))
    for t in times:
        center = min(len(uniform) - 1, round(t * TARGET_HZ))
        lo, hi = max(0, center - half), min(len(uniform), center + half + 1)
        rms = math.sqrt(max(0.0, sums[hi] - sums[lo]) / (hi - lo))
        ratio = (active[hi] - active[lo]) / (hi - lo)
        energy = rms / anchor_rms if anchor_rms is not None else (rms - 1.0) / 5.0
        points.append({"t": round(t, 6), "gyro_rms": round(rms, 6),
                       "energy": round(max(0.0, min(1.0, energy)), 6),
                       "active_ratio": round(ratio, 6)})
    return {"version": 1, "duration_s": duration, "window_s": window_s,
            "step_s": step_s, "normalization": "personal" if anchor_rms else "fixed_fallback",
            "anchor_rms": anchor_rms, "points": points}


def load_energy_timeline(csv_path):
    csv_path = Path(csv_path)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    saved = csv_path.with_name("energy_timeline.json")
    if saved.exists():
        timeline = json.loads(saved.read_text(encoding="utf-8"))
        if timeline.get("version") != 1 or timeline.get("csv_sha256") != digest:
            raise ValueError("能量时间线与当前CSV不匹配")
        return timeline
    anchor = None
    baseline = csv_path.with_name("baseline.json")
    if baseline.exists():
        try:
            value = float(json.loads(baseline.read_text(encoding="utf-8"))["anchor_rms"])
            if math.isfinite(value) and value > 0:
                anchor = value
        except (OSError, ValueError, TypeError, KeyError):
            pass
    timeline = build_energy_timeline(load_rows(csv_path), anchor_rms=anchor)
    timeline["csv_sha256"] = digest
    return timeline
