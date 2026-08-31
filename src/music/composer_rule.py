import random


# =========================
# 和弦模板库
# ============================================================
# TODO(乐理): 模板为常见流行进行的草案，
# 需要人工审校替换。每行是一个循环单元。
# ============================================================

PROGRESSIONS = {
    "calm": [
        ("C", [60, 64, 67]),
        ("Am", [57, 60, 64]),
        ("F", [53, 57, 60]),
        ("G", [55, 59, 62]),
    ],
    "neutral": [
        ("Am", [57, 60, 64]),
        ("F", [53, 57, 60]),
        ("C", [60, 64, 67]),
        ("G", [55, 59, 62]),
    ],
    "intense": [
        ("Em", [52, 55, 59]),
        ("C", [48, 52, 55]),
        ("G", [55, 59, 62]),
        ("D", [50, 54, 57]),
    ],
}

# 每档能量对应的每小节旋律音符数
DENSITY = {
    "calm": 2,
    "neutral": 4,
    "intense": 8,
}

NOTE_MIN = 36
NOTE_MAX = 84


# =========================
# 工具
# =========================

def energy_level(profile):

    e = profile["energy"]

    if e.get("normalized") is not None:
        n = e["normalized"]
    else:
        n = max(
            0.0,
            min(1.0, (e["gyro_rms"] - 1.0) / 5.0),
        )

    if n < 0.33:
        return "calm", n

    if n < 0.7:
        return "neutral", n

    return "intense", n


def resolve_bpm(profile):

    tempo = profile["tempo"]

    if (
        tempo["bpm"] is not None
        and tempo["confidence"] != "low"
    ):
        return int(round(tempo["bpm"]))

    return 90


def resolve_register(profile):

    """
    姿态 -> 旋律音区: -1 低 / 0 中 / +1 高
    """

    p = profile["posture"]

    if not p.get("available"):
        return 0

    roll = p.get("roll_median")

    if roll is None:
        return 0

    if roll < -15:
        return -1

    if roll > 15:
        return 1

    return 0


def resolve_bars(profile):

    d = profile["duration_s"]

    bars = int(d / 1.5)

    return max(8, min(32, bars))


# =========================
# 主入口
# =========================

def compose(profile, seed=None):

    """
    画像JSON -> 乐谱JSON (SCORE_SCHEMA_DRAFT 同构)。
    确定性输出: 相同profile+seed产生相同乐谱。
    """

    level, energy_n = energy_level(profile)

    bpm = resolve_bpm(profile)

    register = resolve_register(profile)

    bars = resolve_bars(profile)

    prog = PROGRESSIONS[level]

    notes_per_bar = DENSITY[level]

    rng = random.Random(
        seed
        if seed is not None
        else hash(
            str(profile)
        )
        & 0xFFFFFFFF
    )

    chords = []

    melody = []

    base_velocity = int(55 + energy_n * 50)

    for bar in range(bars):

        name, chord_notes = prog[
            bar % len(prog)
        ]

        chords.append(
            {
                "bar": bar,
                "symbol": name,
            }
        )

        slots = sorted(
            rng.sample(
                range(0, 16, 2),
                notes_per_bar,
            )
        )

        for i, start in enumerate(slots):

            tone = chord_notes[
                rng.randrange(
                    len(chord_notes)
                )
            ]

            octave = 12 * register

            note = tone + octave

            if note < NOTE_MIN:
                note += 12

            if note > NOTE_MAX:
                note -= 12

            dur = (
                4
                if level == "calm"
                else 2
            )

            melody.append(
                {
                    "bar": bar,
                    "note": note,
                    "start": start,
                    "dur": dur,
                    "velocity": max(
                        30,
                        min(
                            110,
                            base_velocity
                            + rng.randint(-8, 8),
                        ),
                    ),
                }
            )

    level_cn = {
        "calm": "舒缓",
        "neutral": "平稳",
        "intense": "激烈",
    }[level]

    return {
        "bpm": bpm,
        "key": "C",
        "bars": bars,
        "chords": chords,
        "melody": melody,
        "title": f"{level_cn}的挥动",
        "description": (
            f"基于{profile['duration_s']:.0f}秒动作生成:"
            f"能量{energy_n:.2f},"
            f"节奏{bpm}BPM,"
            f"音区{'低' if register<0 else '高' if register>0 else '中'}。"
        ),
    }


def validate_score(score):

    """
    自检: 音域与网格约束。
    返回错误列表(空=合法)。
    """

    errors = []

    for m in score["melody"]:

        if not (
            NOTE_MIN
            <= m["note"]
            <= NOTE_MAX
        ):

            errors.append(
                f"音域越界: {m}"
            )

        if m["start"] + m["dur"] > 16:

            errors.append(
                f"小节越界: {m}"
            )

    return errors


if __name__ == "__main__":

    import json
    import sys

    # Windows重定向到文件时默认GBK，强制UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2:

        print(
            "用法: composer_rule.py <画像.json>"
        )

        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:

        profile = json.load(f)

    score = compose(profile, seed=42)

    errors = validate_score(score)

    print(
        json.dumps(
            score,
            ensure_ascii=False,
            indent=2,
        )
    )

    if errors:

        print("校验失败:", errors)

        sys.exit(1)

    print("校验通过", file=sys.stderr)
