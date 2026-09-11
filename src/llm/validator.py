NOTE_MIN = 36
NOTE_MAX = 84

CHORD_PCS = {
    "C": (0, 4, 7),
    "Dm": (2, 5, 9),
    "Em": (4, 7, 11),
    "E": (4, 8, 11),
    "F": (5, 9, 0),
    "G": (7, 11, 2),
    "Am": (9, 0, 4),
}


def _snap_note_to_chord(note, pcs):

    """
    吸附到最近和弦音(半音距离最近, 平局向下)。
    吸附后越界则放弃。
    """

    for delta in (0, -1, 1, -2, 2, -3, 3, -4, 4):

        snapped = note + delta

        if snapped % 12 in pcs and NOTE_MIN <= snapped <= NOTE_MAX:

            return snapped

    return note


def validate_and_fix(score, snap_harmony=True):

    """
    校验并自动修复LLM乐谱。
    snap_harmony: 强拍/长音的非和弦音吸附到最近和弦音
    (默认开启, --no-snap-harmony 可关)。
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

    # -------------------------
    # 和声吸附(试验开关)
    # -------------------------

    if snap_harmony and score["chords"]:

        chord_by_bar = {}

        for c in score["chords"]:

            try:

                chord_by_bar[int(c["bar"])] = str(
                    c.get("symbol", "")
                )

            except (
                KeyError,
                ValueError,
                TypeError,
            ):
                continue

        snap_count = 0

        for m in score["melody"]:

            pcs = CHORD_PCS.get(
                chord_by_bar.get(m["bar"])
            )

            if pcs is None:
                continue

            if m["start"] in (0, 8) or m["dur"] >= 4:

                if m["note"] % 12 not in pcs:

                    snapped = _snap_note_to_chord(
                        m["note"],
                        pcs,
                    )

                    if snapped != m["note"]:

                        m["note"] = snapped

                        snap_count += 1

        if snap_count:

            fixes.append(
                f"和弦音吸附{snap_count}处"
            )

    return score, fixes, fatals
