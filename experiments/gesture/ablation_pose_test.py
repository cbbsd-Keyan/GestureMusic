import csv
import statistics
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import accuracy_score


def load_csv(path):
    data = {
        "ax": [], "ay": [], "az": [],
        "gx": [], "gy": [], "gz": []
    }

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            for axis in data:
                data[axis].append(float(row[axis]))

    return data


def axis_features(values):
    positives = [x for x in values if x > 0]
    negatives = [-x for x in values if x < 0]

    return [
        max(values),
        min(values),
        max(values) - min(values),
        statistics.mean(values),
        statistics.pstdev(values),
        statistics.mean(abs(x) for x in values),

        statistics.mean(positives) if positives else 0.0,
        statistics.mean(negatives) if negatives else 0.0,

        len(positives) / len(values),
        len(negatives) / len(values),
    ]


def extract_features(path, axes):
    data = load_csv(path)

    features = []

    for axis in axes:
        features.extend(axis_features(data[axis]))

    return features


def load_dataset(base_dir, axes):
    X = []
    y = []

    for label in ["downstroke", "other"]:
        folder = Path(base_dir) / label

        for path in sorted(folder.glob("*.csv")):
            X.append(extract_features(path, axes))
            y.append(label)

    return X, y


feature_sets = {
    "gy only": ["gy"],
    "gy + gz": ["gy", "gz"],
    "gyro only": ["gx", "gy", "gz"],
    "accel only": ["ax", "ay", "az"],
    "all six axes": ["ax", "ay", "az", "gx", "gy", "gz"],
}


cv = StratifiedKFold(
    n_splits=4,
    shuffle=True,
    random_state=42
)


print(
    f"{'Feature set':15s} "
    f"{'CV':>8s} "
    f"{'Validation':>12s}"
)

print("-" * 40)


for name, axes in feature_sets.items():

    X_train, y_train = load_dataset("data", axes)
    X_val, y_val = load_dataset("pose_test", axes)

    model = RandomForestClassifier(
        n_estimators=300,
        random_state=42,
        class_weight="balanced"
    )

    scores = cross_val_score(
        model,
        X_train,
        y_train,
        cv=cv,
        scoring="accuracy"
    )

    model.fit(X_train, y_train)

    pred = model.predict(X_val)

    cv_accuracy = scores.mean()
    val_accuracy = accuracy_score(y_val, pred)

    print(
        f"{name:15s} "
        f"{cv_accuracy * 100:7.1f}% "
        f"{val_accuracy * 100:11.1f}%"
    )