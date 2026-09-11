import csv
import json
import math
import statistics
import sys
from pathlib import Path

from tempo import estimate_tempo
from posture import summarize_posture
from structure import detect_change_points


# =========================
# 常量
# =========================

TARGET_HZ = 100.0

GRAVITY = 9.80665

# 陀螺合量超过该值视为"在动"（rad/s）
ACTIVE_THRESHOLD = 0.5


# =========================
# 加载与重采样
# =========================

def load_rows(path):

    rows = []

    with open(path, "r", encoding="utf-8") as f:

        reader = csv.DictReader(f)

        for row in reader:

            try:

                rows.append([
                    float(row["time_ms"]),
                    float(row["ax"]),
                    float(row["ay"]),
                    float(row["az"]),
                    float(row["gx"]),
                    float(row["gy"]),
                    float(row["gz"]),
                ])

            except (ValueError, KeyError, TypeError):
                continue

    return rows


def resample(rows, hz=TARGET_HZ):

    """
    线性插值到均匀时间网格。
    WiFi 抖动导致原始时间戳不均匀，
    自相关等时序分析必须先经过这一步。
    """

    if len(rows) < 2:
        return []

    t0 = rows[0][0]

    step = 1000.0 / hz

    n = int((rows[-1][0] - t0) / step) + 1

    out = []

    src = 0

    for i in range(n):

        t = t0 + i * step

        while (
            src + 1 < len(rows)
            and rows[src + 1][0] < t
        ):
            src += 1

        if src + 1 >= len(rows):
            break

        tA, tB = rows[src][0], rows[src + 1][0]

        if tB <= tA:
            out.append(rows[src][1:])
            continue

        alpha = (t - tA) / (tB - tA)

        vals = [
            a + (b - a) * alpha
            for a, b in zip(
                rows[src][1:],
                rows[src + 1][1:],
            )
        ]

        out.append(vals)

    return out


# =========================
# 特征
# =========================

def accel_mag(v):

    return math.sqrt(
        v[0] * v[0]
        + v[1] * v[1]
        + v[2] * v[2]
    )


def gyro_mag(v):

    return math.sqrt(
        v[3] * v[3]
        + v[4] * v[4]
        + v[5] * v[5]
    )


def analyze(path):

    rows = load_rows(path)

    if len(rows) < 50:
        return {
            "file": str(path),
            "error": "样本过少",
        }

    duration = (
        rows[-1][0] - rows[0][0]
    ) / 1000.0

    hz_raw = (
        (len(rows) - 1) / duration
        if duration > 0
        else 0.0
    )

    uniform = resample(rows)

    a_mags = [accel_mag(v) for v in uniform]
    g_mags = [gyro_mag(v) for v in uniform]

    a_devs = [
        abs(a - GRAVITY) for a in a_mags
    ]

    g_rms = math.sqrt(
        statistics.fmean(
            g * g for g in g_mags
        )
    )

    active_ratio = (
        sum(
            1
            for g in g_mags
            if g > ACTIVE_THRESHOLD
        )
        / len(g_mags)
    )

    tempo = estimate_tempo(uniform)

    posture = summarize_posture(uniform)

    change_points = detect_change_points(uniform)

    return {
        "file": str(path),
        "duration_s": round(duration, 2),
        "hz_raw": round(hz_raw, 1),
        "samples_uniform": len(uniform),
        "accel_std": round(
            statistics.pstdev(a_mags), 3
        ),
        "accel_mean_dev": round(
            statistics.fmean(a_devs), 3
        ),
        "accel_peak_dev": round(
            max(a_devs), 3
        ),
        "gyro_rms": round(g_rms, 3),
        "gyro_peak": round(max(g_mags), 3),
        "active_ratio": round(
            active_ratio, 3
        ),
        "tempo_bpm": tempo["bpm"],
        "tempo_confidence": tempo["confidence"],
        "tempo_method": tempo["method"],
        "posture_available": posture["available"],
        "roll_median": posture["roll_median"],
        "roll_range": posture["roll_range"],
        "pitch_median": posture["pitch_median"],
        "change_points": change_points,
    }


def build_profile_json(result, subject_id, mount_version):

    """
    输出符合 llm/schema.py PROFILE_SCHEMA v1 的画像。
    """
    normalized = None

    baseline_path = (
        Path(result["file"]).parent / "baseline.json"
    )

    if baseline_path.exists():
        try:
            with open(
                baseline_path,
                "r",
                encoding="utf-8",
            ) as f:
                baseline = json.load(f)

            anchor_rms = float(
                baseline["anchor_rms"]
            )

            if anchor_rms > 0:
                normalized = round(
                    max(
                        0.0,
                        min(
                            result["gyro_rms"]
                            / anchor_rms,
                            1.0,
                        ),
                    ),
                    3,
                )

        except (
            KeyError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ):
            normalized = None

    return {
        "version": "1.0",
        "duration_s": result["duration_s"],
        "tempo": {
            "bpm": result["tempo_bpm"],
            "confidence": result["tempo_confidence"],
            "method": result["tempo_method"],
        },
        "energy": {
            "gyro_rms": result["gyro_rms"],
            "accel_std": result["accel_std"],
            "gyro_peak": result["gyro_peak"],
            "normalized":normalized,
        },
        "activity": {
            "active_ratio": result["active_ratio"],
        },
        "posture": {
            "available": result["posture_available"],
            "roll_median": result["roll_median"],
            "roll_range": result["roll_range"],
            "pitch_median": result["pitch_median"],
        },
        "structure": {
            "change_points": (
                result["change_points"] or None
            ),
        },
        "subject_id": subject_id,
        "mount_version": mount_version,
    }


# =========================
# 目录批量 + 分离度
# =========================

def analyze_folder(folder):

    results = []

    for path in sorted(
        Path(folder).glob("*.csv")
    ):

        r = analyze(path)

        if "error" not in r:
            results.append(r)

    scenes = {}

    for r in results:

        scene = (
            Path(r["file"]).stem.split("_")[0]
        )

        scenes.setdefault(scene, []).append(r)

    for scene, items in scenes.items():

        print(f"\n[{scene}] {len(items)} 段")

        for r in items:

            print(
                f"  {Path(r['file']).name:20s} "
                f"accel_std={r['accel_std']:6.3f} "
                f"gyro_rms={r['gyro_rms']:6.3f} "
                f"gyro_peak={r['gyro_peak']:7.3f} "
                f"active={r['active_ratio']:.2f} "
                f"bpm={r['tempo_bpm'] and round(r['tempo_bpm'],1)} "
                f"({r['tempo_confidence']}/"
                f"{r['tempo_method']})"
            )

    if (
        "vigorous" in scenes
        and "gentle" in scenes
    ):

        v = [
            r["gyro_rms"]
            for r in scenes["vigorous"]
        ]

        g = [
            r["gyro_rms"]
            for r in scenes["gentle"]
        ]

        v_med = statistics.median(v)
        g_med = statistics.median(g)

        ratio = (
            v_med / g_med
            if g_med > 0
            else float("inf")
        )

        print()
        print(
            f"分离度 gyro_rms: "
            f"vigorous中位={v_med:.3f} "
            f"gentle中位={g_med:.3f} "
            f"比值={ratio:.2f} "
            f"(目标>=1.5)"
        )

    return results


# =========================
# 入口
# =========================

if __name__ == "__main__":

    # Windows重定向到文件时默认GBK，强制UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2:

        print(
            "用法: "
            "python profile.py <csv文件或目录>"
        )

        sys.exit(1)

    target = Path(sys.argv[1])

    use_json = "--json" in sys.argv

    if use_json:

        subject = "s00"
        mount = "ruler_v1"

        result = analyze(target)

        if "error" in result:
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(1)

        print(
            json.dumps(
                build_profile_json(
                    result,
                    subject,
                    mount,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

    elif target.is_dir():

        analyze_folder(target)

    else:

        print(
            json.dumps(
                analyze(target),
                ensure_ascii=False,
                indent=2,
            )
        )
