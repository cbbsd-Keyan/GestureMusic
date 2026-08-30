import serial

PORT = "COM9"      # 改成你的实际端口
BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=1)

print("开始读取姿态角，Ctrl+C 结束")

try:
    while True:
        line = ser.readline().decode(errors="ignore").strip()

        if not line:
            continue

        try:
            roll, pitch = map(float, line.split(","))

            print(
                f"roll = {roll:7.2f}°   "
                f"pitch = {pitch:7.2f}°"
            )

        except ValueError:
            pass

except KeyboardInterrupt:
    pass

finally:
    ser.close()