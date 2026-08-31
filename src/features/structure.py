import math
import statistics


# =========================
# 常量
# =========================

# 滑窗长度（秒）
WINDOW_S = 1.0

# 相邻窗口能量比超过该倍数视为突变
RATIO_THRESHOLD = 1.8

# 最多报告几个突变点
MAX_POINTS = 3


def gyro_mag(v):

    return math.sqrt(
        v[3] * v[3]
        + v[4] * v[4]
        + v[5] * v[5]
    )


def detect_change_points(uniform, hz=100.0):

    """
    滑动窗口能量突变检测。
    返回突变时间列表（秒，最多3个）。
    用于乐段切分；检测不到返回空列表。
    """

    mags = [gyro_mag(v) for v in uniform]

    w = int(hz * WINDOW_S)

    step = max(1, w // 2)

    if len(mags) < w * 3:
        return []

    rms_series = []

    i = 0

    while i + w <= len(mags):

        seg = mags[i : i + w]

        rms_series.append(
            math.sqrt(
                statistics.fmean(
                    x * x for x in seg
                )
            )
        )

        i += step

    if len(rms_series) < 4:
        return []

    candidates = []

    # 跳过首尾窗口：录音的开始/停止动作
    # 不算乐段突变
    for j in range(2, len(rms_series) - 1):

        a = rms_series[j - 1]
        b = rms_series[j]

        if a <= 0 or b <= 0:
            continue

        ratio = max(a / b, b / a)

        if ratio >= RATIO_THRESHOLD:

            candidates.append(
                (j * step + w / 2) / hz
            )

    if not candidates:
        return []

    # 合并相邻突变点（间隔<1.5s 视为同一个）
    merged = [candidates[0]]

    for t in candidates[1:]:

        if t - merged[-1] >= 1.5:
            merged.append(t)

    return [
        round(t, 1) for t in merged[:MAX_POINTS]
    ]
