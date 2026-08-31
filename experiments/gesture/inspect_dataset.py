import csv
from pathlib import Path
import matplotlib.pyplot as plt


def load_axis(path, axis_name):
    values = []

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            values.append(float(row[axis_name]))

    return values


def plot_group(folder, axis_name):
    paths = sorted(Path(folder).glob("*.csv"))

    plt.figure(figsize=(10, 5))

    for path in paths:
        values = load_axis(path, axis_name)

        # 把不同采样点数统一映射到 0~1 的动作窗口
        n = len(values)

        if n <= 1:
            continue

        t = [i / (n - 1) for i in range(n)]

        plt.plot(
            t,
            values,
            alpha=0.75,
            label=path.stem
        )

    plt.axhline(0, linewidth=1)

    plt.xlabel("Normalized time")
    plt.ylabel(f"{axis_name} (rad/s)")
    plt.title(f"{folder} - {axis_name}")

    plt.legend()
    plt.tight_layout()
    plt.show()


plot_group("data/downstroke", "gy")
plot_group("data/other", "gy")

plot_group("data/downstroke", "gz")
plot_group("data/other", "gz")