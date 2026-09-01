import math
import statistics


# =========================
# 常量
# =========================

MIN_BPM = 30.0
MAX_BPM = 180.0


# =========================
# 工具
# =========================

def smooth(values, window):

    half = window // 2

    n = len(values)

    out = []

    for i in range(n):

        lo = max(0, i - half)
        hi = min(n, i + half + 1)

        out.append(
            statistics.fmean(values[lo:hi])
        )

    return out


def gyro_mag(v):

    return math.sqrt(
        v[3] * v[3]
        + v[4] * v[4]
        + v[5] * v[5]
    )


# =========================
# 自相关法
# =========================

def autocorr_tempo(series, hz):

    """
    series: 去均值后的信号
    返回 (bpm, 归一化相关强度 0~1) 或 (None, 0)
    """

    n = len(series)

    lag_lo = max(
        2,
        int(hz * 60.0 / MAX_BPM),
    )

    lag_hi = min(
        n // 3,
        int(hz * 60.0 / MIN_BPM),
    )

    if lag_hi <= lag_lo + 2:
        return None, 0.0

    mean = statistics.fmean(series)

    x = [s - mean for s in series]

    r0 = sum(v * v for v in x)

    if r0 <= 0:
        return None, 0.0

    best_lag = None
    best_r = 0.0

    rs = {}

    for lag in range(lag_lo, lag_hi + 1):

        r = sum(
            x[i] * x[i + lag]
            for i in range(n - lag)
        )

        rs[lag] = r

        if r > best_r:
            best_r = r
            best_lag = lag

    if best_lag is None:
        return None, 0.0

    # 抛物线插值细化
    y0 = rs[best_lag]
    yA = rs.get(best_lag - 1, y0)
    yB = rs.get(best_lag + 1, y0)

    denom = yA - 2 * y0 + yB

    delta = 0.0

    if denom != 0:
        delta = 0.5 * (yA - yB) / denom

        if abs(delta) > 1:
            delta = 0.0

    lag_refined = best_lag + delta

    bpm = 60.0 * hz / lag_refined

    strength = best_r / r0

    return bpm, strength


# =========================
# 峰值间隔法
# =========================

def peak_tempo(mags, hz):

    """
    mags: 陀螺合量序列
    返回 (bpm, 有效间隔数, 间隔规整度)
    规整度 = 1 - stdev/median，越接近1越稳
    """

    s = smooth(mags, 10)

    n = len(s)

    mean = statistics.fmean(s)
    std = statistics.pstdev(s)

    if std <= 0:
        return None, 0, 0.0

    threshold = mean + 0.5 * std

    min_gap = max(
        2,
        int(hz * 60.0 / MAX_BPM * 0.8),
    )

    peaks = []

    last_peak = -10 * min_gap

    for i in range(1, n - 1):

        if (
            s[i] >= s[i - 1]
            and s[i] > s[i + 1]
            and s[i] > threshold
            and i - last_peak >= min_gap
        ):

            peaks.append(i)
            last_peak = i

    if len(peaks) < 3:
        return None, len(peaks), 0.0

    intervals = [
        b - a for a, b in zip(peaks, peaks[1:])
    ]

    lag_lo = hz * 60.0 / MAX_BPM
    lag_hi = hz * 60.0 / MIN_BPM

    valid = [
        iv
        for iv in intervals
        if lag_lo * 0.8 <= iv <= lag_hi * 1.2
    ]

    if len(valid) < 2:
        return None, len(peaks), 0.0

    med = statistics.median(valid)

    std_iv = statistics.pstdev(valid)

    regularity = max(
        0.0,
        1.0 - std_iv / med,
    )

    bpm = 60.0 * hz / med

    return bpm, len(peaks), regularity


# =========================
# 主入口
# =========================

def estimate_tempo(uniform, hz=100.0):

    """
    uniform: 重采样后的样本列表
    返回 dict: bpm / confidence / method
    """

    mags = [gyro_mag(v) for v in uniform]

    if len(mags) < int(hz * 5):
        return {
            "bpm": None,
            "confidence": "low",
            "method": "样本不足",
        }

    ac_bpm, strength = autocorr_tempo(
        mags,
        hz,
    )

    pk_bpm, peak_count, regularity = peak_tempo(
        mags,
        hz,
    )

    # ---------- 贴底自首 ----------

    # 估计值贴着最低BPM说明自相关峰落在
    # 最大滞后边界上，多为伪峰
    FLOOR_BPM = 40.0

    if ac_bpm is not None and ac_bpm < FLOOR_BPM:
        ac_bpm = None
        strength = min(strength, 0.2)

    if pk_bpm is not None and pk_bpm < FLOOR_BPM:
        pk_bpm = None
        regularity = 0.0

    # ---------- 决策 ----------

    agree = (
        ac_bpm is not None
        and pk_bpm is not None
        and abs(ac_bpm - pk_bpm)
        / max(ac_bpm, pk_bpm)
        < 0.15
    )

    if strength >= 0.45 and (agree or regularity > 0.6):

        return {
            "bpm": round(ac_bpm, 1),
            "confidence": "high",
            "method": "autocorr",
            "strength": round(strength, 3),
            "peak_bpm": (
                round(pk_bpm, 1)
                if pk_bpm
                else None
            ),
        }

    if strength >= 0.25 or (
        pk_bpm and regularity > 0.7
    ):

        bpm = (
            ac_bpm if strength >= 0.25 else pk_bpm
        )

        return {
            "bpm": round(bpm, 1),
            "confidence": "medium",
            "method": (
                "autocorr"
                if strength >= 0.25
                else "peaks"
            ),
            "strength": round(strength, 3),
            "regularity": round(regularity, 3),
        }

    return {
        "bpm": None,
        "confidence": "low",
        "method": "none",
        "strength": round(strength, 3),
        "peak_bpm": (
            round(pk_bpm, 1) if pk_bpm else None
        ),
    }
