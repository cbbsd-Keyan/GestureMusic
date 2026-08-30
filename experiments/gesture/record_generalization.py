import socket
import csv
import time
from pathlib import Path
import msvcrt

UDP_PORT = 4210
RECORD_SECONDS = 1.5

BASE_DIR = Path("generalization_test")
DOWN_DIR = BASE_DIR / "downstroke"
OTHER_DIR = BASE_DIR / "other"

DOWN_DIR.mkdir(parents=True, exist_ok=True)
OTHER_DIR.mkdir(parents=True, exist_ok=True)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", UDP_PORT))
sock.settimeout(0.05)


def clear_socket():
    """清掉倒计时期间积压的 UDP 数据。"""
    sock.setblocking(False)

    try:
        while True:
            sock.recvfrom(1024)
    except BlockingIOError:
        pass

    sock.settimeout(0.05)


def next_filename(label):
    folder = DOWN_DIR if label == "downstroke" else OTHER_DIR

    index = 1
    while True:
        path = folder / f"{label}_{index:03d}.csv"

        if not path.exists():
            return path

        index += 1


def record_one(label):
    print()
    print(f"准备录制：{label}")

    print("3...")
    time.sleep(0.4)
    print("2...")
    time.sleep(0.4)
    print("1...")
    time.sleep(0.4)

    clear_socket()

    print(">>> GO! <<<")

    rows = []
    start = time.perf_counter()

    while time.perf_counter() - start < RECORD_SECONDS:
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            continue

        try:
            line = data.decode("utf-8").strip()
            parts = line.split(",")

            if len(parts) != 7:
                continue

            values = [float(x) for x in parts]
            rows.append(values)

        except (UnicodeDecodeError, ValueError):
            continue

    if not rows:
        print("没有收到数据，这次不保存。")
        return

    path = next_filename(label)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow([
            "time_ms",
            "ax", "ay", "az",
            "gx", "gy", "gz"
        ])

        writer.writerows(rows)

    gy = [r[5] for r in rows]
    gz = [r[6] for r in rows]

    print(f"已保存：{path}")
    print(f"采样点数：{len(rows)}")

    print(
        f"gy: min={min(gy):.2f}, max={max(gy):.2f} rad/s"
    )

    print(
        f"gz: min={min(gz):.2f}, max={max(gz):.2f} rad/s"
    )

    if len(rows) < 100:
        print("警告：采样点偏少，检查 Wi-Fi / UDP 是否稳定。")


print("UDP gesture recorder")
print(f"Listening on port {UDP_PORT}")
print()
print("按键：")
print("  D = 录一次 DOWNSTROKE")
print("  O = 录一次 OTHER")
print("  Q = 退出")
print()

while True:
    if msvcrt.kbhit():
        key = msvcrt.getwch().lower()

        if key == "d":
            record_one("downstroke")

        elif key == "o":
            record_one("other")

        elif key == "q":
            print("退出录制。")
            break

    time.sleep(0.02)

sock.close()