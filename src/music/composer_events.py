import math
import statistics

from profile import load_rows, resample

from composer_rule import (
    PROGRESSIONS,
    energy_level,
    resolve_bpm,
)


NOTE_MIN = 48
NOTE_MAX = 84


def _pitch(ax, ay, az):

    return math.degrees(
        math.atan2(
            -ax,
            math.sqrt(ay * ay + az * az),
        )
    )


def extract_swing_events(uniform, hz=100.0):

    """
    从重采样序列提取每次挥动的(时刻, 力度, 峰值索引)。
    逻辑与 tempo.py 峰检测一致, 独立实现避免改动现有代码。
    """

    mags = []

    for v in uniform:

        mags.append(
            (v[3] ** 2 + v[4] ** 2 + v[5] ** 2)
            ** 0.5
        )

    half = 5

    sm = []

    for i in range(len(mags)):

        lo = max(0, i - half)
        hi = min(len(mags), i + half + 1)

        sm.append(
            statistics.fmean(mags[lo:hi])
        )

    if not sm:
        return []

    mean = statistics.fmean(sm)

    std = statistics.pstdev(sm)

    if std <= 0:
        return []

    threshold = mean + 0.5 * std

    min_gap = max(
        2,
        int(hz * 60 / 180),
    )

    events = []

    last = -10 * min_gap

    for i in range(1, len(sm) - 1):

        if (
            sm[i] >= sm[i - 1]
            and sm[i] > sm[i + 1]
            and sm[i] > threshold
            and i - last >= min_gap
        ):

            events.append(
                (i / hz, sm[i], i)
            )

            last = i

    return events


def _wrap(note):

    while note < NOTE_MIN:
        note += 12

    while note > NOTE_MAX:
        note -= 12

    return note


def _vision_octave(t, vision_levels):
    """匹配录制相对时间；无0.3秒内样本时返回None，与中音区区分。"""
    nearest = None
    best_dt = 0.30

    for vt, vl in vision_levels:
        dt = abs(vt - t)
        if dt < best_dt:
            best_dt = dt
            nearest = vl

    return None if nearest is None else 12 * nearest


def compose_events(
    csv_path,
    profile,
    use_posture=False,
    vision_levels=None,
):

    """
    下挥落音模式: 每次挥动按时刻变成音符,
    力度决定音的分量(单音/双音/重和弦)。
    use_posture: 挥动前俯仰角(会话内相对)
    决定该记音的八度(试验)。
    vision_levels: [(相对CSV首样本的秒数, -1/0/+1)]；与姿态模式互斥。
    None不启用视觉，空列表表示视觉不可用，按默认音区演奏。
    返回 (score, {"counts": 轻中重次数, "posture": 音区次数或None,
                    "vision": 匹配统计或None, "register_mode": 模式})
    或 (None, 原因)。默认不启用音区控制。
    """

    if use_posture and vision_levels is not None:
        raise ValueError("姿态和视觉音区模式不能同时启用")

    if vision_levels is not None:
        for t, level in vision_levels:
            if not math.isfinite(t) or level not in (-1, 0, 1):
                raise ValueError("视觉样本需为有限秒数和-1/0/+1音区")

    rows = load_rows(csv_path)

    if len(rows) < 50:
        return None, "数据不足"

    uniform = resample(rows)

    events = extract_swing_events(uniform)

    if len(events) < 3:
        return None, f"只检测到{len(events)}次挥动"

    weights = sorted(m for _, m, _ in events)

    p50 = weights[len(weights) // 2]

    p80 = weights[
        int(len(weights) * 0.8)
    ]

    # 姿态音区: 每次挥动前0.3秒窗的俯仰角,
    # 会话内三等分 -> 低/中/高八度
    register_of = {}

    posture_counts = None
    vision_counts = None

    if use_posture and len(events) >= 6:

        pitches = []

        for t, m, idx in events:

            lo = max(0, idx - 45)
            hi = max(0, idx - 15)

            if hi <= lo:
                hi = min(len(uniform), idx)

            seg = uniform[lo:hi]

            if not seg:
                seg = [uniform[idx]]

            pitches.append(
                statistics.fmean(
                    _pitch(v[0], v[1], v[2])
                    for v in seg
                )
            )

        order = sorted(
            range(len(events)),
            key=lambda k: pitches[k],
        )

        n = len(order)

        for rank, k in enumerate(order):

            if rank < n / 3:
                register_of[k] = -12

            elif rank >= 2 * n / 3:
                register_of[k] = +12

            else:
                register_of[k] = 0

        posture_counts = {
            "高": sum(
                1 for v in register_of.values()
                if v > 0
            ),
            "中": sum(
                1 for v in register_of.values()
                if v == 0
            ),
            "低": sum(
                1 for v in register_of.values()
                if v < 0
            ),
        }

    if vision_levels is not None:
        vision_counts = {"低": 0, "中": 0, "高": 0, "未匹配": 0}
        for i, (t, _m, _idx) in enumerate(events):
            octave = _vision_octave(t, vision_levels)
            if octave is None:
                vision_counts["未匹配"] += 1
                octave = 0
            else:
                vision_counts[{-12: "低", 0: "中", 12: "高"}[octave]] += 1
            register_of[i] = octave

    level, energy_n = energy_level(profile)

    bpm = resolve_bpm(profile)

    bar_len = 240.0 / bpm

    duration = profile["duration_s"]

    bars = max(
        8,
        min(24, int(duration / bar_len) + 1),
    )

    prog = PROGRESSIONS[level]

    chords = []

    for bar in range(bars):

        name, _ = prog[bar % len(prog)]

        chords.append(
            {"bar": bar, "symbol": name}
        )

    melody = []

    counts = {"轻": 0, "中": 0, "重": 0}

    for i, (t, m, _idx) in enumerate(events):

        bar = int(t / bar_len)

        if bar >= bars:
            bar = bars - 1

        start = int(
            round(
                (t - bar * bar_len)
                / (bar_len / 16)
            )
        )

        start = max(0, min(15, start))

        # 时值不得溢出小节
        if start + 4 > 16:
            start = min(start, 12)

        chord = prog[bar % len(prog)][1]

        reg = register_of.get(i, 0)

        if m >= p80:

            counts["重"] += 1

            group = [
                _wrap(chord[0] + reg),
                _wrap(chord[1] + reg),
                _wrap(chord[2] + reg),
                _wrap(chord[1] + 12 + reg),
            ]

            vel = int(92 + energy_n * 18)

            dur = 4

        elif m >= p50:

            counts["中"] += 1

            group = [
                _wrap(chord[i % 3] + reg),
                _wrap(chord[(i + 2) % 3] + reg),
            ]

            vel = int(72 + energy_n * 18)

            dur = 2

        else:

            counts["轻"] += 1

            group = [
                _wrap(chord[i % 3] + 12 + reg)
            ]

            vel = int(52 + energy_n * 16)

            dur = 2

        for note in group:

            melody.append(
                {
                    "bar": bar,
                    "note": note,
                    "start": start,
                    "dur": dur,
                    "velocity": min(
                        115,
                        vel,
                    ),
                }
            )

    return {
        "bpm": bpm,
        "key": "C",
        "bars": bars,
        "chords": chords,
        "melody": melody,
        "title": "下挥落音",
        "description": (
            f"你的{sum(counts.values())}次挥动逐一落音: "
            f"轻{counts['轻']}、中{counts['中']}、"
            f"重{counts['重']}。"
        ),
    }, {
        "counts": counts,
        "posture": posture_counts,
        "vision": vision_counts,
        "register_mode": (
            "vision" if vision_levels is not None
            else "posture" if use_posture else "none"
        ),
    }
