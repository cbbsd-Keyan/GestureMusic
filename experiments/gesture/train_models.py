import csv
from pathlib import Path
import statistics

from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    classification_report
)


AXES = ["ax", "ay", "az", "gx", "gy", "gz"]

FEATURE_TYPES = [
    "max",
    "min",
    "range",
    "mean",
    "std",
    "mean_abs",
    "positive_mean",
    "negative_mean",
    "positive_ratio",
    "negative_ratio",
]

FEATURE_NAMES = [
    f"{axis}_{feature}"
    for axis in AXES
    for feature in FEATURE_TYPES
]


def load_csv(path):
    data = {axis: [] for axis in AXES}

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            for axis in AXES:
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


def extract_features(path):
    d = load_csv(path)

    features = []

    # 六个轴分别提统计特征
    for axis in AXES:
        features.extend(axis_features(d[axis]))

    return features


def load_dataset(base_dir):
    X = []
    y = []
    names = []

    for label in ["downstroke", "other"]:
        folder = Path(base_dir) / label

        for path in sorted(folder.glob("*.csv")):
            X.append(extract_features(path))
            y.append(label)
            names.append(path.name)

    return X, y, names


# ------------------------
# 载入数据
# ------------------------

X_train, y_train, train_names = load_dataset("data")
X_test, y_test, test_names = load_dataset("test_data")

print(f"Training samples: {len(X_train)}")
print(f"Test samples:     {len(X_test)}")
print()


# ------------------------
# 模型
# ------------------------

svm = make_pipeline(
    StandardScaler(),
    SVC(kernel="rbf", C=1.0, gamma="scale")
)

rf = RandomForestClassifier(
    n_estimators=300,
    random_state=42,
    class_weight="balanced"
)

models = {
    "SVM": svm,
    "Random Forest": rf
}


# ------------------------
# 训练集交叉验证
# ------------------------

cv = StratifiedKFold(
    n_splits=4,
    shuffle=True,
    random_state=42
)

print("=== Cross-validation on training data ===")

for name, model in models.items():
    scores = cross_val_score(
        model,
        X_train,
        y_train,
        cv=cv,
        scoring="accuracy"
    )

    print(
        f"{name:15s}: "
        f"{scores.mean() * 100:5.1f}% "
        f"(folds: {[round(x * 100, 1) for x in scores]})"
    )

print()


# ------------------------
# 独立测试集
# ------------------------

for name, model in models.items():

    print("=" * 60)
    print(name)
    print("=" * 60)

    model.fit(X_train, y_train)

    if name == "Random Forest":
        importances = model.feature_importances_

        ranked = sorted(
            zip(FEATURE_NAMES, importances),
            key=lambda x: x[1],
            reverse=True
        )

        print()
        print("Top 15 feature importances:")

        for feature, importance in ranked[:15]:
            print(
                f"{feature:25s} "
                f"{importance:.4f}"
            )

        print()

    pred = model.predict(X_test)

    for filename, true, predicted in zip(
        test_names, y_test, pred
    ):
        result = "OK" if true == predicted else "WRONG"

        print(
            f"{filename:25s} "
            f"true={true:10s} "
            f"pred={predicted:10s} "
            f"{result}"
        )

    accuracy = accuracy_score(y_test, pred)

    print()
    print(
        f"Test accuracy: "
        f"{accuracy * 100:.1f}% "
        f"({sum(a == b for a, b in zip(y_test, pred))}/{len(y_test)})"
    )

    print()
    print("Confusion matrix:")
    print(
        confusion_matrix(
            y_test,
            pred,
            labels=["downstroke", "other"]
        )
    )

    print()
    print("Classification report:")
    print(
        classification_report(
            y_test,
            pred,
            digits=3
        )
    )