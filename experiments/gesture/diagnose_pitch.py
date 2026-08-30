import csv
import math
import statistics
from pathlib import Path


def load_csv(path):
    data = {
        "ax": [], "ay": [], "az": [],
        "gx": [], "gy": [], "gz": []
    }

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            for key in data:
                data[key].append(float(row[key]))

    return data


def analyze(path):
    d = load_csv(path)
    n = len(d["ax"])

    k = min(20, max(5, n // 5))

    # 用窗口开头估计重力方向
    ux = statistics.mean(d["ax"][:k])
    uy = statistics.mean(d["ay"][:k])
    uz = statistics.mean(d["az"][:k])

    g_start = math.sqrt(
        ux * ux +
        uy * uy +
        uz * uz
    )

    if g_start > 1e-6:
        ux /= g_start
        uy /= g_start
        uz /= g_start

    # X × Up
    ny = -uz
    nz = uy

    norm_n = math.sqrt(
        ny * ny +
        nz * nz
    )

    if norm_n > 1e-6:
        ny /= norm_n
        nz /= norm_n

    pitch = []
    gyro_perp = []

    for gy, gz in zip(d["gy"], d["gz"]):
        pitch.append(
            gy * ny +
            gz * nz
        )

        gyro_perp.append(
            math.sqrt(
                gy * gy +
                gz * gz
            )
        )

    positive = [
        x for x in pitch
        if x > 0
    ]

    negative = [
        -x for x in pitch
        if x < 0
    ]

    return {
        "g_start": g_start,

        "up_x": ux,
        "up_y": uy,
        "up_z": uz,

        "pitch_max": max(pitch),
        "pitch_min": min(pitch),
        "pitch_mean": statistics.mean(pitch),
        "pitch_std": statistics.pstdev(pitch),

        "pitch_positive_mean":
            statistics.mean(positive)
            if positive else 0,

        "pitch_negative_mean":
            statistics.mean(negative)
            if negative else 0,

        "pitch_positive_ratio":
            len(positive) / len(pitch),

        "rms_perp":
            math.sqrt(
                sum(x*x for x in gyro_perp)
                / len(gyro_perp)
            )
    }


files = [
    "generalization_test/downstroke/downstroke_007.csv",
    "generalization_test/downstroke/downstroke_008.csv",
    "generalization_test/downstroke/downstroke_009.csv",
    "generalization_test/downstroke/downstroke_010.csv",

    "generalization_test/downstroke/downstroke_013.csv",
    "generalization_test/downstroke/downstroke_015.csv",
    "generalization_test/downstroke/downstroke_016.csv",

    "generalization_test/other/other_001.csv",
    "generalization_test/other/other_019.csv",
    "generalization_test/other/other_020.csv",
]


for filename in files:
    f = analyze(Path(filename))

    print()
    print(filename)

    print(
        f"start |a| = {f['g_start']:.2f}"
    )

    print(
        "estimated Up = "
        f"({f['up_x']:.2f}, "
        f"{f['up_y']:.2f}, "
        f"{f['up_z']:.2f})"
    )

    print(
        f"pitch: "
        f"min={f['pitch_min']:.2f}, "
        f"max={f['pitch_max']:.2f}, "
        f"mean={f['pitch_mean']:.2f}, "
        f"std={f['pitch_std']:.2f}"
    )

    print(
        f"pitch positive mean="
        f"{f['pitch_positive_mean']:.2f}, "
        f"negative mean="
        f"{f['pitch_negative_mean']:.2f}, "
        f"positive ratio="
        f"{f['pitch_positive_ratio']:.2f}"
    )

    print(
        f"RMS_perp="
        f"{f['rms_perp']:.2f}"
    )