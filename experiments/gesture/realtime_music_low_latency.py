import socket
import math
import statistics
import time
from collections import deque

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
# 1. 音频
#
# 这一版仍使用 sd.play，但把波形预先算好。
# 这样触发时不再现场生成正弦波。
# 如果后面实测仍有明显“声音端”延迟，再换持久 OutputStream。
# ============================================================

NOTE_DURATION = 0.22
NOTE_VOLUME = 0.25


def make_wave(freq, duration=NOTE_DURATION, volume=NOTE_VOLUME):
    t = np.linspace(
        0,
        duration,
        int(SAMPLE_RATE * duration),
        endpoint=False,
    )

    wave = np.sin(2 * np.pi * freq * t)

    attack = max(1, int(0.008 * SAMPLE_RATE))
    release = max(1, int(0.05 * SAMPLE_RATE))

    envelope = np.ones_like(wave)
    envelope[:attack] = np.linspace(0, 1, attack)
    envelope[-release:] = np.linspace(1, 0, release)

    return (volume * wave * envelope).astype(np.float32)


NOTE_WAVES = {
    note: make_wave(freq)
    for note, freq in NOTE_FREQ.items()
}


def play_note(note):
    # 不 wait；新音符会立刻重触发。
    sd.play(NOTE_WAVES[note], SAMPLE_RATE)


# ============================================================
# 2. 倾斜 -> 音符
# ============================================================

current_note = "E4"
locked_note = "E4"

OUTER_ANGLE = 30.0
INNER_ANGLE = 10.0
HYST = 1.5

# 只有比较稳定时才用加速度估计姿态和“上下挥轴”
POSE_GYRO_LIMIT = 0.8
ACCEL_MIN = 8.5
ACCEL_MAX = 11.5
POSE_WINDOW = 6
POSE_MAX_RANGE = 4.0

stable_rolls = deque(maxlen=POSE_WINDOW)
stable_accels = deque(maxlen=POSE_WINDOW)


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
        if -OUTER_ANGLE - HYST <= roll < -INNER_ANGLE + HYST:
            return current_note

    elif current_note == "E4":
        if -INNER_ANGLE - HYST <= roll < INNER_ANGLE + HYST:
            return current_note

    elif current_note == "G4":
        if INNER_ANGLE - HYST <= roll < OUTER_ANGLE + HYST:
            return current_note

    elif current_note == "A4":
        if roll >= OUTER_ANGLE - HYST:
            return current_note

    current_note = base_note_from_roll(roll)
    return current_note


# ============================================================
# 3. 实时 downstroke detector
#
# 不再：
#   录完整动作 -> 等安静 -> RF 分类 -> 播放
#
# 改成：
#   稳定时估计 pitch 轴
#   -> pitch_rate 跨阈值
#   -> 立刻播放
#   -> 检测到反向回棒后重新允许下一次触发
# ============================================================

# intentional downstroke 通常会明显高于这个值。
# 若“挥了不响”，先降到 1.5；若“太容易误响”，升到 2.5~3.0。
TRIGGER_PITCH_RATE = 2.0       # rad/s

# 回棒反向运动达到这个量级，就重新武装下一拍。
RETURN_PITCH_RATE = 1.2        # rad/s

# 防止一次挥棒里的瞬时抖动造成重复触发。
REFRACTORY_SECONDS = 0.08

# 对 pitch_rate 做很短的平滑，只引入约 1~2 个采样点的延迟。
RATE_SMOOTH_WINDOW = 3
pitch_rate_history = deque(maxlen=RATE_SMOOTH_WINDOW)

# pitch_rate = gy * pitch_ny + gz * pitch_nz
# 这个方向在棒稳定时由加速度估计。
pitch_ny = 1.0
pitch_nz = 0.0
pitch_axis_valid = False

# 第一次明确的挥动自动定义“downstroke 的正负号”。
# 这样不必现在就假设你的最终棒子 MPU 安装方向。
down_sign = None

# True: 下一次同方向 downstroke 可以触发
ready_for_downstroke = True
last_trigger_time = -1e9


def update_pitch_axis(accel_samples):
    """用最近稳定姿态的加速度估计与棒 X 轴垂直的上下挥旋转轴。"""
    global pitch_ny, pitch_nz, pitch_axis_valid

    if not accel_samples:
        return

    ux = statistics.mean(a[0] for a in accel_samples)
    uy = statistics.mean(a[1] for a in accel_samples)
    uz = statistics.mean(a[2] for a in accel_samples)

    norm_u = math.sqrt(ux * ux + uy * uy + uz * uz)
    if norm_u < 1e-6:
        return

    ux /= norm_u
    uy /= norm_u
    uz /= norm_u

    # 与原 invariant 特征一致：X × Up = (0, -uz, uy)
    ny = -uz
    nz = uy

    norm_n = math.sqrt(ny * ny + nz * nz)
    if norm_n < 1e-6:
        return

    pitch_ny = ny / norm_n
    pitch_nz = nz / norm_n
    pitch_axis_valid = True


# ============================================================
# 4. 启动保护
# ============================================================

armed = False
startup_motion_seen = False
last_print_note = None


# ============================================================
# 5. UDP
# ============================================================

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print()
print("Realtime Melody Orbit - LOW LATENCY")
print("Pick up the wand, then hold it still.")
print("After READY, make ONE deliberate downstroke first.")
print("That first stroke calibrates the downstroke direction.")
print()


# ============================================================
# 6. 主循环
# ============================================================

while True:
    packet, addr = sock.recvfrom(1024)

    try:
        values = list(
            map(
                float,
                packet.decode().strip().split(",")
            )
        )

        # timestamp, ax, ay, az, gx, gy, gz
        if len(values) < 7:
            continue

        timestamp, ax, ay, az, gx, gy, gz = values[:7]

        gyro_perp = math.sqrt(gy * gy + gz * gz)
        accel_mag = math.sqrt(ax * ax + ay * ay + az * az)

        roll = math.degrees(math.atan2(ay, az))

        # ----------------------------------------------------
        # A. 启动：先确认用户确实拿起过棒子
        # ----------------------------------------------------
        if not armed:
            if (
                gyro_perp > 1.0
                or accel_mag < ACCEL_MIN
                or accel_mag > ACCEL_MAX
            ):
                startup_motion_seen = True

        # ----------------------------------------------------
        # B. 稳定姿态：更新音高 + pitch 轴
        # ----------------------------------------------------
        pose_trustworthy = (
            gyro_perp < POSE_GYRO_LIMIT
            and ACCEL_MIN < accel_mag < ACCEL_MAX
        )

        if pose_trustworthy:
            stable_rolls.append(roll)
            stable_accels.append((ax, ay, az))
        else:
            stable_rolls.clear()
            stable_accels.clear()

        if len(stable_rolls) == POSE_WINDOW:
            roll_range = max(stable_rolls) - min(stable_rolls)

            if roll_range < POSE_MAX_RANGE:
                stable_roll = statistics.mean(stable_rolls)
                update_pitch_axis(stable_accels)

                if not armed:
                    if startup_motion_seen and pitch_axis_valid:
                        armed = True
                        current_note = base_note_from_roll(stable_roll)
                        locked_note = current_note
                        last_print_note = current_note

                        print(
                            f"[READY] roll={stable_roll:+6.1f}° "
                            f"-> {current_note}"
                        )

                else:
                    note = update_note_from_roll(stable_roll)

                    if note != last_print_note:
                        print(
                            f"[SELECT] roll={stable_roll:+6.1f}° "
                            f"-> {note}"
                        )
                        last_print_note = note

        if not armed or not pitch_axis_valid:
            continue

        # ----------------------------------------------------
        # C. 每个采样点立刻计算 pitch_rate
        # ----------------------------------------------------
        pitch_rate = gy * pitch_ny + gz * pitch_nz
        pitch_rate_history.append(pitch_rate)

        smooth_rate = statistics.mean(pitch_rate_history)

        now = time.perf_counter()

        # ----------------------------------------------------
        # D. 第一次明显挥动：自动校准 downstroke 方向
        # ----------------------------------------------------
        if down_sign is None:
            if abs(smooth_rate) >= TRIGGER_PITCH_RATE:
                down_sign = 1.0 if smooth_rate > 0 else -1.0

                locked_note = current_note
                last_trigger_time = now
                ready_for_downstroke = False
                stable_rolls.clear()
                stable_accels.clear()

                print(
                    f"[CALIBRATE] down_sign={down_sign:+.0f}, "
                    f"rate={smooth_rate:+.2f} rad/s"
                )
                print(f">>> PLAY {locked_note}")
                play_note(locked_note)

            continue

        signed_rate = down_sign * smooth_rate

        # ----------------------------------------------------
        # E. READY -> 起挥跨阈值，立即发音
        # ----------------------------------------------------
        if ready_for_downstroke:
            if (
                signed_rate >= TRIGGER_PITCH_RATE
                and now - last_trigger_time >= REFRACTORY_SECONDS
            ):
                locked_note = current_note
                last_trigger_time = now
                ready_for_downstroke = False

                stable_rolls.clear()
                stable_accels.clear()

                print(
                    f">>> PLAY {locked_note} "
                    f"rate={smooth_rate:+.2f} rad/s"
                )
                play_note(locked_note)

        # ----------------------------------------------------
        # F. 已触发 -> 检测明显反向回棒，重新允许下一拍
        #
        # 不要求“静止 12 帧”，所以连续演奏不必停住。
        # ----------------------------------------------------
        else:
            if (
                signed_rate <= -RETURN_PITCH_RATE
                and now - last_trigger_time >= REFRACTORY_SECONDS
            ):
                ready_for_downstroke = True
                print("[REARM] return stroke detected")

    except Exception as e:
        print("ERROR:", e)
