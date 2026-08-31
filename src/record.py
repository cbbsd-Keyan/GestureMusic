import sys
import time
import msvcrt
from pathlib import Path

from input.udp_reader import UDPReader
from input.recorder import Recorder


# =========================
# 配置
# =========================

UDP_PORT = 4210

# 相对脚本位置定位，与运行目录无关
DATA_DIR = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "batch_2026_09_w1"
)

SUBJECT_ID = "s00"

MOUNT_VERSION = "ruler_v1"

# 命令行覆盖:
# python record.py s01           -> 换受试者
# python record.py s01 baton_v1  -> 换受试者+固定方式
if len(sys.argv) > 1:
    SUBJECT_ID = sys.argv[1]

if len(sys.argv) > 2:
    MOUNT_VERSION = sys.argv[2]

SCENES = {
    "1": "vigorous",
    "2": "gentle",
    "3": "free",
}


# =========================
# 初始化
# =========================

reader = UDPReader(port=UDP_PORT)

recorder = Recorder(
    out_dir=DATA_DIR,
    subject_id=SUBJECT_ID,
    mount_version=MOUNT_VERSION,
)

scene = "free"

drop_count = 0


print("===== Continuous Recorder =====")
print()
print(f"受试者: {SUBJECT_ID} | 固定方式: {MOUNT_VERSION}")
print(f"数据目录: {DATA_DIR}/{SUBJECT_ID}")
print()
print("1/2/3 -> 选择场景 (vigorous/gentle/free)")
print("R -> 开始 / S -> 停止并保存")
print("Q -> 退出")
print()


try:

    while True:

        # =========================
        # 键盘控制
        # =========================

        if msvcrt.kbhit():

            key = msvcrt.getwch().lower()

            if key == "q":
                break

            elif key == "r":

                recorder.start()

                print(
                    f">>> 录制中 [{scene}] "
                    f"(每秒采样数见下行滚动)"
                )

            elif key == "s":

                n = recorder.stop()

                if n == 0:
                    print("没有数据，未保存。")
                    continue

                result = recorder.save(scene=scene)

                m = result["meta_content"]

                print(
                    f"已保存 {m['samples']} 点 | "
                    f"{m['duration_s']}s | "
                    f"约 {m['hz_estimate']} Hz | "
                    f"{result['csv']}"
                )

                if m["samples"] < 300:
                    print("警告：样本偏少 (<300)，建议录满 5 秒以上。")

            elif key in SCENES:

                scene = SCENES[key]

                print(f"场景切换为: {scene}")

        # =========================
        # UDP输入
        # =========================

        line = reader.read()

        if line is not None:

            parts = line.split(",")

            if len(parts) == 7:

                try:

                    values = [
                        float(x) for x in parts
                    ]

                    recorder.feed(values)

                except ValueError:
                    drop_count += 1

            else:
                drop_count += 1

        # =========================
        # 录制中状态提示
        # =========================

        if recorder.recording and len(recorder.rows) % 200 == 0:

            secs = len(recorder.rows) / 100.0

            print(
                f"  ... {secs:.0f}s "
                f"({len(recorder.rows)} 点)"
            )

        time.sleep(0.001)

finally:

    if recorder.recording:

        recorder.stop()

        if recorder.rows:
            recorder.save(scene=scene)

    reader.close()

    print(f"\n程序结束 (丢弃包: {drop_count})")
