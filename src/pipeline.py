import argparse
import json
import sys
import time
import msvcrt
from pathlib import Path


# =========================
# 路径
# =========================

SRC_DIR = Path(__file__).resolve().parent
ROOT_DIR = SRC_DIR.parent

FEATURES_DIR = SRC_DIR / "features"
MUSIC_DIR = SRC_DIR / "music"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(FEATURES_DIR))
sys.path.insert(0, str(MUSIC_DIR))


# =========================
# 项目模块
# =========================

from input.udp_reader import UDPReader
from input.recorder import Recorder

from profile import analyze, build_profile_json
from composer_rule import compose
from arrangement import build_arranged_events
from midi_engine import MidiEngine


# =========================
# 配置
# =========================

UDP_PORT = 4210
MOUNT_VERSION = "ruler_v1"
RECORD_SECONDS = 15


# =========================
# baseline
# =========================

def load_anchor(subject_id):

    baseline_path = (
        ROOT_DIR
        / "data"
        / "batch_2026_09_w1"
        / subject_id
        / "baseline.json"
    )

    if not baseline_path.exists():

        print(
            f"[错误] 未找到校准文件:\n"
            f"{baseline_path}\n"
            f"请先完成 calibration。"
        )

        return None

    try:

        with open(
            baseline_path,
            "r",
            encoding="utf-8",
        ) as f:

            baseline = json.load(f)

        anchor = float(
            baseline["anchor_rms"]
        )

        if anchor <= 0:
            raise ValueError

        return anchor

    except (
        KeyError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):

        print(
            "[错误] baseline.json 中 "
            "anchor_rms 无效。"
        )

        return None


# =========================
# 实时录制
# =========================

def record_free(subject_id):

    data_dir = (
        ROOT_DIR
        / "data"
        / "batch_2026_09_w1"
    )

    reader = UDPReader(
        port=UDP_PORT
    )

    recorder = Recorder(
        out_dir=data_dir,
        subject_id=subject_id,
        mount_version=MOUNT_VERSION,
    )

    print()
    print("==============================")
    print(
        f"准备自由挥动 {RECORD_SECONDS} 秒"
    )
    print("按 R 开始")
    print("按 Q 退出")
    print("==============================")

    try:

        # -------------------------
        # 等待 R
        # -------------------------

        while True:

            if msvcrt.kbhit():

                key = (
                    msvcrt
                    .getwch()
                    .lower()
                )

                if key == "r":
                    break

                if key == "q":
                    return None

            # 清掉等待期间旧 UDP 包
            reader.read()

            time.sleep(0.001)

        print(
            f"[录制] 开始，请自由挥动 "
            f"{RECORD_SECONDS} 秒"
        )

        recorder.start()

        start = time.perf_counter()

        last_second = -1

        # -------------------------
        # 自动录 15 秒
        # -------------------------

        while True:

            elapsed = (
                time.perf_counter()
                - start
            )

            if elapsed >= RECORD_SECONDS:
                break

            line = reader.read()

            if line is not None:

                parts = line.split(",")

                if len(parts) == 7:

                    try:

                        values = [
                            float(x)
                            for x in parts
                        ]

                        recorder.feed(
                            values
                        )

                    except ValueError:
                        pass

            second = int(elapsed)

            if second != last_second:

                last_second = second

                print(
                    f"  ... "
                    f"{second + 1}/"
                    f"{RECORD_SECONDS}s"
                )

            time.sleep(0.001)

        # -------------------------
        # 保存
        # -------------------------

        n = recorder.stop()

        if n == 0:

            print(
                "[错误] 没有收到传感器数据。"
            )

            return None

        result = recorder.save(
            scene="free"
        )

        csv_path = Path(
            result["csv"]
        )

        print(
            f"[录制完成] "
            f"{n} 点"
        )

        print(
            f"[CSV] {csv_path}"
        )

        return csv_path

    finally:

        reader.close()


# =========================
# 特征 + energy
# =========================

def analyze_motion(
    csv_path,
    subject_id,
    anchor,
):

    result = analyze(
        csv_path
    )

    if "error" in result:

        print(
            f"[错误] 特征分析失败: "
            f"{result['error']}"
        )

        return None, None

    # -------------------------
    # gyro_rms / anchor
    # -------------------------

    energy = (
        result["gyro_rms"]
        / anchor
    )

    energy = max(
        0.0,
        min(
            1.0,
            energy,
        ),
    )

    # -------------------------
    # profile
    # -------------------------

    profile = build_profile_json(
        result,
        subject_id,
        MOUNT_VERSION,
    )

    # 明确覆盖 normalized
    profile["energy"]["normalized"] = (
        round(
            energy,
            3,
        )
    )

    print()
    print(
        f"[特征] gyro_rms="
        f"{result['gyro_rms']:.3f}"
    )

    print(
        f"[锚值] anchor_rms="
        f"{anchor:.3f}"
    )

    print(
        f"[能量] normalized="
        f"{energy:.3f}"
    )

    return profile, energy


# =========================
# MIDI 播放
# =========================

def play_score(
    score,
    energy,
    device_id,
):

    events, tier, play_bpm = (
        build_arranged_events(
            score,
            energy,
        )
    )

    print()
    print(
        f"[配器] "
        f"{tier} | "
        f"energy={energy:.2f}"
    )

    print(
        f"[速度] "
        f"{score['bpm']} "
        f"-> "
        f"{play_bpm:.0f} BPM"
    )

    print(
        f"[播放] "
        f"MIDI设备 {device_id}"
    )

    engine = MidiEngine(
        device_id=device_id
    )

    start_clock = (
        time.perf_counter()
    )

    try:

        for (
            event_time,
            etype,
            data,
            vel,
        ) in events:

            while True:

                now = (
                    time.perf_counter()
                    - start_clock
                )

                wait = (
                    event_time
                    - now
                )

                if wait <= 0:
                    break

                time.sleep(
                    min(
                        wait,
                        0.01,
                    )
                )

            if etype == "melody_on":

                engine.play_melody(
                    data,
                    vel,
                )

            elif etype == "melody_off":

                engine.stop_melody(
                    data
                )

            elif etype == "chord_on":

                engine.play_chord(
                    data,
                    vel,
                )

            elif etype == "chord_off":

                engine.stop_chord(
                    data
                )

            elif etype == "bass_on":

                engine.play_bass(
                    data,
                    vel,
                )

            elif etype == "bass_off":

                engine.stop_bass(
                    data
                )

            elif etype == "drum":

                engine.play_drum(
                    data,
                    vel,
                )

    finally:

        engine.close()

    print("[播放完成]")


# =========================
# 主流程
# =========================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "subject",
        help="受试者ID，例如 s03",
    )

    parser.add_argument(
        "--device",
        type=int,
        required=True,
        help="MIDI输出设备ID",
    )

    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help=(
            "无板测试模式："
            "直接使用已有CSV，"
            "跳过实时录制"
        ),
    )

    args = parser.parse_args()

    subject_id = args.subject

    # -------------------------
    # 1. baseline
    # -------------------------

    anchor = load_anchor(
        subject_id
    )

    if anchor is None:
        sys.exit(1)

    print(
        f"[校准] "
        f"anchor_rms="
        f"{anchor:.3f}"
    )

    pipeline_start = (
        time.perf_counter()
    )

    # -------------------------
    # 2. CSV来源
    # -------------------------

    if args.csv is not None:

        csv_path = Path(
            args.csv
        )

        if not csv_path.exists():

            print(
                f"[错误] "
                f"CSV不存在: "
                f"{csv_path}"
            )

            sys.exit(1)

        print()
        print(
            "[测试模式] "
            "跳过实时录制"
        )

        print(
            f"[CSV] {csv_path}"
        )

    else:

        csv_path = record_free(
            subject_id
        )

        if csv_path is None:
            sys.exit(1)

    # -------------------------
    # 3. profile + energy
    # -------------------------

    profile, energy = (
        analyze_motion(
            csv_path,
            subject_id,
            anchor,
        )
    )

    if profile is None:
        sys.exit(1)

    # -------------------------
    # 4. compose
    # -------------------------

    seed = int(
        time.time() * 1000
    )

    score = compose(
        profile,
        seed=seed,
    )

    print()
    print(
        f"[作曲] "
        f"{score['bars']} 小节 | "
        f"{score['bpm']} BPM"
    )

    # -------------------------
    # 5. 延迟
    # -------------------------

    ready_time = (
        time.perf_counter()
        - pipeline_start
    )

    if args.csv is None:

        print(
            f"[延迟] "
            f"按R到准备播放 "
            f"{ready_time:.2f}s"
        )

    else:

        print(
            f"[处理耗时] "
            f"{ready_time:.2f}s"
        )

    # -------------------------
    # 6. arrangement + playback
    # -------------------------

    play_score(
        score,
        energy,
        args.device,
    )


if __name__ == "__main__":
    main()