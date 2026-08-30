import csv
import math
from pathlib import Path


def load_gyro(path):
    gx, gy, gz = [], [], []

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            gx.append(float(row["gx"]))
            gy.append(float(row["gy"]))
            gz.append(float(row["gz"]))

    return gx, gy, gz


def percentile(values, p):
    values = sorted(values)

    if not values:
        return 0.0

    index = int((len(values) - 1) * p)
    return values[index]


def get_strength(path):
    gx, gy, gz = load_gyro(path)

    # 与棒长轴 X 垂直的挥棒角速度
    gyro_perp = [
        math.sqrt(y*y + z*z)
        for y, z in zip(gy, gz)
    ]

    # 总角速度
    gyro_mag = [
        math.sqrt(x*x + y*y + z*z)
        for x, y, z in zip(gx, gy, gz)
    ]

    rms_perp = math.sqrt(
        sum(v*v for v in gyro_perp) / len(gyro_perp)
    )

    p95_perp = percentile(gyro_perp, 0.95)

    max_perp = max(gyro_perp)
    max_mag = max(gyro_mag)

    return rms_perp, p95_perp, max_perp, max_mag


results = []

for path in Path("data/downstroke").glob("*.csv"):
    strength = get_strength(path)
    results.append((path.name, *strength))

results.sort(key=lambda x: x[1])

print(
    f"{'file':24s} "
    f"{'RMS_perp':>10s} "
    f"{'P95_perp':>10s} "
    f"{'MAX_perp':>10s} "
    f"{'MAX_mag':>10s}"
)

print("-" * 70)

for row in results:
    filename, rms, p95, max_perp, max_mag = row

    print(
        f"{filename:24s} "
        f"{rms:10.2f} "
        f"{p95:10.2f} "
        f"{max_perp:10.2f} "
        f"{max_mag:10.2f}"
    )