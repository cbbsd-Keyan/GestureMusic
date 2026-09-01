import argparse
import json
import sys
import time
from pathlib import Path


FEATURES_DIR = (
    Path(__file__)
    .resolve()
    .parent.parent
    / "features"
)


def parse_source_from_name(score_path):

    """
    pV2_s02_vigorous_002_1.json
      -> (s02, data/batch_2026_09_w1/s02/vigorous_002.csv)
    解析失败返回 None
    """

    stem = Path(score_path).stem

    parts = stem.split("_")

    if len(parts) < 4:
        return None

    subject = parts[1]

    csv_stem = "_".join(parts[2:-1])

    csv_path = (
        Path(__file__)
        .resolve()
        .parent.parent.parent
        / "data"
        / "batch_2026_09_w1"
        / subject
        / f"{csv_stem}.csv"
    )

    if not csv_path.exists():
        return None

    return subject, csv_path


def energy_from_data(subject, csv_path):

    """
    个人归一化: 本段gyro_rms / 本人全部段最大gyro_rms
    """

    sys.path.insert(0, str(FEATURES_DIR))

    from profile import analyze

    r = analyze(csv_path)

    if "error" in r:
        return None, r

    subject_dir = csv_path.parent

    values = []

    for p in sorted(subject_dir.glob("*.csv")):

        other = analyze(p)

        if "error" not in other:
            values.append(other["gyro_rms"])

    if not values:
        return None, r

    energy = max(
        0.0,
        min(1.0, r["gyro_rms"] / max(values)),
    )

    return energy, r


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "score",
        help="乐谱 JSON 文件",
    )

    parser.add_argument(
        "--device",
        type=int,
        required=True,
        help="MIDI 输出设备 ID",
    )

    parser.add_argument(
        "--energy",
        type=float,
        default=None,
        help="手动指定能量0~1（优先级最高）",
    )

    parser.add_argument(
        "--melody-prog",
        type=int,
        default=None,
        help="旋律音色 GM 编号（默认钢琴0）",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印配器方案不播放",
    )

    args = parser.parse_args()

    with open(args.score, encoding="utf-8") as f:
        score = json.load(f)

    from arrangement import (
        build_arranged_events,
        energy_tier,
        total_duration,
    )

    # -------------------------
    # 能量来源: 手动 > 文件名回溯
    # -------------------------

    source = "手动"

    energy = args.energy

    detail = ""

    if energy is None:

        parsed = parse_source_from_name(args.score)

        if parsed is not None:

            subject, csv_path = parsed

            energy, r = energy_from_data(
                subject,
                csv_path,
            )

            if energy is not None:

                source = (
                    f"{subject}个人归一化"
                    f"(gyro_rms={r['gyro_rms']:.2f})"
                )

        if energy is None:

            energy = 0.5

            source = "默认中档"

    tier = energy_tier(energy)

    events, _ = build_arranged_events(
        score,
        energy,
    )

    counts = {}

    for _, etype, _, _ in events:

        key = etype.split("_")[0]

        counts[key] = counts.get(key, 0) + 1

    duration = total_duration(score)

    tier_desc = {
        "calm": "无鼓 | 根音长音 | 轻",
        "neutral": "轻鼓(hihat+kick) | 每拍贝斯 | 中",
        "intense": "全套鼓(kick/snare/hihat) | 八分贝斯 | 强重音",
    }

    print(
        f"[配器] {tier}档 | energy={energy:.2f} "
        f"| 来源:{source}"
    )

    print(f"       {tier_desc[tier]}")

    print(
        f"[事件] 旋律{counts.get('melody', 0) // 2}音 "
        f"和弦{counts.get('chord', 0) // 2}拍 "
        f"贝斯{counts.get('bass', 0) // 2}音 "
        f"鼓{counts.get('drum', 0)}击 "
        f"| 时长{duration:.0f}s"
    )

    if args.dry_run:
        return

    # -------------------------
    # 播放
    # -------------------------

    from midi_engine import MidiEngine

    engine = MidiEngine(device_id=args.device)

    if args.melody_prog is not None:

        engine.player.set_instrument(
            args.melody_prog,
            engine.MELODY_CHANNEL,
        )

    print(f"[播放] MIDI设备 {args.device}")

    start_clock = time.perf_counter()

    try:

        for event_time, etype, data, vel in events:

            while True:

                now = (
                    time.perf_counter() - start_clock
                )

                wait = event_time - now

                if wait <= 0:
                    break

                time.sleep(min(wait, 0.01))

            if etype == "melody_on":
                engine.play_melody(data, vel)

            elif etype == "melody_off":
                engine.stop_melody(data)

            elif etype == "chord_on":
                engine.play_chord(data, vel)

            elif etype == "chord_off":
                engine.stop_chord(data)

            elif etype == "bass_on":
                engine.play_bass(data, vel)

            elif etype == "bass_off":
                engine.stop_bass(data)

            elif etype == "drum":
                engine.play_drum(data, vel)

    finally:

        engine.close()

    print("[播放完成]")


if __name__ == "__main__":

    main()
