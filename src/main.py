import time
import msvcrt

from input.udp_reader import UDPReader
from music.midi_engine import MidiEngine
from music.music_engine import MusicEngine


# =========================
# 配置
# =========================

UDP_PORT = 4210
MIDI_DEVICE_ID = 1

# 主线程需要什么音乐层
ENABLE_CHORDS = True
ENABLE_BASS = True
ENABLE_MELODY = True

# 鼓目前只是可选效果
ENABLE_DRUMS = False


# =========================
# 初始化
# =========================

reader = UDPReader(
    port=UDP_PORT
)

midi = MidiEngine(
    device_id=MIDI_DEVICE_ID
)

music = MusicEngine(
    midi=midi,
    enable_chords=ENABLE_CHORDS,
    enable_bass=ENABLE_BASS,
    enable_melody=ENABLE_MELODY,
    enable_drums=ENABLE_DRUMS,
)


print("===== Gesture Music =====")
print()
print("真实下挥 -> Beat")
print("左右倾斜 -> Melody contour")
print()
print("D -> 开/关鼓")
print("B -> 开/关 Bass")
print("C -> 开/关 Chord")
print("M -> 开/关 Melody")
print("Q -> 退出")
print()


try:

    while True:

        # =========================
        # 键盘调试
        # =========================

        if msvcrt.kbhit():

            key = msvcrt.getwch().lower()

            if key == "q":
                break

            elif key == "d":
                music.toggle_drums()

            elif key == "b":
                music.toggle_bass()

            elif key == "c":
                music.toggle_chords()

            elif key == "m":
                music.toggle_melody()


        # =========================
        # UDP输入
        # =========================

        line = reader.read()

        if line is not None:

            if line.startswith("TILT,"):

                try:

                    _, value = line.split(",")

                    music.update_roll(
                        float(value)
                    )

                except ValueError:
                    pass


            elif line.startswith("BEAT"):

                parts = line.split(",")

                if len(parts) >= 2:
                    try:
                        speed = float(parts[1])
                        print(f"REAL BEAT | speed={speed:.1f}")
                    except ValueError:
                        pass

                music.handle_beat()


        # =========================
        # 内部音乐时钟
        # =========================

        music.update()

        time.sleep(0.001)


finally:

    music.close()
    reader.close()
    midi.close()

    print("\n程序结束")