NOTE_MIN = 36
NOTE_MAX = 84


def validate_and_fix(score):

    """
    校验并自动修复LLM乐谱。
    返回 (score, fixes列表, fatal错误列表)。
    fatal非空时调用方应回退规则作曲。
    """

    fixes = []
    fatals = []

    if not isinstance(score, dict):

        return score, fixes, ["乐谱不是JSON对象"]

    # ---------- bpm ----------

    bpm = score.get("bpm")

    if not isinstance(bpm, (int, float)):

        score["bpm"] = 90
        fixes.append("bpm缺失，置90")

    else:

        bpm = int(round(bpm))

        if not 30 <= bpm <= 220:

            bpm = max(30, min(220, bpm))
            fixes.append(f"bpm越界，钳到{bpm}")

        score["bpm"] = bpm

    # ---------- bars ----------

    bars = score.get("bars")

    if not isinstance(bars, int) or bars < 4:

        bars = len(score.get("chords", [])) or 16
        fixes.append(f"bars非法，取{bars}")

    score["bars"] = min(bars, 64)

    # ---------- melody ----------

    melody = score.get("melody")

    if not isinstance(melody, list) or not melody:

        return score, fixes, ["melody为空"]

    cleaned = []

    for m in melody:

        try:

            note = int(m["note"])
            bar = int(m["bar"])
            start = int(m["start"])
            dur = int(m.get("dur", 2))
            vel = int(m.get("velocity", 70))

        except (KeyError, ValueError, TypeError):

            fixes.append(f"丢弃坏音符: {m}")
            continue

        if not 0 <= bar < score["bars"]:

            fixes.append(f"丢弃越界小节音符: {m}")
            continue

        if not NOTE_MIN <= note <= NOTE_MAX:

            note = max(
                NOTE_MIN,
                min(NOTE_MAX, note),
            )

            fixes.append(f"音高钳回{note}")

        if not 0 <= start <= 15:
            start = max(0, min(15, start))
            fixes.append(f"start钳到{start}")

        if not 1 <= dur <= 4:
            dur = max(1, min(4, dur))
            fixes.append(f"dur钳到{dur}")

        if start + dur > 16:
            dur = 16 - start
            fixes.append(f"时值截短到{dur}")

        if not 30 <= vel <= 110:

            vel = max(30, min(110, vel))

            fixes.append(f"力度钳到{vel}")

        cleaned.append(
            {
                "bar": bar,
                "note": note,
                "start": start,
                "dur": dur,
                "velocity": vel,
            }
        )

    if not cleaned:

        return score, fixes, ["有效音符为0"]

    score["melody"] = cleaned

    score.setdefault("title", "未命名")
    score.setdefault("description", "")
    score.setdefault("key", "C")
    score.setdefault("chords", [])

    return score, fixes, fatals
