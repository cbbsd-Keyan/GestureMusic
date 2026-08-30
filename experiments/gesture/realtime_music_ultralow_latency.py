import socket
import math
import statistics
import time
import queue
from collections import deque

import numpy as np
import sounddevice as sd

try:
    import msvcrt
except ImportError:
    msvcrt = None


# ============================================================
# 0. 基本参数
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
# 1. 常驻低延迟音频流
# ============================================================

NOTE_DURATION = 0.20
NOTE_VOLUME = 0.25


def make_wave(
    freq,
    duration=NOTE_DURATION,
    volume=NOTE_VOLUME
):
    t = (
        np.arange(
            int(SAMPLE_RATE * duration),
            dtype=np.float32
        )
        / SAMPLE_RATE
    )

    wave = np.sin(
        2 * np.pi * freq * t
    ).astype(np.float32)

    # 很短的 attack，减少起音延迟感
    attack = max(
        1,
        int(0.002 * SAMPLE_RATE)
    )

    release = max(
        1,
        int(0.035 * SAMPLE_RATE)
    )

    envelope = np.ones_like(wave)

    envelope[:attack] = np.linspace(
        0,
        1,
        attack,
        dtype=np.float32
    )

    envelope[-release:] = np.linspace(
        1,
        0,
        release,
        dtype=np.float32
    )

    return (
        volume
        * wave
        * envelope
    ).astype(np.float32)


NOTE_WAVES = {
    note: make_wave(freq)
    for note, freq in NOTE_FREQ.items()
}

note_queue = queue.SimpleQueue()

active_wave = None
active_pos = 0


def audio_callback(
    outdata,
    frames,
    time_info,
    status
):
    global active_wave
    global active_pos

    newest = None

    while True:
        try:
            newest = note_queue.get_nowait()

        except queue.Empty:
            break

    if newest is not None:
        active_wave = newest
        active_pos = 0

    outdata.fill(0)

    if active_wave is None:
        return

    remaining = (
        len(active_wave)
        - active_pos
    )

    n = min(
        frames,
        remaining
    )

    if n > 0:
        outdata[:n, 0] = (
            active_wave[
                active_pos:
                active_pos + n
            ]
        )

        active_pos += n

    if active_pos >= len(active_wave):
        active_wave = None
        active_pos = 0


stream = sd.OutputStream(
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="float32",
    callback=audio_callback,
    latency="low",
    blocksize=0,
)

stream.start()


def play_note(note):
    note_queue.put(
        NOTE_WAVES[note]
    )


# ============================================================
# 2. 倾斜 -> 音符
# ============================================================

current_note = "E4"
locked_note = "E4"

OUTER_ANGLE = 30.0
INNER_ANGLE = 10.0
HYST = 1.5


def base_note_from_roll(roll):

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
    global current_note

    if current_note == "C4":

        if roll < -OUTER_ANGLE + HYST:
            return current_note

    elif current_note == "D4":

        if (
            -OUTER_ANGLE - HYST
            <= roll
            < -INNER_ANGLE + HYST
        ):
            return current_note

    elif current_note == "E4":

        if (
            -INNER_ANGLE - HYST
            <= roll
            < INNER_ANGLE + HYST
        ):
            return current_note

    elif current_note == "G4":

        if (
            INNER_ANGLE - HYST
            <= roll
            < OUTER_ANGLE + HYST
        ):
            return current_note

    elif current_note == "A4":

        if roll >= OUTER_ANGLE - HYST:
            return current_note

    current_note = (
        base_note_from_roll(
            roll
        )
    )

    return current_note


# ============================================================
# 3. 显式演奏模式
#
# 不再自动判断 READY。
#
# SPACE：
#     STANDBY -> ARMED
#     ARMED   -> STANDBY
#
# 用户自己负责：
#     拿好棒子 -> 按空格 -> 开始演奏
# ============================================================

armed = False

ARM_POSE_SAMPLES = 10

recent_accels = deque(
    maxlen=ARM_POSE_SAMPLES
)

recent_rolls = deque(
    maxlen=ARM_POSE_SAMPLES
)


# 当前根据姿态得到的“上下挥轴”
pitch_ny = 1.0
pitch_nz = 0.0

pitch_axis_valid = False


def calculate_pitch_axis(accel_samples):
    """
    根据当前棒子的稳定姿态计算上下挥的旋转轴。

    棒长轴近似 MPU +X。

    n = X × Up
      = (0, -uz, uy)
    """

    if len(accel_samples) < 3:
        return None

    ux = statistics.mean(
        a[0]
        for a in accel_samples
    )

    uy = statistics.mean(
        a[1]
        for a in accel_samples
    )

    uz = statistics.mean(
        a[2]
        for a in accel_samples
    )

    norm_u = math.sqrt(
        ux * ux
        + uy * uy
        + uz * uz
    )

    if norm_u < 1e-6:
        return None

    ux /= norm_u
    uy /= norm_u
    uz /= norm_u

    ny = -uz
    nz = uy

    norm_n = math.sqrt(
        ny * ny
        + nz * nz
    )

    if norm_n < 1e-6:
        return None

    ny /= norm_n
    nz /= norm_n

    return ny, nz


# ============================================================
# 4. 下挥检测器
#
# 结构：
#
# IDLE
#   ↓
# 检测到持续向下
#   ↓
# DOWN
#   ↓
# 时间 + 转角 + 峰值足够
#   ↓
# 确认是真正下挥
#   ↓
# 下挥减速 / 反向
#   ↓
# BEAT
#   ↓
# PLAY
#   ↓
# RETURN
#   ↓
# 明确向上 + 回到顶部附近
#   ↓
# IDLE
# ============================================================


# ------------------------------------------------------------
# 下挥方向
#
# 之前有效实验中：
# down_sign = +1
#
# 所以当前固定。
#
# 如果之后确定方向反了，只改这里：
#
# DOWN_SIGN = -1.0
# ------------------------------------------------------------

DOWN_SIGN = 1.0


# ------------------------------------------------------------
# pitch_rate 平滑
# ------------------------------------------------------------

RATE_SMOOTH_WINDOW = 3

pitch_rate_history = deque(
    maxlen=RATE_SMOOTH_WINDOW
)


# ------------------------------------------------------------
# 下挥开始
#
# 注意：
# 超过这里不会直接发音。
# 只是认为“一次可能的下挥开始了”。
# ------------------------------------------------------------

DOWN_START_RATE = 0.60
DOWN_START_CONFIRM_FRAMES = 3


# ------------------------------------------------------------
# 真正下挥的确认条件
#
# 至少：
#
# 50 ms
# 4°
# 峰值 1.2 rad/s
#
# 先略微宽松一点。
# 后面根据真实日志再调。
# ------------------------------------------------------------

MIN_DOWN_TIME = 0.050

MIN_DOWN_ANGLE = math.radians(
    4.0
)

MIN_DOWN_PEAK = 1.20


# 如果 0.4 秒还不像一次真正下挥，就取消
MAX_DOWN_TIME = 0.40


# ------------------------------------------------------------
# beat / 落点
#
# 下挥已经确认后，
# 当向下速度降低到接近 0，
# 认为到达 beat。
# ------------------------------------------------------------

BEAT_END_RATE = 0.20
BEAT_END_CONFIRM_FRAMES = 2


# ------------------------------------------------------------
# 回棒
# ------------------------------------------------------------

RETURN_RATE = 0.50
RETURN_CONFIRM_FRAMES = 2


# 回棒到顶部附近减速
REARM_NEUTRAL_RATE = 0.30
REARM_NEUTRAL_FRAMES = 2


# ------------------------------------------------------------
# 状态变量
# ------------------------------------------------------------

gesture_state = "IDLE"

start_frames = 0

down_elapsed = 0.0
down_area = 0.0
down_peak = 0.0

beat_end_frames = 0

return_seen = False
return_frames = 0

neutral_frames = 0

detector_prev_timestamp = None


def reset_detector():
    global gesture_state
    global start_frames

    global down_elapsed
    global down_area
    global down_peak

    global beat_end_frames

    global return_seen
    global return_frames
    global neutral_frames

    global detector_prev_timestamp

    gesture_state = "IDLE"

    start_frames = 0

    down_elapsed = 0.0
    down_area = 0.0
    down_peak = 0.0

    beat_end_frames = 0

    return_seen = False
    return_frames = 0

    neutral_frames = 0

    detector_prev_timestamp = None

    pitch_rate_history.clear()


# ============================================================
# 5. ARM / DISARM
# ============================================================

last_print_note = None


def arm_system():
    global armed

    global pitch_ny
    global pitch_nz
    global pitch_axis_valid

    global current_note
    global locked_note
    global last_print_note

    if len(recent_accels) < ARM_POSE_SAMPLES:

        print(
            "[ARM FAILED] "
            "Not enough IMU samples yet."
        )

        return


    axis = calculate_pitch_axis(
        recent_accels
    )

    if axis is None:

        print(
            "[ARM FAILED] "
            "Cannot determine pitch axis."
        )

        return


    pitch_ny, pitch_nz = axis

    pitch_axis_valid = True


    if recent_rolls:

        roll = statistics.mean(
            recent_rolls
        )

        current_note = (
            base_note_from_roll(
                roll
            )
        )

        locked_note = current_note

        last_print_note = (
            current_note
        )

    else:

        roll = 0.0


    reset_detector()

    armed = True


    print()
    print(
        "========== ARMED =========="
    )

    print(
        f"roll={roll:+.1f}° "
        f"note={current_note}"
    )

    print(
        f"pitch axis: "
        f"ny={pitch_ny:+.3f}, "
        f"nz={pitch_nz:+.3f}"
    )

    print(
        "Gesture detection ON."
    )

    print(
        "Press SPACE again to stop."
    )

    print(
        "==========================="
    )
    print()


def disarm_system():
    global armed

    armed = False

    reset_detector()

    print()
    print(
        "========= STANDBY ========="
    )

    print(
        "Gesture detection OFF."
    )

    print(
        "Hold the wand ready, "
        "then press SPACE to arm."
    )

    print(
        "==========================="
    )
    print()


# ============================================================
# 6. UDP
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


# ============================================================
# 7. UDP 诊断
# ============================================================

prev_device_ts = None
prev_host_arrival = None

burst_count = 0

last_burst_report = (
    time.perf_counter()
)


# ============================================================
# 启动提示
# ============================================================

print()

print(
    "Realtime Melody Orbit"
)

print(
    "Explicit Performance Mode"
)

print()

print(
    f"Audio output latency: "
    f"{stream.latency * 1000:.1f} ms"
)

print()

print(
    "SPACE : ARM / DISARM"
)

print(
    "T     : audio-only test"
)

print()

print(
    "Current mode: STANDBY"
)

print(
    "Hold the wand in your starting pose,"
)

print(
    "then press SPACE."
)

print()


# ============================================================
# 8. 主循环
# ============================================================

try:

    while True:

        packet, addr = sock.recvfrom(
            1024
        )

        host_arrival = (
            time.perf_counter()
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


            # ====================================================
            # A. 当前基本量
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

            roll = math.degrees(
                math.atan2(
                    ay,
                    az
                )
            )


            # ====================================================
            # B. 无论是否 ARMED，
            # 都保存最近姿态。
            #
            # 用户按 SPACE 的一刻，
            # 就用这些数据初始化系统。
            # ====================================================

            recent_accels.append(
                (
                    ax,
                    ay,
                    az
                )
            )

            recent_rolls.append(
                roll
            )


            # ====================================================
            # C. 键盘
            # ====================================================

            if (
                msvcrt is not None
                and msvcrt.kbhit()
            ):

                key = (
                    msvcrt.getwch()
                    .lower()
                )


                # -----------------------------------------------
                # SPACE：演奏模式开关
                # -----------------------------------------------

                if key == " ":

                    if armed:
                        disarm_system()

                    else:
                        arm_system()

                    continue


                # -----------------------------------------------
                # T：纯音频测试
                # -----------------------------------------------

                elif key == "t":

                    print(
                        "[AUDIO TEST] "
                        "T -> PLAY E4"
                    )

                    play_note(
                        "E4"
                    )


            # ====================================================
            # D. UDP burst 诊断
            # ====================================================

            if (
                prev_device_ts is not None
                and prev_host_arrival is not None
            ):

                device_dt = (
                    timestamp
                    - prev_device_ts
                )

                host_dt_ms = (
                    (
                        host_arrival
                        - prev_host_arrival
                    )
                    * 1000.0
                )

                if (
                    device_dt >= 5.0
                    and host_dt_ms < 2.0
                ):
                    burst_count += 1


            prev_device_ts = timestamp

            prev_host_arrival = (
                host_arrival
            )


            now_diag = host_arrival

            if (
                now_diag
                - last_burst_report
                >= 3.0
            ):

                if burst_count > 0:

                    print(
                        f"[UDP] "
                        f"burst-like arrivals "
                        f"in last 3s: "
                        f"{burst_count}"
                    )

                burst_count = 0

                last_burst_report = (
                    now_diag
                )


            # ====================================================
            # E. STANDBY：
            #
            # 到这里直接结束。
            #
            # 不做任何 gesture 识别。
            # ====================================================

            if not armed:
                continue


            # ====================================================
            # F. ARMED 时的选音
            #
            # 选音仍然只在动作较小时更新，
            # 避免下挥过程中乱跳音。
            #
            # 注意：
            # 这只是“音高选择”的稳定判断，
            # 和“用户有没有准备好”已经无关。
            # ====================================================

            pose_good_for_note = (
                gyro_perp < 0.8
                and 8.0
                < accel_mag
                < 12.0
            )


            if pose_good_for_note:

                note = (
                    update_note_from_roll(
                        roll
                    )
                )

                if (
                    note
                    != last_print_note
                ):

                    print(
                        f"[SELECT] "
                        f"roll={roll:+.1f}° "
                        f"-> {note}"
                    )

                    last_print_note = (
                        note
                    )


            # ====================================================
            # G. 当前上下挥角速度
            # ====================================================

            pitch_rate = (
                gy * pitch_ny
                + gz * pitch_nz
            )

            pitch_rate_history.append(
                pitch_rate
            )

            smooth_rate = (
                statistics.mean(
                    pitch_rate_history
                )
            )


            # 当前固定：
            #
            # signed_rate > 0 = 下挥
            # signed_rate < 0 = 上挥

            signed_rate = (
                DOWN_SIGN
                * smooth_rate
            )


            # ====================================================
            # H. 根据 MPU timestamp 算 dt
            # ====================================================

            if detector_prev_timestamp is None:

                dt = 0.01

            else:

                raw_dt = (
                    timestamp
                    - detector_prev_timestamp
                ) / 1000.0


                if (
                    0.002
                    <= raw_dt
                    <= 0.030
                ):

                    dt = raw_dt

                else:

                    dt = 0.01


            detector_prev_timestamp = (
                timestamp
            )


            # ====================================================
            # STATE 1：IDLE
            #
            # 等待一次真正开始向下的动作。
            #
            # 此时不会发音。
            # ====================================================

            if gesture_state == "IDLE":

                if (
                    signed_rate
                    >= DOWN_START_RATE
                ):

                    start_frames += 1

                else:

                    start_frames = 0


                if (
                    start_frames
                    >= DOWN_START_CONFIRM_FRAMES
                ):

                    gesture_state = (
                        "DOWN"
                    )

                    locked_note = (
                        current_note
                    )

                    down_elapsed = (
                        DOWN_START_CONFIRM_FRAMES
                        * dt
                    )

                    down_area = (
                        max(
                            signed_rate,
                            0.0
                        )
                        * down_elapsed
                    )

                    down_peak = max(
                        signed_rate,
                        0.0
                    )

                    beat_end_frames = 0
                    start_frames = 0


                    print(
                        f"[DOWN] "
                        f"note={locked_note} "
                        f"rate={smooth_rate:+.2f}"
                    )


            # ====================================================
            # STATE 2：DOWN
            #
            # 累积这一段动作的：
            #
            # 时间
            # 转角
            # 峰值速度
            #
            # 从而判断它是不是真的下挥。
            # ====================================================

            elif gesture_state == "DOWN":

                down_elapsed += dt


                # 只累计真正朝下的部分
                if signed_rate > 0:

                    down_area += (
                        signed_rate
                        * dt
                    )


                down_peak = max(
                    down_peak,
                    signed_rate
                )


                committed = (
                    down_elapsed
                    >= MIN_DOWN_TIME

                    and down_area
                    >= MIN_DOWN_ANGLE

                    and down_peak
                    >= MIN_DOWN_PEAK
                )


                # -----------------------------------------------
                # 尚未形成真正下挥
                # -----------------------------------------------

                if not committed:

                    # 很快就向上：
                    # 只是乱晃
                    if (
                        signed_rate
                        <= -RETURN_RATE
                    ):

                        print(
                            f"[CANCEL] "
                            f"false motion "
                            f"time="
                            f"{down_elapsed*1000:.0f}ms "
                            f"angle="
                            f"{math.degrees(down_area):.1f}° "
                            f"peak="
                            f"{down_peak:.2f}"
                        )

                        reset_detector()


                    # 拖很久仍未形成有效下挥
                    elif (
                        down_elapsed
                        >= MAX_DOWN_TIME
                    ):

                        print(
                            f"[CANCEL] "
                            f"weak / unclear motion "
                            f"time="
                            f"{down_elapsed*1000:.0f}ms "
                            f"angle="
                            f"{math.degrees(down_area):.1f}° "
                            f"peak="
                            f"{down_peak:.2f}"
                        )

                        reset_detector()


                # -----------------------------------------------
                # 已经确认是真下挥
                #
                # 等待落点。
                # -----------------------------------------------

                else:

                    if (
                        signed_rate
                        <= BEAT_END_RATE
                    ):

                        beat_end_frames += 1

                    else:

                        beat_end_frames = 0


                    if (
                        beat_end_frames
                        >= BEAT_END_CONFIRM_FRAMES
                    ):

                        print(
                            f">>> BEAT "
                            f"{locked_note} "
                            f"time="
                            f"{down_elapsed*1000:.0f}ms "
                            f"angle="
                            f"{math.degrees(down_area):.1f}° "
                            f"peak="
                            f"{down_peak:.2f}"
                        )

                        play_note(
                            locked_note
                        )

                        gesture_state = (
                            "RETURN"
                        )

                        return_seen = False
                        return_frames = 0

                        neutral_frames = 0
                        beat_end_frames = 0


            # ====================================================
            # STATE 3：RETURN
            #
            # 发音以后，
            # 必须经历一个完整回棒，
            # 才能允许下一拍。
            # ====================================================

            elif gesture_state == "RETURN":


                # -----------------------------------------------
                # 先确认确实开始向上回棒
                # -----------------------------------------------

                if not return_seen:

                    if (
                        signed_rate
                        <= -RETURN_RATE
                    ):

                        return_frames += 1

                    else:

                        return_frames = 0


                    if (
                        return_frames
                        >= RETURN_CONFIRM_FRAMES
                    ):

                        return_seen = True

                        return_frames = 0
                        neutral_frames = 0


                        print(
                            f"[RETURN] "
                            f"rate="
                            f"{smooth_rate:+.2f}"
                        )


                # -----------------------------------------------
                # 已经在回棒
                #
                # 等回棒到顶部附近、速度降下来。
                # -----------------------------------------------

                else:

                    if (
                        abs(signed_rate)
                        <= REARM_NEUTRAL_RATE
                    ):

                        neutral_frames += 1

                    else:

                        neutral_frames = 0


                    if (
                        neutral_frames
                        >= REARM_NEUTRAL_FRAMES
                    ):

                        print(
                            "[READY NEXT]"
                        )

                        reset_detector()


        except (
            UnicodeDecodeError,
            ValueError
        ):

            continue


        except Exception as e:

            print(
                "ERROR:",
                e
            )


finally:

    sock.close()

    stream.stop()
    stream.close()