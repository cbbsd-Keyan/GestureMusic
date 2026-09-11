import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent

sys.path.insert(0, str(BASE / "features"))
sys.path.insert(0, str(BASE / "music"))
sys.path.insert(0, str(BASE / "input"))
sys.path.insert(0, str(BASE / "llm"))

from udp_reader import UDPReader
from recorder import Recorder
from session_clock import SessionClock

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


def record_swing(reader, seconds, timing=None):

    # 等待用户和校准时UDP持续到达，先丢弃旧包，避免与当前视频错配。
    for _ in range(10000):
        if reader.read() is None:
            break
    else:
        raise RuntimeError("UDP积压无法清空，请重新录制")

    rows = []
    clock = SessionClock()

    t0 = time.monotonic()

    last_print = 0

    while time.monotonic() - t0 < seconds:

        line = reader.read()
        received_at = time.monotonic()

        if line is None:
            time.sleep(0.001)
            continue

        parts = line.split(",")

        if len(parts) != 7:
            continue

        try:

            values = [float(x) for x in parts]

        except ValueError:
            continue

        if not all(math.isfinite(value) for value in values):
            continue
        if not clock.observe(values[0], received_at):
            continue
        rows.append(values)

        elapsed = time.monotonic() - t0

        if elapsed - last_print >= 2.0:

            last_print = elapsed

            print(
                f"  已录 {elapsed:.0f} 秒 "
                f"({len(rows)} 点)"
            )

    if timing is not None:
        timing.update(clock.summary())
    return rows


def capture_session(args):
    """现场采集；所有退出路径均停止视频并关闭UDP。"""
    reader = UDPReader(port=4210)
    tracker = None
    tracker_stopped = False
    vision = None
    try:
        if not check_board(reader):
            sys.exit(1)

        if args.vision:
            from beacon_tracker import BeaconTracker
            tracker = BeaconTracker(beacon=args.beacon, camera_id=args.camera, mirror=args.mirror)
            vision = {"version": 1, "time_reference": "csv_start",
                      "levels": [], "beacon": args.beacon,
                      "camera": args.camera, "error": None}
            try:
                calibrated = tracker.calibrate()
            except Exception as exc:
                calibrated = False
                tracker.error = str(exc)
            if not calibrated:
                vision["error"] = tracker.error or "校准失败"
                print(f"[视觉不可用] {vision['error']}；使用默认音区")

        input("自由挥动 15 秒, 按回车开始...")
        if tracker is not None and vision["error"] is None:
            if not tracker.start():
                vision["error"] = tracker.error or "采集启动失败"
                print(f"[视觉不可用] {vision['error']}；使用默认音区")

        print("[录制中]")
        timing = {}
        try:
            rows = record_swing(reader, RECORD_SECONDS, timing=timing)
        except (ValueError, RuntimeError) as exc:
            print(f"[录制失败] {exc}")
            sys.exit(1)

        if tracker is not None:
            tracker.stop()
            tracker_stopped = True
            if tracker.error:
                vision["error"] = tracker.error
            vision["sync"] = timing
            if vision["error"] is None and timing.get("samples", 0):
                vision["levels"] = tracker.levels(
                    origin=timing["host_origin_monotonic"],
                    duration=timing["duration_s"],
                )
                print(
                    f"[视觉对齐] 有效样本{len(vision['levels'])} "
                    f"接收偏移跨度{timing['receive_offset_span_s'] * 1000:.1f}ms"
                )
            if vision["error"]:
                print(f"[视觉不可用] {vision['error']}；使用默认音区")

        if len(rows) < 300:
            print(f"[数据太少] 只录到{len(rows)}点，请检查板子后重试")
            sys.exit(1)

        recorder = Recorder(out_dir=LIVE_DIR / "_sessions", subject_id=args.subject)
        recorder.start()
        for row in rows:
            recorder.feed(row)
        recorder.stop()
        csv_path = recorder.save(scene="live")["csv"]
        return csv_path, vision
    finally:
        try:
            if tracker is not None and not tracker_stopped:
                tracker.stop()
        finally:
            reader.close()


def load_vision(csv_path):
    """只复用与当前CSV配套的视觉记录，避免不同会话误配。"""
    path = csv_path.with_name("vision.json")
    with path.open(encoding="utf-8") as f:
        vision = json.load(f)
    if (vision.get("version") != 1 or vision.get("time_reference") != "csv_start"
            or vision.get("csv_sha256") != hashlib.sha256(csv_path.read_bytes()).hexdigest()):
        raise ValueError("视觉记录的版本、时间基准或配套CSV不匹配")
    if not isinstance(vision.get("levels"), list):
        raise ValueError("视觉记录缺少样本列表")
    # 作曲端还会检查每个样本的值；此处用于入口的明确报错。
    import math
    for sample in vision["levels"]:
        if (not isinstance(sample, list) or len(sample) != 2
                or not isinstance(sample[0], (int, float))
                or not math.isfinite(sample[0]) or sample[1] not in (-1, 0, 1)):
            raise ValueError("视觉样本需为[有限秒数, -1/0/+1音区]")
    return vision


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
    register_times=None,
    register_mode=None,
    dynamics=None,
    timeline=None,
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

    from composer_events import extract_swing_events
    peaks = [t for t, _, _ in extract_swing_events(uniform)]
    if timeline is not None:
        times = [p["t"] for p in timeline["points"]]
        roll = [p["gyro_rms"] for p in timeline["points"]]

    # 档位线(raw单位)
    if timeline is not None and timeline.get("anchor_rms"):
        anchor = timeline["anchor_rms"]
        tier_lo, tier_hi = 0.33 * anchor, 0.70 * anchor
        tier_note = "按你的校准"
    elif "校准" in energy_src:

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

    show_reg = (
        register_times
        and register_mode in ("posture", "vision")
        and len(register_times) > 0
    )

    heights = [3] + ([1.3] if show_reg else []) + ([1.5] if dynamics else []) + [1]
    fig, axes = plt.subplots(len(heights), 1, figsize=(9, 4 + len(heights)),
                             gridspec_kw={"height_ratios": heights})
    ax1, ax2 = axes[0], axes[-1]
    if show_reg:
        axR = axes[1]
    if dynamics is not None:
        axD = axes[-2]
        controls = dynamics.bar_controls
        positions = [dynamics.intro_seconds + c["bar"] * 16 * dynamics.grid_s for c in controls]
        levels = [{"calm": 0, "neutral": 1, "intense": 2}[c["tier"]] for c in controls]
        positions.append(dynamics.intro_seconds + dynamics.bars * 16 * dynamics.grid_s)
        levels.append(levels[-1])
        axD.step(positions, levels, where="post", color="#e07a20")
        axD.set_yticks([0, 1, 2], ["轻柔", "中等", "强烈"])
        axD.set_ylim(-0.3, 2.3)
        axD.set_xlabel("实际播放时间（秒，含前奏偏移）")
        axD.set_title("实际伴奏档位（按小节切换；静止时暂停起音）")

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

    ax1.set_ylabel("角速度 RMS (rad/s)")

    ax1.set_title(
        f"你刚才的挥动 ({tier_note})"
    )

    ax1.legend(loc="upper left")

    if show_reg:

        reg_label = (
            "视觉音区(摄像头)"
            if register_mode == "vision"
            else "俯仰角音区(试验)"
        )

        reg_xs = [t for t, _ in register_times]
        reg_ys = [v for _, v in register_times]

        axR.step(
            reg_xs,
            reg_ys,
            where="post",
            color="#9467bd",
            linewidth=1.8,
        )

        axR.scatter(
            reg_xs,
            reg_ys,
            color="#9467bd",
            s=16,
            zorder=3,
        )

        axR.set_yticks([-1, 0, 1])
        axR.set_yticklabels(["低", "中", "高"])
        axR.set_ylim(-1.5, 1.5)
        axR.set_ylabel("音区")
        axR.set_title(
            f"每次挥动实际生效的音区 | {reg_label}"
        )

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
        (f"播放 {dynamics.bpm:g} BPM   总体强度 {energy*100:.0f}%   伴奏跟随局部强弱"
         if dynamics is not None else
         f"动作节奏 {bpm_text}   总体强度 {energy*100:.0f}% → {tier_name}"),
        fontsize=13,
    )

    ax2.text(
        0.02,
        0.22,
        ("强度驱动力度；伴奏按小节换档（含平滑与滞回）；红点为挥动"
         if dynamics is not None else "当前按整段强度配器，虚线仅作参考；红点为挥动"),
        fontsize=10,
        color="gray",
    )

    fig.tight_layout()

    fig.savefig(
        out_png,
        dpi=120,
    )
    if not interactive:
        plt.close(fig)

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
        "--events",
        action="store_true",
        help="下挥落音试验模式(挥动时刻直接变音符)",
    )

    register_mode = parser.add_mutually_exclusive_group()
    register_mode.add_argument(
        "--posture",
        action="store_true",
        help="姿态控音区试验(按相对俯仰角分音区;需--events)",
    )

    register_mode.add_argument(
        "--vision", action="store_true",
        help="摄像头控音区试验(需--events；CSV复测需同目录vision.json)",
    )
    parser.add_argument("--camera", type=int, default=0, help="视觉模式摄像头编号")
    parser.add_argument("--mirror", action="store_true", help="水平镜像(摄像头画面左右反了就加)")
    parser.add_argument("--beacon", choices=("bright", "green"), default="bright",
                        help="视觉信标：bright亮点 / green绿色亮点")

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只跑流程不出声(测试用)",
    )
    parser.add_argument("--static-energy", action="store_true", help="使用旧版整段能量配器作对照")
    parser.add_argument("--seed", type=int, default=None, help="规则作曲随机种子，便于固定旋律比较")

    args = parser.parse_args()

    if args.posture and not args.events:
        parser.error("--posture 需要同时使用 --events")
    if args.vision and not args.events:
        parser.error("--vision 需要同时使用 --events")

    print("===== 挥棒出声 · 完整流程 =====")
    print()

    # -------------------------
    # 1. 板子 & 录制
    # -------------------------

    vision = None
    if args.csv:

        csv_path = Path(args.csv)

        print(f"[测试模式] 使用现有数据 {csv_path}")
        if args.vision:
            try:
                vision = load_vision(csv_path)
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                parser.error(f"无法复测视觉模式: {exc}")

    else:

        csv_path, vision = capture_session(args)

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

    timeline = None
    if not args.static_energy:
        from energy_timeline import load_energy_timeline
        try:
            timeline = load_energy_timeline(csv_path)
            if timeline.get("anchor_rms"):
                energy = max(0.0, min(1.0, profile["energy"]["gyro_rms"] / timeline["anchor_rms"]))
                profile["energy"]["normalized"] = energy
                energy_src = "本人校准（时间线）"
        except (ValueError, OSError, TypeError, KeyError) as exc:
            timeline = None
            print(f"[动态配器不可用] {exc}；本次使用整段能量配器")

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
    register_times = None
    register_mode = None
    mapping = "song"

    if args.events:

        from composer_events import compose_events

        ev_score, ev_info = compose_events(
            csv_path,
            profile,
            use_posture=args.posture,
            vision_levels=vision["levels"] if args.vision else None,
        )

        if ev_score is not None:

            score = ev_score
            mapping = "events"
            counts = ev_info["counts"]
            register_times = ev_info.get("register_times")
            register_mode = ev_info.get("register_mode")

            engine_name = (
                f"下挥落音(试验) | "
                f"轻{counts['轻']} 中{counts['中']} "
                f"重{counts['重']}"
            )

            if args.posture:
                posture = ev_info["posture"]
                if posture is None:
                    print("[姿态音区] 挥动不足6次，使用默认音区")
                else:
                    print(
                        f"[姿态音区(试验)] 低{posture['低']} "
                        f"中{posture['中']} 高{posture['高']}"
                    )

            if args.vision:
                counts = ev_info["vision"]
                print(
                    f"[视觉音区(试验)] 低{counts['低']} 中{counts['中']} "
                    f"高{counts['高']} 未匹配{counts['未匹配']} "
                    "(未匹配使用默认音区)"
                )

        else:

            print(
                f"[下挥落音不可用] {ev_info}, "
                "自动用规则作曲"
            )

    if args.llm and not args.events and score is None:

        try:

            from client import call_llm

            score, meta = call_llm(profile)
            from validator import validate_and_fix
            score, fixes, fatals = validate_and_fix(score)
            if fatals:
                raise ValueError("；".join(fatals))

            engine_name = (
                f"大模型({meta['model']}, "
                f"{meta['latency_s']}秒)"
            )

        except Exception as e:

            score = None

            print(
                f"[大模型失败] {e}"
            )

            print("[自动切换规则作曲]")

    if score is None:

        score = compose(
            profile,
            seed=args.seed if args.seed is not None else int(time.time()) % 100000,
        )

    print()
    print(
        f"[作曲] {engine_name} | "
        f"{score['bars']}小节 "
        f"{score['bpm']}BPM | "
        f"《{score.get('title', '')}》"
    )

    t_compose_done = time.monotonic()

    from arrangement import build_arranged_events
    dynamics = None
    if timeline is not None:
        from motion_dynamics import MotionDynamics
        try:
            dynamics = MotionDynamics(score, timeline, mode=mapping)
        except (ValueError, TypeError, KeyError) as exc:
            print(f"[动态配器不可用] {exc}；本次使用整段能量配器")
            timeline = None
    events, tier, play_bpm = build_arranged_events(score, energy, dynamics=dynamics)
    if dynamics is not None:
        names = {"calm": "轻", "neutral": "中", "intense": "强"}
        print("[动态配器] 小节档位 " + "→".join(names[c["tier"]] for c in dynamics.bar_controls))

    # -------------------------
    # 4. 存档
    # -------------------------

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    out_dir = LIVE_DIR / stamp

    out_dir.mkdir(parents=True, exist_ok=True)

    import shutil

    shutil.copy(csv_path, out_dir / "input.csv")

    if dynamics is not None:
        for name, data in (("energy_timeline.json", timeline), ("dynamics.json", dynamics.report())):
            with (out_dir / name).open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    with (out_dir / "playback.json").open("w", encoding="utf-8") as f:
        json.dump({"version": 1, "play_bpm": play_bpm, "events": events}, f, ensure_ascii=False)

    if vision is not None:
        vision["csv_sha256"] = hashlib.sha256((out_dir / "input.csv").read_bytes()).hexdigest()
        with (out_dir / "vision.json").open("w", encoding="utf-8") as f:
            json.dump(vision, f, ensure_ascii=False, indent=2)

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
            register_times=register_times,
            register_mode=register_mode,
            dynamics=dynamics,
            timeline=timeline,
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
