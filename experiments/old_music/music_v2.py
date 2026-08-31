import pygame.midi
import serial
import time
import msvcrt

# =========================
# 串口
# =========================

PORT = "COM9"       # 改成你的实际端口
BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=0)
time.sleep(1)

# 清掉刚打开串口时可能积压的数据
ser.reset_input_buffer()

# =========================
# MIDI
# =========================

pygame.midi.init()
player = pygame.midi.Output(1)

CHORD_CHANNEL = 0
BASS_CHANNEL = 1
MELODY_CHANNEL = 2
DRUM_CHANNEL = 9

player.set_instrument(0, CHORD_CHANNEL)
player.set_instrument(32, BASS_CHANNEL)
player.set_instrument(0, MELODY_CHANNEL)

# =========================
# 音乐数据
# =========================

chords = [
    [60, 64, 67],  # C
    [57, 60, 64],  # Am
    [53, 57, 60],  # F
    [55, 59, 62],  # G
]

chord_names = ["C", "Am", "F", "G"]

bass_notes = [
    36,  # C2
    33,  # A1
    29,  # F1
    31,  # G1
]

melody_notes = [
    [60, 64, 67],  # C
    [57, 60, 64],  # Am
    [53, 57, 60],  # F
    [55, 59, 62],  # G
]

drum_pattern = [
    36,  # kick
    42,  # hihat
    38,  # snare
    42,  # hihat
]

# =========================
# 当前状态
# =========================

beat = 0

roll = 0.0
height = 1       # 0 LOW / 1 MID / 2 HIGH

current_chord = None
current_bass = None
last_melody = None


# =========================
# roll → 旋律档位
# =========================

def roll_to_height(value):
    if value < -15:
        return 0
    elif value > 15:
        return 2
    else:
        return 1


# =========================
# 真正播放“一拍”
# =========================

def play_beat():

    global beat
    global current_chord
    global current_bass
    global last_melody

    chord_index = (beat // 4) % 4
    beat_in_bar = beat % 4

    # ---------- 换和弦 ----------

    if beat_in_bar == 0:

        if current_chord is not None:
            for note in current_chord:
                player.note_off(
                    note,
                    65,
                    CHORD_CHANNEL
                )

        if current_bass is not None:
            player.note_off(
                current_bass,
                80,
                BASS_CHANNEL
            )

        current_chord = chords[chord_index]
        current_bass = bass_notes[chord_index]

        for note in current_chord:
            player.note_on(
                note,
                60,
                CHORD_CHANNEL
            )

        player.note_on(
            current_bass,
            75,
            BASS_CHANNEL
        )

    # ---------- 鼓 ----------

    drum_note = drum_pattern[beat_in_bar]

    player.note_on(
        drum_note,
        105,
        DRUM_CHANNEL
    )

    player.note_off(
        drum_note,
        105,
        DRUM_CHANNEL
    )

    # ---------- 旋律 ----------

    if last_melody is not None:
        player.note_off(
            last_melody,
            90,
            MELODY_CHANNEL
        )

    melody_note = melody_notes[chord_index][height]

    # 右倾 HIGH 再高一个八度
    if height == 2:
        melody_note += 12

    player.note_on(
        melody_note,
        90,
        MELODY_CHANNEL
    )

    last_melody = melody_note

    print(
        f"BEAT {beat + 1:2d} | "
        f"Chord {chord_names[chord_index]:2s} | "
        f"Roll {roll:6.1f}° | "
        f"{['LOW', 'MID', 'HIGH'][height]:4s} | "
        f"Melody {melody_note}"
    )

    beat += 1


# =========================
# 主程序
# =========================

print("===== Gesture Music V4 =====")
print()
print("真实下挥 -> 下一拍")
print("左倾     -> 低旋律")
print("水平     -> 中旋律")
print("右倾     -> 高旋律")
print("Q        -> 退出")
print()


try:

    while True:

        # Q 仍然留作退出
        if msvcrt.kbhit():
            key = msvcrt.getwch()

            if key.lower() == "q":
                break

        # 没收到串口就继续
        if not ser.in_waiting:
            time.sleep(0.001)
            continue

        line = (
            ser.readline()
            .decode(errors="ignore")
            .strip()
        )

        if not line:
            continue

        # =========================
        # 姿态
        # =========================

        if line.startswith("TILT,"):

            try:
                _, value = line.split(",")

                roll = float(value)

                new_height = roll_to_height(roll)

                if new_height != height:

                    height = new_height

                    print(
                        f"Roll {roll:6.1f}° -> "
                        f"{['LOW', 'MID', 'HIGH'][height]}"
                    )

            except ValueError:
                pass

        # =========================
        # 下挥
        # =========================

        elif line == "BEAT":
            play_beat()


finally:

    if current_chord:
        for note in current_chord:
            player.note_off(
                note,
                65,
                CHORD_CHANNEL
            )

    if current_bass:
        player.note_off(
            current_bass,
            80,
            BASS_CHANNEL
        )

    if last_melody:
        player.note_off(
            last_melody,
            90,
            MELODY_CHANNEL
        )

    ser.close()
    player.close()
    pygame.midi.quit()

    print("\n程序结束")