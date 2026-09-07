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

VOICE_LO = 43
VOICE_HI = 62


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

# 伴奏pattern: (格位, 时值格)
# calm=每拍单音琶音 neutral=八分琶音
# intense=强拍重击+抢拍
ACCOMP_PATTERN = {
    "calm": [(0, 4), (4, 4), (8, 4), (12, 4)],
    "neutral": [
        (0, 2), (2, 2), (4, 2), (6, 2),
        (8, 2), (10, 2), (12, 2), (14, 2),
    ],
    "intense": [(0, 2), (8, 2), (14, 2)],
}

# 琶音音序(在voicing三音上的索引)
ARP_ORDER = [0, 1, 2, 1]

# 力度弧线锚点: (曲子位置, 乘数)
ARC_ANCHORS = [
    (0.0, 0.90),
    (0.15, 0.95),
    (0.60, 1.05),
    (1.0, 0.85),
]


def arc_factor(pos):

    """
    曲子位置(0~1) -> 力度乘数。
    先渐强到黄金点，再收束。
    """

    pos = max(0.0, min(1.0, pos))

    for (x0, y0), (x1, y1) in zip(
        ARC_ANCHORS,
        ARC_ANCHORS[1:],
    ):

        if pos <= x1:

            if x1 <= x0:
                return y1

            a = (pos - x0) / (x1 - x0)

            return y0 + a * (y1 - y0)

    return ARC_ANCHORS[-1][1]


# =========================
# 事件构建
# =========================

def build_arranged_events(
    score,
    energy,
    legato=False,
    plain=False,
    avoid=True,
):

    """
    乐谱JSON + energy -> 统一事件流。
    energy 驱动: 播放速度 / 旋律音区 / 整体力度 / 配器密度
    legato: 旋律连音填充(默认关)
    plain: 旧版渲染(长音和弦/无引子尾声/无力度弧线)
    avoid: 同刻碰撞规避(≤2半音跳过/八度软化/其余保留)
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

    # 引子: 第一小节旋律静音(plain模式除外)
    if not plain:
        melody = [
            x for x in melody if x["bar"] > 0
        ]

    total_pos = max(1, bars * 16)

    # 旋律占位: (起格, 止格, 音高) 与 每小节起音位置
    melody_spans = []

    onsets_by_bar = {}

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

        vel = int(vel * vscale)

        # 力度弧线 + 后半曲抬升
        if not plain:

            pos = (
                bar * 16 + start
            ) / total_pos

            vel = int(vel * arc_factor(pos))

            if bar >= bars / 2:
                vel = vel + 6

        vel = min(120, vel)

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

        melody_spans.append(
            (bar * 16 + start, end_pos, note)
        )

        onsets_by_bar.setdefault(
            bar,
            [],
        ).append(start)

        events.append((t0, "melody_on", note, vel))
        events.append((t1, "melody_off", note, 0))

    # -------------------------
    # 碰撞判定(只作用于同刻)
    # -------------------------

    def collision_adjust(pitch, t_pos):

        """
        返回 (是否保留, 力度乘数)。
        ≤2半音=糊刺 跳过；八度=厚 软化；其余=合法对位 保留。
        """

        for s, e, m_note in melody_spans:

            if s <= t_pos < e:

                d = abs(pitch - m_note)

                if d <= 2:
                    return False, 1.0

                if d == 12:
                    return True, 0.7

        return True, 1.0

    # -------------------------
    # 和弦（持续铺底）
    # -------------------------

    chords = score.get("chords", [])

    chord_vel = min(
        110,
        int(CHORD_VELOCITY[tier] * vscale),
    )

    prev_voicing = None

    last_symbol = None

    for i, item in enumerate(chords):

        symbol = item["symbol"]

        pcs = TRIAD_PCS.get(symbol)

        if pcs is None:
            continue

        notes = voice_chord(pcs, prev_voicing)

        prev_voicing = notes

        last_symbol = symbol

        bar = item["bar"]

        next_bar = (
            chords[i + 1]["bar"]
            if i + 1 < len(chords)
            else bars
        )

        if plain:

            # 旧版: 整段长音
            t0 = beat_time(bar, 0)
            t1 = beat_time(next_bar, 0)

            events.append((t0, "chord_on", notes, chord_vel))
            events.append((t1, "chord_off", notes, 0))

            continue

        # 新版: 逐小节伴奏pattern
        for b in range(bar, next_bar):

            bpos = (
                b * 16 + 8
            ) / total_pos

            arc = 1 + (
                arc_factor(bpos) - 1
            ) * 0.5

            base_vel = min(
                110,
                int(chord_vel * arc),
            )

            # 密度自适应: 旋律密的小节伴奏减半
            pattern = ACCOMP_PATTERN[tier]

            mel_count = len(
                onsets_by_bar.get(b, [])
            )

            if not plain and mel_count >= 5:

                pattern = [
                    p
                    for p in pattern
                    if p[0] in (0, 8)
                ]

            # 抢拍让路: 旋律在12~15格有音则去掉14格
            if (
                not plain
                and tier == "intense"
                and any(
                    12 <= p <= 15
                    for p in onsets_by_bar.get(b, [])
                )
            ):

                pattern = [
                    p
                    for p in pattern
                    if p[0] != 14
                ]

            if tier == "intense":

                # 强拍重击(逐音过碰撞规则)
                for pos, dur in pattern:

                    v = base_vel if pos != 14 else int(base_vel * 0.8)

                    t_pos = b * 16 + pos

                    kept = []

                    soft = False

                    for n in notes:

                        if avoid and not plain:

                            keep, scale = collision_adjust(
                                n,
                                t_pos,
                            )

                            if not keep:
                                continue

                            if scale < 1.0:
                                soft = True

                        kept.append(n)

                    if not kept:
                        continue

                    if soft:
                        v = int(v * 0.7)

                    t0 = beat_time(b, pos)
                    t1 = t0 + dur * grid

                    events.append((t0, "chord_on", kept, v))
                    events.append((t1, "chord_off", kept, 0))

            else:

                # 流动琶音(逐音过碰撞规则)
                for k, (pos, dur) in enumerate(pattern):

                    note = notes[
                        ARP_ORDER[
                            k % len(ARP_ORDER)
                        ]
                    ]

                    v = int(base_vel * 0.85)

                    if avoid and not plain:

                        keep, scale = collision_adjust(
                            note,
                            b * 16 + pos,
                        )

                        if not keep:
                            continue

                        v = int(v * scale)

                    t0 = beat_time(b, pos)
                    t1 = t0 + dur * grid

                    events.append(
                        (t0, "chord_on", [note], v)
                    )
                    events.append(
                        (t1, "chord_off", [note], 0)
                    )

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

    # -------------------------
    # 尾声: 主和弦延长收束(plain除外)
    # -------------------------

    if not plain and last_symbol is not None:

        pcs = TRIAD_PCS.get(last_symbol)

        root = ROOTS.get(last_symbol)

        if pcs is not None and root is not None:

            final_voicing = voice_chord(
                pcs,
                prev_voicing,
            )

            t0 = beat_time(bars, 0)

            events.append(
                (
                    t0,
                    "chord_on",
                    final_voicing,
                    int(chord_vel * 0.9),
                )
            )

            events.append(
                (
                    t0 + 12 * grid,
                    "chord_off",
                    final_voicing,
                    0,
                )
            )

            events.append(
                (t0, "bass_on", root, int(bass_vel * 0.9))
            )

            events.append(
                (t0 + 16 * grid, "bass_off", root, 0)
            )

    events.sort(key=lambda x: x[0])

    return events, tier, bpm


def total_duration(score, energy, plain=False):

    bpm = score["bpm"] * tempo_factor(
        energy,
        score["bpm"],
    )

    grid = 60.0 / bpm / 4.0

    extra = 0 if plain else 16 * grid

    return score["bars"] * 16 * grid + extra + 1.0
