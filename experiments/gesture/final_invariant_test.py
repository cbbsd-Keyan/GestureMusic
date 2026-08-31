import csv
import math
import statistics
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import accuracy_score, confusion_matrix


RAW_AXES = ["ax", "ay", "az", "gx", "gy", "gz"]


def load_csv(path):
    data = {axis: [] for axis in RAW_AXES}

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            for axis in RAW_AXES:
                data[axis].append(float(row[axis]))

    return data


def add_derived_channels(data):
    n = len(data["ax"])

    # ------------------------------
    # 1. 用动作窗口最前面一小段估计“向上”方向
    # ------------------------------
    k = min(20, max(5, n // 5))

    ux = statistics.mean(data["ax"][:k])
    uy = statistics.mean(data["ay"][:k])
    uz = statistics.mean(data["az"][:k])

    norm_u = math.sqrt(ux * ux + uy * uy + uz * uz)

    if norm_u > 1e-6:
        ux /= norm_u
        uy /= norm_u
        uz /= norm_u

    # 棒的长轴近似是 MPU 的 +X
    #
    # n_axis = X × Up
    #
    # X = (1, 0, 0)
    # Up = (ux, uy, uz)
    #
    # 所以：
    # n_axis = (0, -uz, uy)

    ny = -uz
    nz = uy

    norm_n = math.sqrt(ny * ny + nz * nz)

    if norm_n < 1e-6:
        ny = 1.0
        nz = 0.0
    else:
        ny /= norm_n
        nz /= norm_n

    pitch_rate = []
    gyro_perp = []
    gyro_mag = []
    accel_mag = []
    accel_perp = []

    for i in range(n):
        ax = data["ax"][i]
        ay = data["ay"][i]
        az = data["az"][i]

        gx = data["gx"][i]
        gy = data["gy"][i]
        gz = data["gz"][i]

        # 相对于重力方向定义的“上下挥”角速度
        pitch = gy * ny + gz * nz

        pitch_rate.append(pitch)

        # 与棒自身 X 轴垂直的角速度大小
        gyro_perp.append(
            math.sqrt(gy * gy + gz * gz)
        )

        # 总角速度
        gyro_mag.append(
            math.sqrt(gx * gx + gy * gy + gz * gz)
        )

        # 总加速度
        accel_mag.append(
            math.sqrt(ax * ax + ay * ay + az * az)
        )

        # 垂直于棒长轴的加速度大小
        accel_perp.append(
            math.sqrt(ay * ay + az * az)
        )

    derived = {
        "pitch_rate": pitch_rate,
        "gyro_perp": gyro_perp,
        "gyro_mag": gyro_mag,
        "accel_mag": accel_mag,
        "accel_perp": accel_perp,
    }

    return derived


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


def extract_features(path, mode):
    raw = load_csv(path)
    derived = add_derived_channels(raw)

    features = []

    if mode == "raw":
        for axis in RAW_AXES:
            features.extend(axis_features(raw[axis]))

    elif mode == "invariant":
        # gx = 绕棒自身扭转
        features.extend(axis_features(raw["gx"]))

        for channel in [
            "pitch_rate",
            "gyro_perp",
            "gyro_mag",
            "accel_mag",
            "accel_perp",
        ]:
            features.extend(axis_features(derived[channel]))

    elif mode == "combined":
        for axis in RAW_AXES:
            features.extend(axis_features(raw[axis]))

        for channel in [
            "pitch_rate",
            "gyro_perp",
            "gyro_mag",
            "accel_mag",
            "accel_perp",
        ]:
            features.extend(axis_features(derived[channel]))

    return features


def load_multiple_datasets(base_dirs, mode):
    X = []
    y = []

    for base_dir in base_dirs:
        for label in ["downstroke", "other"]:
            folder = Path(base_dir) / label

            for path in sorted(folder.glob("*.csv")):
                X.append(extract_features(path, mode))
                y.append(label)

    return X, y


def load_single_dataset(base_dir, mode):
    return load_multiple_datasets([base_dir], mode)


feature_modes = {
    "invariant": "invariant",
}


# 训练集：
# 原始 data + 刚才故意改变姿态录的 pose_test
TRAIN_DIRS = [
    "data",
    "pose_test"
]

# test_data 已经不是“最终测试集”，
# 现在只作为开发阶段 validation
VAL_DIR = "generalization_test"


cv = StratifiedKFold(
    n_splits=4,
    shuffle=True,
    random_state=42
)


print("Training folders:", TRAIN_DIRS)
print("Validation folder:", VAL_DIR)
print()

print(
    f"{'Feature set':18s} "
    f"{'CV':>8s} "
    f"{'Validation':>12s}"
)

print("-" * 42)


for display_name, mode in feature_modes.items():

    X_train, y_train = load_multiple_datasets(
        TRAIN_DIRS,
        mode
    )

    X_val, y_val = load_single_dataset(
        VAL_DIR,
        mode
    )

    model = RandomForestClassifier(
        n_estimators=500,
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
    proba = model.predict_proba(X_val)

    down_idx = list(model.classes_).index("downstroke")
    other_idx = list(model.classes_).index("other")

    cv_acc = scores.mean()
    val_acc = accuracy_score(y_val, pred)

    print(
        f"{display_name:18s} "
        f"{cv_acc * 100:7.1f}% "
        f"{val_acc * 100:11.1f}%"
    )


# ------------------------------
# 输出 invariant 的详细结果
# ------------------------------

X_train, y_train = load_multiple_datasets(
    TRAIN_DIRS,
    "invariant"
)

X_val, y_val = load_single_dataset(
    VAL_DIR,
    "invariant"
)

model = RandomForestClassifier(
    n_estimators=500,
    random_state=42,
    class_weight="balanced"
)

model.fit(X_train, y_train)

pred = model.predict(X_val)

print()
print("=== Invariant detailed results ===")

names = []

for label in ["downstroke", "other"]:
    folder = Path(VAL_DIR) / label

    for path in sorted(folder.glob("*.csv")):
        names.append(path.name)

for i, (filename, true, predicted) in enumerate(
    zip(names, y_val, pred)
):
    result = "OK" if true == predicted else "WRONG"

    p_down = proba[i][down_idx]
    p_other = proba[i][other_idx]

    print(
        f"{filename:25s} "
        f"true={true:10s} "
        f"pred={predicted:10s} "
        f"P(down)={p_down:5.2f} "
        f"P(other)={p_other:5.2f} "
        f"{result}"
    )

print()
print("Invariant confusion matrix:")

print(
    confusion_matrix(
        y_val,
        pred,
        labels=["downstroke", "other"]
    )
)

correct = sum(a == b for a, b in zip(y_val, pred))

print()
print(
    f"Accuracy: {correct}/{len(y_val)} "
    f"= {100 * correct / len(y_val):.1f}%"
)