import statistics

from profile import load_rows, resample

from composer_rule import (
    PROGRESSIONS,
    energy_level,
    resolve_bpm,
)


NOTE_MIN = 48
NOTE_MAX = 84


def extract_swing_events(uniform, hz=100.0):

    """
    从重采样序列提取每次挥动的(时刻, 力度)。
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
                (i / hz, sm[i])
            )

            last = i

    return events


def _wrap(note):

    while note < NOTE_MIN:
        note += 12

    while note > NOTE_MAX:
        note -= 12

    return note


def compose_events(csv_path, profile):

    """
    下挥落音模式: 每次挥动按时刻变成音符,
    力度决定音的分量(单音/双音/重和弦)。
    返回 (score, 统计) 或 (None, 原因)。
    """

    rows = load_rows(csv_path)

    if len(rows) < 50:
        return None, "数据不足"

    uniform = resample(rows)

    events = extract_swing_events(uniform)

    if len(events) < 3:
        return None, f"只检测到{len(events)}次挥动"

    weights = sorted(m for _, m in events)

    p50 = weights[len(weights) // 2]

    p80 = weights[
        int(len(weights) * 0.8)
    ]

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

    for i, (t, m) in enumerate(events):

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

        if m >= p80:

            counts["重"] += 1

            group = [
                _wrap(chord[0]),
                _wrap(chord[1]),
                _wrap(chord[2]),
                _wrap(chord[1] + 12),
            ]

            vel = int(92 + energy_n * 18)

            dur = 4

        elif m >= p50:

            counts["中"] += 1

            group = [
                _wrap(chord[i % 3]),
                _wrap(chord[(i + 2) % 3]),
            ]

            vel = int(72 + energy_n * 18)

            dur = 2

        else:

            counts["轻"] += 1

            group = [_wrap(chord[i % 3] + 12)]

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
    }, counts
