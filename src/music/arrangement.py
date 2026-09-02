import math


# =========================
# 和弦：低音区 + 声部连接
# =========================

TRIAD_PCS = {
    "C": (0, 4, 7),
    "Dm": (2, 5, 9),
    "Em": (4, 7, 11),
    "E": (4, 8, 11),
    "F": (5, 9, 0),
    "G": (7, 11, 2),
    "Am": (9, 0, 4),
}

ROOTS = {
    "C": 36,
    "Dm": 38,
    "Em": 40,
    "E": 40,
    "F": 41,
    "G": 43,
    "Am": 45,
}

VOICE_LO = 48
VOICE_HI = 67


def voice_chord(pcs, prev_voicing):

    """
    为三和弦选最近转位（最小声部移动），
    音区限制在 48~67，避免与旋律打架。
    """

    candidates = []

    for a in range(VOICE_LO, VOICE_HI + 1):

        if a % 12 != pcs[0]:
            continue

        for b in range(a + 1, VOICE_HI + 1):

            if b % 12 != pcs[1]:
                continue

            for c in range(b + 1, VOICE_HI + 1):

                if c % 12 != pcs[2]:
                    continue

                candidates.append((a, b, c))

    if not candidates:
        return list(pcs)

    if prev_voicing is None:

        return list(
            min(
                candidates,
                key=lambda v: sum(v),
            )
        )

    best = min(
        candidates,
        key=lambda v: sum(
            abs(x - y)
            for x, y in zip(v, prev_voicing)
        ),
    )

    return list(best)


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
# 能量 -> 感知强度映射
# 前三杠杆: 速度/音区/力度
# =========================

def tempo_factor(energy, base_bpm):

    """
    energy 0->0.85x, 1->1.2x
    快曲封顶防失控
    """

    f = 0.85 + 0.35 * energy

    if base_bpm >= 130:
        f = min(f, 1.08)

    elif base_bpm >= 110:
        f = min(f, 1.12)

    return f


def octave_shift(energy):

    """
    高能量旋律上移八度(更亮更激动)
    """

    if energy > 0.7:
        return 12

    return 0


def velocity_scale(energy):

    return 0.85 + 0.30 * energy


# =========================
# 鼓型（小节内十六分格位）
# =========================

DRUMS = {
    "calm": [],
    "neutral": [
        (0, 36),
        (0, 42),
        (4, 42),
        (8, 36),
        (8, 42),
        (12, 42),
    ],
    "intense": [
        (0, 36),
        (0, 42),
        (2, 42),
        (4, 38),
        (4, 42),
        (6, 42),
        (8, 36),
        (8, 42),
        (10, 36),
        (10, 42),
        (12, 38),
        (12, 42),
        (14, 42),
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

def build_arranged_events(
    score,
    energy,
    legato=False,
):

    """
    乐谱JSON + energy -> 统一事件流。
    energy 驱动: 播放速度 / 旋律音区 / 整体力度 / 配器密度
    legato: 旋律连音填充(延长到下一音)，默认关闭
    事件: (时间秒, 类型, 数据, 力度)
    """

    base_bpm = score["bpm"]
    bars = score["bars"]

    bpm = base_bpm * tempo_factor(energy, base_bpm)

    grid = 60.0 / bpm / 4.0

    tier = energy_tier(energy)

    vscale = velocity_scale(energy)

    octave = octave_shift(energy)

    events = []

    def beat_time(bar, pos):

        return (bar * 16 + pos) * grid

    # -------------------------
    # 旋律（音区偏移 + 强拍重音 + 力度缩放 + 连音填充）
    # -------------------------

    melody = sorted(
        score.get("melody", []),
        key=lambda x: (x["bar"], x["start"]),
    )

    for idx, item in enumerate(melody):

        bar = item["bar"]
        start = item["start"]
        dur = item["dur"]
        note = item["note"] + octave

        if note > 96:
            note -= 12

        vel = item.get("velocity", 80)

        if start in (0, 8):
            vel = vel + ACCENT[tier]

        vel = min(
            120,
            int(vel * vscale),
        )

        t0 = beat_time(bar, start)

        # 连音填充(可选)：延长到下一个旋律音出现，
        # 消灭乐句内空洞（封顶8格）
        end_pos = bar * 16 + start + dur

        if legato and idx + 1 < len(melody):

            nxt = melody[idx + 1]

            next_pos = (
                nxt["bar"] * 16 + nxt["start"]
            )

            if next_pos > end_pos:

                end_pos = min(
                    next_pos,
                    end_pos + 8,
                )

        t1 = beat_time(
            end_pos // 16,
            end_pos % 16,
        )

        events.append((t0, "melody_on", note, vel))
        events.append((t1, "melody_off", note, 0))

    # -------------------------
    # 和弦（持续铺底）
    # -------------------------

    chords = score.get("chords", [])

    chord_vel = min(
        110,
        int(CHORD_VELOCITY[tier] * vscale),
    )

    prev_voicing = None

    for i, item in enumerate(chords):

        symbol = item["symbol"]

        pcs = TRIAD_PCS.get(symbol)

        if pcs is None:
            continue

        notes = voice_chord(pcs, prev_voicing)

        prev_voicing = notes

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

    bass_vel = min(
        110,
        int(78 * vscale),
    )

    for item in chords:

        symbol = item["symbol"]

        root = ROOTS.get(symbol)

        if root is None:
            continue

        fifth = root + 7

        for pos, dur in BASS[tier]:

            # 第三拍用五度增加行进感
            note = fifth if pos == 8 else root

            t0 = beat_time(item["bar"], pos)
            t1 = t0 + dur * grid

            events.append((t0, "bass_on", note, bass_vel))
            events.append((t1, "bass_off", note, 0))

    # -------------------------
    # 鼓
    # -------------------------

    drum_vel = min(
        115,
        int(100 * vscale),
    )

    for bar in range(bars):

        for pos, drum_note in DRUMS[tier]:

            events.append(
                (beat_time(bar, pos), "drum", drum_note, drum_vel)
            )

    events.sort(key=lambda x: x[0])

    return events, tier, bpm


def total_duration(score, energy):

    bpm = score["bpm"] * tempo_factor(
        energy,
        score["bpm"],
    )

    grid = 60.0 / bpm / 4.0

    return score["bars"] * 16 * grid + 1.0
