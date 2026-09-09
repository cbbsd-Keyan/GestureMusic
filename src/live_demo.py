import argparse
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent

sys.path.insert(0, str(BASE / "features"))
sys.path.insert(0, str(BASE / "music"))
sys.path.insert(0, str(BASE / "input"))

from udp_reader import UDPReader
from recorder import Recorder

from profile import (
    analyze,
    build_profile_json,
    load_rows,
    resample,
)


# =========================
# 配置
# =========================

RECORD_SECONDS = 15

LIVE_DIR = (
    BASE.parent / "reports" / "live_demo"
)


def check_board(reader, wait_s=3.0):

    t0 = time.monotonic()

    alive = 0
    data_lines = 0

    while time.monotonic() - t0 < wait_s:

        line = reader.read()

        if line is None:
            time.sleep(0.02)
            continue

        if line.startswith("ALIVE"):
            alive += 1

        elif "," in line:

            try:

                parts = line.split(",")

                if len(parts) == 7:
                    float(parts[0])
                    data_lines += 1

            except ValueError:
                pass

    if data_lines == 0 and alive == 0:

        print()
        print("[板子无响应] 三步排查:")
        print("  1. 手机热点开着吗? 板子在已连接设备里吗?")
        print("  2. 防火墙放行 UDP 4210 了吗?")
        print("  3. 板子重新上电等 10 秒再试")

        return False

    print(
        f"[板子在线] 心跳{alive}条, "
        f"数据流{data_lines}点/3秒"
    )

    return True


def record_swing(reader, seconds):

    rows = []

    t0 = time.monotonic()

    last_print = 0

    while time.monotonic() - t0 < seconds:

        line = reader.read()

        if line is None:
            time.sleep(0.001)
            continue

        parts = line.split(",")

        if len(parts) != 7:
            continue

        try:

            values = [float(x) for x in parts]

            rows.append(values)

        except ValueError:
            continue

        elapsed = time.monotonic() - t0

        if elapsed - last_print >= 2.0:

            last_print = elapsed

            print(
                f"  已录 {elapsed:.0f} 秒 "
                f"({len(rows)} 点)"
            )

    return rows


def resolve_energy(profile_json, csv_path, subject):

    e = profile_json["energy"]

    if e.get("normalized") is not None:

        return e["normalized"], "本人校准"

    anchor_path = (
        csv_path.parent / "baseline.json"
    )

    if anchor_path.exists():

        try:

            with open(
                anchor_path,
                encoding="utf-8",
            ) as f:

                anchor = json.load(f)[
                    "anchor_rms"
                ]

            return (
                max(
                    0.0,
                    min(
                        1.0,
                        e["gyro_rms"] / anchor,
                    ),
                ),
                "本人校准锚值",
            )

        except (
            KeyError,
            ValueError,
            json.JSONDecodeError,
        ):
            pass

    raw = e["gyro_rms"]

    energy = max(0.0, min(1.0, (raw - 1.0) / 5.0))

    return energy, "保底换算"


def show_motion_chart(
    csv_path,
    profile,
    energy,
    energy_src,
    out_png,
    interactive=True,
):

    """
    录制结束立即生成"刚才你怎么挥的"图,
    播放期间常驻, 让动作->音乐的因果可见。
    """

    import math
    import statistics

    import matplotlib

    if not interactive:
        matplotlib.use("Agg")

    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "sans-serif",
    ]

    import matplotlib.pyplot as plt

    from tempo import gyro_mag

    rows = load_rows(csv_path)

    if len(rows) < 2:
        return

    uniform = resample(rows)

    mags = [gyro_mag(v) for v in uniform]

    hz = 100.0

    # 1秒滚动RMS(步进0.1s)
    win = int(hz)

    times = []
    roll = []

    for i in range(0, len(mags) - win + 1, int(hz * 0.1)):

        seg = mags[i : i + win]

        times.append((i + win / 2) / hz)

        roll.append(
            math.sqrt(
                statistics.fmean(
                    x * x for x in seg
                )
            )
        )

    # 节拍标记: 平滑后局部峰
    sm = []

    half = 5

    for i in range(len(mags)):

        lo = max(0, i - half)
        hi = min(len(mags), i + half + 1)

        sm.append(
            statistics.fmean(mags[lo:hi])
        )

    mean = statistics.fmean(sm)
    std = statistics.pstdev(sm)

    thr = mean + 0.5 * std

    min_gap = int(hz * 60 / 180)

    peaks = []

    last = -10 * min_gap

    for i in range(1, len(sm) - 1):

        if (
            sm[i] >= sm[i - 1]
            and sm[i] > sm[i + 1]
            and sm[i] > thr
            and i - last >= min_gap
        ):

            peaks.append(i / hz)

            last = i

    # 档位线(raw单位)
    if "校准" in energy_src:

        anchor_path = (
            Path(csv_path).parent / "baseline.json"
        )

        with open(
            anchor_path,
            encoding="utf-8",
        ) as f:

            anchor = json.load(f)["anchor_rms"]

        tier_lo = 0.33 * anchor
        tier_hi = 0.70 * anchor

        tier_note = "按你的校准"

    else:

        tier_lo = 1.0 + 5.0 * 0.33
        tier_hi = 1.0 + 5.0 * 0.70

        tier_note = "保底换算"

    bpm = profile["tempo"]["bpm"]

    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(9, 5.5),
        gridspec_kw={
            "height_ratios": [3, 1]
        },
    )

    ax1.plot(
        times,
        roll,
        color="#1f77b4",
        linewidth=1.8,
    )

    peak_vals = []

    for t in peaks:

        idx = min(
            int(t * 10),
            len(roll) - 1,
        )

        peak_vals.append(roll[idx])

    ax1.scatter(
        peaks,
        peak_vals,
        color="#d62728",
        s=18,
        zorder=3,
        label=f"检测到的挥动 ({len(peaks)}下)",
    )

    ax1.axhline(
        tier_lo,
        color="green",
        linestyle="--",
        alpha=0.7,
    )

    ax1.axhline(
        tier_hi,
        color="red",
        linestyle="--",
        alpha=0.7,
    )

    ax1.text(
        times[-1],
        tier_lo,
        " 中档线",
        color="green",
        va="bottom",
    )

    ax1.text(
        times[-1],
        tier_hi,
        " 激烈线",
        color="red",
        va="bottom",
    )

    ax1.set_ylabel("挥动强度")

    ax1.set_title(
        f"你刚才的挥动 ({tier_note})"
    )

    ax1.legend(loc="upper left")

    bpm_text = (
        f"{bpm:.0f}"
        if bpm
        else "未检出(用90)"
    )

    tier_name = (
        "轻柔档"
        if energy < 0.33
        else "激烈档"
        if energy > 0.7
        else "中档"
    )

    ax2.axis("off")

    ax2.text(
        0.02,
        0.72,
        f"节奏 {bpm_text} → 曲速   "
        f"强度 {energy*100:.0f}% → {tier_name}   "
        f"时长 {profile['duration_s']:.0f}秒 → 曲长",
        fontsize=13,
    )

    ax2.text(
        0.02,
        0.22,
        "曲线跨过虚线 = 音乐换档；红点 = 系统数出来的拍子",
        fontsize=10,
        color="gray",
    )

    fig.tight_layout()

    fig.savefig(
        out_png,
        dpi=120,
    )

    if interactive:

        try:

            plt.show(block=False)

            plt.pause(0.5)

        except Exception:

            pass


def main():

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--device",
        type=int,
        default=1,
        help="MIDI 输出设备号",
    )

    parser.add_argument(
        "--subject",
        default="s00",
        help="受试者编号",
    )

    parser.add_argument(
        "--llm",
        action="store_true",
        help="用大模型作曲(失败自动回规则)",
    )

    parser.add_argument(
        "--csv",
        default=None,
        help="跳过录制, 直接用现有CSV测试",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只跑流程不出声(测试用)",
    )

    args = parser.parse_args()

    print("===== 挥棒出声 · 完整流程 =====")
    print()

    # -------------------------
    # 1. 板子 & 录制
    # -------------------------

    if args.csv:

        csv_path = Path(args.csv)

        print(f"[测试模式] 使用现有数据 {csv_path}")

    else:

        reader = UDPReader(port=4210)

        if not check_board(reader):
            sys.exit(1)

        print()
        input("自由挥动 15 秒, 按回车开始...")

        print("[录制中]")

        rows = record_swing(
            reader,
            RECORD_SECONDS,
        )

        if len(rows) < 300:

            print(
                f"[数据太少] 只录到{len(rows)}点, "
                "请检查板子后重试"
            )

            sys.exit(1)

        recorder = Recorder(
            out_dir=LIVE_DIR / "_sessions",
            subject_id=args.subject,
        )

        recorder.start()

        for r in rows:
            recorder.feed(r)

        recorder.stop()

        result = recorder.save(scene="live")

        csv_path = result["csv"]

        reader.close()

    # -------------------------
    # 2. 画像
    # -------------------------

    t_analyze = time.monotonic()

    r = analyze(csv_path)

    if "error" in r:

        print(f"[画像失败] {r['error']}")

        sys.exit(1)

    profile = build_profile_json(
        r,
        args.subject,
        "live",
    )

    energy, energy_src = resolve_energy(
        profile,
        csv_path,
        args.subject,
    )

    bpm = profile["tempo"]["bpm"]

    bpm_text = (
        f"{bpm:.0f} (可信度{profile['tempo']['confidence']})"
        if bpm
        else "未检出, 将用默认90"
    )

    print()
    print(f"[画像] 节奏: {bpm_text}")
    print(
        f"[画像] 强度: {energy*100:.0f}% "
        f"({energy_src})"
    )
    print(
        f"[画像] 时长: {profile['duration_s']}秒 "
        f"| 活跃: {profile['activity']['active_ratio']*100:.0f}%"
    )

    t_profile_done = time.monotonic()

    # -------------------------
    # 3. 作曲
    # -------------------------

    from composer_rule import compose

    score = None

    engine_name = "规则作曲"

    if args.llm:

        try:

            from client import call_llm

            score, meta = call_llm(profile)

            engine_name = (
                f"大模型({meta['model']}, "
                f"{meta['latency_s']}秒)"
            )

        except Exception as e:

            print(
                f"[大模型失败] {e}"
            )

            print("[自动切换规则作曲]")

            score = None

    if score is None:

        score = compose(
            profile,
            seed=int(time.time()) % 100000,
        )

    print()
    print(
        f"[作曲] {engine_name} | "
        f"{score['bars']}小节 "
        f"{score['bpm']}BPM | "
        f"《{score.get('title', '')}》"
    )

    t_compose_done = time.monotonic()

    # -------------------------
    # 4. 存档
    # -------------------------

    stamp = time.strftime("%H%M%S")

    out_dir = LIVE_DIR / stamp

    out_dir.mkdir(parents=True, exist_ok=True)

    import shutil

    shutil.copy(csv_path, out_dir / "input.csv")

    with open(
        out_dir / "profile.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            profile,
            f,
            ensure_ascii=False,
            indent=2,
        )

    with open(
        out_dir / "score.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            score,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"[存档] {out_dir}")

    # -------------------------
    # 4.5 挥动曲线图(播放期间常驻)
    # -------------------------

    try:

        show_motion_chart(
            csv_path,
            profile,
            energy,
            energy_src,
            out_dir / "motion.png",
            interactive=not args.dry_run,
        )

        print("[曲线] 已生成挥动曲线图")

    except Exception as e:

        print(f"[曲线] 生成失败(不影响音乐): {e}")

    # -------------------------
    # 5. 播放
    # -------------------------

    if args.dry_run:

        print("[试运行] 跳过播放")

    else:

        from arrangement import (
            build_arranged_events,
        )
        from midi_engine import MidiEngine

        print()
        print("[播放中] 按 Ctrl+C 可中断")

        events, tier, play_bpm = (
            build_arranged_events(score, energy)
        )

        engine = MidiEngine(
            device_id=args.device,
        )

        grid = 60.0 / play_bpm / 4.0

        start_clock = time.perf_counter()

        try:

            for t, etype, data, vel in events:

                while True:

                    now = (
                        time.perf_counter()
                        - start_clock
                    )

                    wait = t - now

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

        except KeyboardInterrupt:

            print("\n[中断] 停止播放")

        finally:

            engine.close()

    # -------------------------
    # 6. 耗时
    # -------------------------

    print()
    print(
        f"[耗时] 画像 {t_profile_done - t_analyze:.1f}秒 "
        f"+ 作曲 {t_compose_done - t_profile_done:.1f}秒 "
        f"= 停止挥动到就绪 "
        f"{t_compose_done - t_analyze:.1f}秒"
    )

    print("[完成]")


if __name__ == "__main__":

    main()
