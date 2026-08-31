import csv
from pathlib import Path
import statistics
import math


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


def mean_abs(values):
    return sum(abs(x) for x in values) / len(values)


def positive_area(values):
    return sum(x for x in values if x > 0)


def negative_area(values):
    return sum(-x for x in values if x < 0)


def extract(path):
    d = load_csv(path)

    gy = d["gy"]
    gz = d["gz"]
    gx = d["gx"]

    features = {
        "max_gy": max(gy),
        "min_gy": min(gy),
        "range_gy": max(gy) - min(gy),

        "std_gy": statistics.pstdev(gy),
        "mean_abs_gy": mean_abs(gy),

        "positive_gy": positive_area(gy),
        "negative_gy": negative_area(gy),

        "max_abs_gx": max(abs(x) for x in gx),
        "max_abs_gz": max(abs(x) for x in gz),

        "std_gx": statistics.pstdev(gx),
        "std_gz": statistics.pstdev(gz),
    }

    return features


def print_folder(folder, label):
    for path in sorted(Path(folder).glob("*.csv")):
        f = extract(path)

        print(
            f"{path.name:24s} "
            f"{label:10s} "
            f"maxGy={f['max_gy']:5.2f} "
            f"minGy={f['min_gy']:6.2f} "
            f"range={f['range_gy']:5.2f} "
            f"std={f['std_gy']:4.2f} "
            f"+area={f['positive_gy']:7.1f} "
            f"-area={f['negative_gy']:7.1f} "
            f"|gz|max={f['max_abs_gz']:5.2f}"
        )


print("DOWNSTROKE")
print_folder("data/downstroke", "downstroke")

print()
print("OTHER")
print_folder("data/other", "other")