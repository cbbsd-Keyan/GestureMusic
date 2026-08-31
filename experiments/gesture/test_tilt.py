import socket
import math

UDP_IP = "0.0.0.0"
UDP_PORT = 4210

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print("Listening...")


current_note = "E4"

HYST = 2.0


def update_note_from_roll(roll):
    global current_note

    if current_note == "C4":
        # C -> D
        if roll > -26 + HYST:
            current_note = "D4"

    elif current_note == "D4":
        # D -> C
        if roll < -26 - HYST:
            current_note = "C4"

        # D -> E
        elif roll > -12 + HYST:
            current_note = "E4"

    elif current_note == "E4":
        # E -> D
        if roll < -12 - HYST:
            current_note = "D4"

        # E -> G
        elif roll > 12 + HYST:
            current_note = "G4"

    elif current_note == "G4":
        # G -> E
        if roll < 12 - HYST:
            current_note = "E4"

        # G -> A
        elif roll > 26 + HYST:
            current_note = "A4"

    elif current_note == "A4":
        # A -> G
        if roll < 26 - HYST:
            current_note = "G4"

    return current_note


while True:
    data, addr = sock.recvfrom(1024)

    try:
        text = data.decode().strip()
        values = list(map(float, text.split(",")))

        # 当前 UDP 数据：
        # timestamp, ax, ay, az, gx, gy, gz
        if len(values) >= 7:
            timestamp, ax, ay, az, gx, gy, gz = values[:7]
        else:
            continue

        # 绕 x 轴的左右倾角
        roll = math.degrees(math.atan2(ay, az))

        current_note = update_note_from_roll(roll)

        print(
            f"roll={roll:7.2f}°  ->  {current_note}"
        )

    except Exception as e:
        print("parse error:", e)