import socket
import math
import statistics
from collections import deque

import joblib
import numpy as np
import sounddevice as sd


# ============================================================
# 基本参数
# ============================================================

UDP_IP = "0.0.0.0"
UDP_PORT = 4210

SAMPLE_RATE = 44100

NOTE_FREQ = {
    "C4": 261.63,
    "D4": 293.66,
    "E4": 329.63,
    "G4": 392.00,
    "A4": 440.00,
}


# ============================================================
# 1. 加载 RF 模型
# ============================================================

obj = joblib.load("gesture_rf_v2.pkl")

if hasattr(obj, "predict_proba"):
    model = obj

elif isinstance(obj, dict):
    model = None

    for key in ["model", "classifier", "rf"]:
        if key in obj and hasattr(obj[key], "predict_proba"):
            model = obj[key]
            break

    if model is None:
        raise RuntimeError(
            f"gesture_rf_v2.pkl 是 dict，但找不到模型。"
            f"keys={list(obj.keys())}"
        )

else:
    raise RuntimeError(
        f"无法识别 pkl 内容，type={type(obj)}"
    )


print("Model loaded.")
print("Classes:", model.classes_)


# ============================================================
# 2. 音频
# ============================================================

def play_note(note, duration=0.28, volume=0.25):
    freq = NOTE_FREQ[note]

    t = np.linspace(
        0,
        duration,
        int(SAMPLE_RATE * duration),
        endpoint=False
    )

    wave = np.sin(
        2 * np.pi * freq * t
    )

    attack = max(
        1,
        int(0.02 * SAMPLE_RATE)
    )

    release = max(
        1,
        int(0.08 * SAMPLE_RATE)
    )

    envelope = np.ones_like(wave)

    envelope[:attack] = np.linspace(
        0,
        1,
        attack
    )

    envelope[-release:] = np.linspace(
        1,
        0,
        release
    )

    wave = volume * wave * envelope

    # 不 wait，避免阻塞 UDP
    sd.play(
        wave,
        SAMPLE_RATE
    )


# ============================================================
# 3. 倾斜 -> 音符
# ============================================================

current_note = "E4"
locked_note = "E4"


# ------------------------------------------------------------
# 五音基础边界
#
# C       D          E          G       A
#    -30       -10       +10       +30
# ------------------------------------------------------------

OUTER_ANGLE = 30.0
INNER_ANGLE = 10.0


# ------------------------------------------------------------
# 滞回
# ------------------------------------------------------------

HYST = 1.5


# ------------------------------------------------------------
# 姿态可信度
# ------------------------------------------------------------

POSE_GYRO_LIMIT = 0.8

ACCEL_MIN = 8.5
ACCEL_MAX = 11.5

# 原来 8 帧，现在稍微缩短，让选音响应快一点
POSE_WINDOW = 6

POSE_MAX_RANGE = 4.0

stable_rolls = deque(
    maxlen=POSE_WINDOW
)


def base_note_from_roll(roll):
    """
    不考虑历史状态，
    单纯按照当前 roll 所在区间判断音符。
    """

    if roll < -OUTER_ANGLE:
        return "C4"

    elif roll < -INNER_ANGLE:
        return "D4"

    elif roll < INNER_ANGLE:
        return "E4"

    elif roll < OUTER_ANGLE:
        return "G4"

    else:
        return "A4"


def update_note_from_roll(roll):
    """
    带滞回的音高选择。

    与旧版最大区别：
    不再规定一次只能跳相邻音。

    例如：
    当前 A4，但 roll 已经回到 +5°
    可以直接 A4 -> E4，
    不需要 A -> G -> E。
    """

    global current_note


    # ========================================================
    # 当前 C4
    # ========================================================

    if current_note == "C4":

        # 基础 C 区：roll < -30
        #
        # 进入 C 后，允许稍微回一点，
        # 到 -28.5 以前仍保持 C。
        if roll < -OUTER_ANGLE + HYST:
            return current_note


    # ========================================================
    # 当前 D4
    # ========================================================

    elif current_note == "D4":

        # 基础 D 区：-30 ~ -10
        #
        # 保持区：
        # -31.5 ~ -8.5
        if (
            -OUTER_ANGLE - HYST
            <= roll
            < -INNER_ANGLE + HYST
        ):
            return current_note


    # ========================================================
    # 当前 E4
    # ========================================================

    elif current_note == "E4":

        # 基础 E 区：-10 ~ +10
        #
        # 保持区：
        # -11.5 ~ +11.5
        if (
            -INNER_ANGLE - HYST
            <= roll
            < INNER_ANGLE + HYST
        ):
            return current_note


    # ========================================================
    # 当前 G4
    # ========================================================

    elif current_note == "G4":

        # 基础 G 区：+10 ~ +30
        #
        # 保持区：
        # +8.5 ~ +31.5
        if (
            INNER_ANGLE - HYST
            <= roll
            < OUTER_ANGLE + HYST
        ):
            return current_note


    # ========================================================
    # 当前 A4
    # ========================================================

    elif current_note == "A4":

        # 基础 A 区：roll >= +30
        #
        # 进入 A 后，
        # 低于 +28.5 才离开。
        if roll >= OUTER_ANGLE - HYST:
            return current_note


    # ========================================================
    # 已经离开当前音符保持区
    #
    # 直接按照实际角度重新判断。
    #
    # 所以可以：
    # A -> E
    # A -> D
    # C -> G
    # 等等
    # ========================================================

    current_note = base_note_from_roll(
        roll
    )

    return current_note


# ============================================================
# 4. 与 final_invariant_test.py 相同的特征
# ============================================================

def add_derived_channels(data):
    n = len(data["ax"])

    k = min(
        20,
        max(5, n // 5)
    )

    ux = statistics.mean(
        data["ax"][:k]
    )

    uy = statistics.mean(
        data["ay"][:k]
    )

    uz = statistics.mean(
        data["az"][:k]
    )

    norm_u = math.sqrt(
        ux * ux
        + uy * uy
        + uz * uz
    )

    if norm_u > 1e-6:
        ux /= norm_u
        uy /= norm_u
        uz /= norm_u


    # 棒长轴近似 MPU +X
    ny = -uz
    nz = uy

    norm_n = math.sqrt(
        ny * ny
        + nz * nz
    )

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


        # 相对于重力方向的上下挥角速度
        pitch = (
            gy * ny
            + gz * nz
        )

        pitch_rate.append(
            pitch
        )


        gyro_perp.append(
            math.sqrt(
                gy * gy
                + gz * gz
            )
        )


        gyro_mag.append(
            math.sqrt(
                gx * gx
                + gy * gy
                + gz * gz
            )
        )


        accel_mag.append(
            math.sqrt(
                ax * ax
                + ay * ay
                + az * az
            )
        )


        accel_perp.append(
            math.sqrt(
                ay * ay
                + az * az
            )
        )


    return {
        "pitch_rate": pitch_rate,
        "gyro_perp": gyro_perp,
        "gyro_mag": gyro_mag,
        "accel_mag": accel_mag,
        "accel_perp": accel_perp,
    }


def axis_features(values):
    positives = [
        x
        for x in values
        if x > 0
    ]

    negatives = [
        -x
        for x in values
        if x < 0
    ]


    return [
        max(values),

        min(values),

        max(values) - min(values),

        statistics.mean(values),

        statistics.pstdev(values),

        statistics.mean(
            abs(x)
            for x in values
        ),

        statistics.mean(positives)
        if positives
        else 0.0,

        statistics.mean(negatives)
        if negatives
        else 0.0,

        len(positives) / len(values),

        len(negatives) / len(values),
    ]


def extract_invariant_features(data):
    derived = add_derived_channels(
        data
    )

    features = []

    features.extend(
        axis_features(
            data["gx"]
        )
    )


    for channel in [
        "pitch_rate",
        "gyro_perp",
        "gyro_mag",
        "accel_mag",
        "accel_perp",
    ]:

        features.extend(
            axis_features(
                derived[channel]
            )
        )


    return features


# ============================================================
# 5. 实时动作状态机
# ============================================================

AXES = [
    "ax",
    "ay",
    "az",
    "gx",
    "gy",
    "gz",
]


PRE_SAMPLES = 20

MIN_WINDOW = 60

MAX_WINDOW = 150


# 比最开始的 1.5 低，
# 允许比较轻的演奏动作进入检测
START_GYRO_PERP = 1.0


QUIET_GYRO_PERP = 0.8

QUIET_FRAMES_REQUIRED = 12


# 先保持 0.50
DOWN_THRESHOLD = 0.59


pre_buffer = deque(
    maxlen=PRE_SAMPLES
)

recording = False

action_window = []

quiet_frames = 0


# ============================================================
# 6. 启动保护
#
# 程序启动后：
#
# 1. 先等待用户拿起棒子
# 2. 拿起过程中绝不识别 gesture
# 3. 拿稳以后才进入 READY
# ============================================================

armed = False

startup_motion_seen = False


def samples_to_data(samples):
    data = {
        axis: []
        for axis in AXES
    }

    for sample in samples:

        for axis in AXES:

            data[axis].append(
                sample[axis]
            )

    return data


def classify_action(samples):
    data = samples_to_data(
        samples
    )

    features = extract_invariant_features(
        data
    )

    X = [features]

    probabilities = model.predict_proba(
        X
    )[0]

    down_idx = list(
        model.classes_
    ).index(
        "downstroke"
    )

    p_down = probabilities[
        down_idx
    ]

    predicted = (
        "downstroke"
        if p_down >= DOWN_THRESHOLD
        else "other"
    )

    return (
        predicted,
        p_down
    )


# ============================================================
# 7. UDP
# ============================================================

sock = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM
)

sock.bind(
    (
        UDP_IP,
        UDP_PORT
    )
)


print()
print(
    "Realtime Melody Orbit started."
)

print(
    "Pick up the wand, then hold it still."
)

print(
    "Gesture recognition will start after READY."
)

print()


last_print_note = None


# ============================================================
# 8. 主循环
# ============================================================

while True:

    packet, addr = sock.recvfrom(
        1024
    )

    try:

        values = list(
            map(
                float,
                packet.decode()
                .strip()
                .split(",")
            )
        )


        # timestamp, ax, ay, az, gx, gy, gz
        if len(values) < 7:
            continue


        (
            timestamp,
            ax,
            ay,
            az,
            gx,
            gy,
            gz
        ) = values[:7]


        sample = {
            "ax": ax,
            "ay": ay,
            "az": az,
            "gx": gx,
            "gy": gy,
            "gz": gz,
        }


        # ====================================================
        # A. 当前运动程度
        # ====================================================

        gyro_perp = math.sqrt(
            gy * gy
            + gz * gz
        )


        accel_mag = math.sqrt(
            ax * ax
            + ay * ay
            + az * az
        )


        # ====================================================
        # B. roll
        # ====================================================

        roll = math.degrees(
            math.atan2(
                ay,
                az
            )
        )


        # ====================================================
        # C. 启动阶段先检测“拿起棒子”
        #
        # 不只看 gyro：
        # 如果平移拿起导致线性加速度明显偏离 g，
        # 也认为用户已经开始拿棒子。
        # ====================================================

        if not armed:

            if (
                gyro_perp > START_GYRO_PERP
                or accel_mag < ACCEL_MIN
                or accel_mag > ACCEL_MAX
            ):
                startup_motion_seen = True


        # ====================================================
        # D. 判断姿态是否可信
        # ====================================================

        pose_trustworthy = (
            not recording
            and gyro_perp < POSE_GYRO_LIMIT
            and ACCEL_MIN < accel_mag < ACCEL_MAX
        )


        if pose_trustworthy:

            stable_rolls.append(
                roll
            )

        else:

            stable_rolls.clear()


        # ====================================================
        # E. 连续稳定后才更新音高
        # ====================================================

        if len(stable_rolls) == POSE_WINDOW:

            roll_range = (
                max(stable_rolls)
                - min(stable_rolls)
            )


            if roll_range < POSE_MAX_RANGE:

                stable_roll = statistics.mean(
                    stable_rolls
                )


                # ============================================
                # 还没 READY
                # ============================================

                if not armed:

                    # 必须先经历过一次“拿起运动”
                    # 然后重新稳定下来
                    if startup_motion_seen:

                        armed = True

                        current_note = (
                            base_note_from_roll(
                                stable_roll
                            )
                        )

                        locked_note = current_note

                        last_print_note = (
                            current_note
                        )

                        pre_buffer.clear()

                        print(
                            f"[READY] "
                            f"roll={stable_roll:+6.1f}° "
                            f"-> {current_note}"
                        )


                # ============================================
                # 已经 READY
                # ============================================

                else:

                    note = update_note_from_roll(
                        stable_roll
                    )


                    if note != last_print_note:

                        print(
                            f"[SELECT] "
                            f"roll={stable_roll:+6.1f}° "
                            f"-> {note}"
                        )

                        last_print_note = note


        # ====================================================
        # F. 没 READY 之前绝对不进入动作检测
        # ====================================================

        if not armed:
            continue


        # ====================================================
        # G. 动作检测
        # ====================================================

        if not recording:

            # 保存动作开始前的数据
            pre_buffer.append(
                sample
            )


            # ------------------------------------------------
            # 出现明显运动
            # ------------------------------------------------

            if (
                len(pre_buffer) == PRE_SAMPLES
                and gyro_perp > START_GYRO_PERP
            ):

                recording = True


                # --------------------------------------------
                # 锁定当前音符
                # --------------------------------------------

                locked_note = current_note

                print(
                    f"[LOCK] "
                    f"{locked_note}"
                )


                stable_rolls.clear()


                # --------------------------------------------
                # 把运动前的数据也放入窗口
                # --------------------------------------------

                action_window = list(
                    pre_buffer
                )

                quiet_frames = 0


        # ====================================================
        # H. 正在记录动作
        # ====================================================

        else:

            action_window.append(
                sample
            )


            if gyro_perp < QUIET_GYRO_PERP:

                quiet_frames += 1

            else:

                quiet_frames = 0


            enough_data = (
                len(action_window)
                >= MIN_WINDOW
            )


            movement_finished = (
                quiet_frames
                >= QUIET_FRAMES_REQUIRED
            )


            too_long = (
                len(action_window)
                >= MAX_WINDOW
            )


            # =================================================
            # 动作结束 -> 分类
            # =================================================

            if enough_data and (
                movement_finished
                or too_long
            ):

                (
                    predicted,
                    p_down
                ) = classify_action(
                    action_window
                )


                print(
                    f"[GESTURE] "
                    f"{predicted:10s} "
                    f"P(down)={p_down:.2f} "
                    f"samples="
                    f"{len(action_window)}"
                )


                # =============================================
                # downstroke -> 播放锁定的音
                # =============================================

                if predicted == "downstroke":

                    print(
                        f"        >>> PLAY "
                        f"{locked_note}"
                    )

                    play_note(
                        locked_note
                    )


                # =============================================
                # 恢复待机
                # =============================================

                recording = False

                action_window = []

                quiet_frames = 0

                pre_buffer.clear()

                stable_rolls.clear()


    except Exception as e:

        print(
            "ERROR:",
            e
        )