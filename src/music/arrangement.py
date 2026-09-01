import math


# =========================
# 和弦根音（低音区）
# =========================

ROOTS = {
    "C": 36,
    "Dm": 38,
    "Em": 40,
    "F": 41,
    "G": 43,
    "Am": 45,
}

CHORD_NOTES = {
    "C": [60, 64, 67],
    "Dm": [62, 65, 69],
    "Em": [64, 67, 71],
    "F": [65, 69, 72],
    "G": [67, 71, 74],
    "Am": [69, 72, 76],
}


# =========================
# 能量分档
# =========================

def energy_tier(energy):

    """
    energy: 0~1
    返回 calm / neutral / intense
    """

    if energy < 0.33:
        return "calm"

    if energy < 0.7:
        return "neutral"

    return "intense"


# =========================
# 鼓型（小节内十六分格位）
# =========================

DRUMS = {
    "calm": [],
    "neutral": [
        (0, 36),
        (0, 42),
        (8, 36),
        (8, 42),
    ],
    "intense": [
        (0, 36),
        (0, 42),
        (4, 38),
        (4, 42),
        (8, 36),
        (8, 36),
        (8, 42),
        (12, 38),
        (12, 42),
    ],
}

# 贝斯音符格位与时长（十六分）
BASS = {
    "calm": [(0, 16)],
    "neutral": [
        (0, 4),
        (4, 4),
        (8, 4),
        (12, 4),
    ],
    "intense": [
        (0, 2),
        (2, 2),
        (4, 2),
        (6, 2),
        (8, 2),
        (10, 2),
        (12, 2),
        (14, 2),
    ],
}

CHORD_VELOCITY = {
    "calm": 50,
    "neutral": 60,
    "intense": 72,
}

ACCENT = {
    "calm": 0,
    "neutral": 8,
    "intense": 18,
}


# =========================
# 事件构建
# =========================

def build_arranged_events(score, energy):

    """
    乐谱JSON + energy -> 统一事件流。
    事件: (时间秒, 类型, 数据, 力度)
    类型命名保证同刻 off 排在 on 前。
    """

    bpm = score["bpm"]
    bars = score["bars"]

    grid = 60.0 / bpm / 4.0

    tier = energy_tier(energy)

    events = []

    def beat_time(bar, pos):

        return (bar * 16 + pos) * grid

    # -------------------------
    # 旋律（含强拍重音）
    # -------------------------

    for item in score.get("melody", []):

        bar = item["bar"]
        start = item["start"]
        dur = item["dur"]
        note = item["note"]

        vel = item.get("velocity", 80)

        if start in (0, 8):
            vel = min(110, vel + ACCENT[tier])

        t0 = beat_time(bar, start)
        t1 = t0 + dur * grid

        events.append((t0, "melody_on", note, vel))
        events.append((t1, "melody_off", note, 0))

    # -------------------------
    # 和弦（持续铺底）
    # -------------------------

    chords = score.get("chords", [])

    chord_vel = CHORD_VELOCITY[tier]

    for i, item in enumerate(chords):

        symbol = item["symbol"]

        notes = CHORD_NOTES.get(symbol)

        if notes is None:
            continue

        bar = item["bar"]

        next_bar = (
            chords[i + 1]["bar"]
            if i + 1 < len(chords)
            else bars
        )

        t0 = beat_time(bar, 0)
        t1 = beat_time(next_bar, 0)

        events.append((t0, "chord_on", notes, chord_vel))
        events.append((t1, "chord_off", notes, 0))

    # -------------------------
    # 贝斯（根音律动）
    # -------------------------

    for item in chords:

        symbol = item["symbol"]

        root = ROOTS.get(symbol)

        if root is None:
            continue

        for pos, dur in BASS[tier]:

            t0 = beat_time(item["bar"], pos)
            t1 = t0 + dur * grid

            events.append((t0, "bass_on", root, 78))
            events.append((t1, "bass_off", root, 0))

    # -------------------------
    # 鼓
    # -------------------------

    for bar in range(bars):

        for pos, drum_note in DRUMS[tier]:

            events.append(
                (beat_time(bar, pos), "drum", drum_note, 100)
            )

    events.sort(key=lambda x: x[0])

    return events, tier


def total_duration(score):

    grid = 60.0 / score["bpm"] / 4.0

    return score["bars"] * 16 * grid + 1.0
