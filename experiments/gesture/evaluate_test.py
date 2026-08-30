import csv
from pathlib import Path

THRESHOLD = 5.0


def get_features(path):
    gy = []

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            gy.append(float(row["gy"]))

    max_gy = max(gy)
    positive_gy = sum(x for x in gy if x > 0)
    negative_gy = sum(-x for x in gy if x < 0)

    return max_gy, positive_gy, negative_gy

def evaluate_folder(folder, true_label):
    paths = sorted(Path(folder).glob("*.csv"))

    correct = 0

    for path in paths:
        max_gy, positive_gy, negative_gy = get_features(path)

        if max_gy > 5.0:
            predicted = "downstroke"

        elif max_gy > 2.5 and positive_gy > 1.5 * negative_gy:
            predicted = "downstroke"

        else:
            predicted = "other"

        ok = predicted == true_label
        correct += int(ok)

        print(
            f"{path.name:25s} "
            f"maxGy={max_gy:5.2f} "
            f"+area={positive_gy:7.1f} "
            f"-area={negative_gy:7.1f} "
            f"pred={predicted:10s} "
            f"{'OK' if ok else 'WRONG'}"
        )

    return correct, len(paths)


print(f"Threshold = {THRESHOLD:.2f} rad/s")
print()

c1, n1 = evaluate_folder("test_data/downstroke", "downstroke")

print()

c2, n2 = evaluate_folder("test_data/other", "other")

print()
print("--------------------")

correct = c1 + c2
total = n1 + n2

print(f"Accuracy: {correct}/{total} = {100*correct/total:.1f}%")