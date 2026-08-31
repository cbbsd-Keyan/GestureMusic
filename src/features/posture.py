import math
import statistics


# =========================
# 常量
# =========================

GRAVITY = 9.80665

# 加速度合量偏离重力超过该值视为"运动中"，
# 运动中的样本不可信，不参与姿态解算
STATIC_TOLERANCE = 1.5


def roll_pitch(v):

    """
    从单帧加速度解算姿态角（度）。
    v: [ax, ay, az, gx, gy, gz]
    """

    ax, ay, az = v[0], v[1], v[2]

    roll = math.atan2(ay, az)

    pitch = math.atan2(
        -ax,
        math.sqrt(ay * ay + az * az),
    )

    return (
        math.degrees(roll),
        math.degrees(pitch),
    )


def summarize_posture(uniform):

    """
    姿态统计：只采用准静态样本。
    剧烈运动段准静态样本不足时
    available=False，诚实告知下游不可用。
    """

    static_samples = []

    for v in uniform:

        a_mag = math.sqrt(
            v[0] * v[0]
            + v[1] * v[1]
            + v[2] * v[2]
        )

        if abs(a_mag - GRAVITY) < STATIC_TOLERANCE:
            static_samples.append(v)

    valid_ratio = (
        len(static_samples) / len(uniform)
        if uniform
        else 0.0
    )

    if len(static_samples) < 30:

        return {
            "available": False,
            "valid_ratio": round(valid_ratio, 3),
            "roll_median": None,
            "roll_range": None,
            "pitch_median": None,
        }

    rolls = []
    pitches = []

    for v in static_samples:

        r, p = roll_pitch(v)

        rolls.append(r)
        pitches.append(p)

    rolls.sort()
    pitches.sort()

    def percentile(sorted_vals, q):

        idx = int(q * (len(sorted_vals) - 1))

        return sorted_vals[idx]

    roll_med = statistics.median(rolls)

    # 以中位数为基准展开，消除 ±180° 环绕伪影
    centered = [
        ((r - roll_med + 180.0) % 360.0) - 180.0
        for r in rolls
    ]

    centered.sort()

    roll_range = (
        percentile(centered, 0.9)
        - percentile(centered, 0.1)
    )

    return {
        "available": True,
        "valid_ratio": round(valid_ratio, 3),
        "roll_median": round(
            statistics.median(rolls), 1
        ),
        "roll_range": round(roll_range, 1),
        "pitch_median": round(
            statistics.median(pitches), 1
        ),
    }
