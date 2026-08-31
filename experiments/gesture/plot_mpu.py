import socket
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


UDP_PORT = 4210
N = 2000          # 保存最近 300 个采样点 ≈ 3 秒（100 Hz）


# =========================
# UDP
# =========================

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", UDP_PORT))
sock.setblocking(False)

print(f"Listening on UDP port {UDP_PORT}...")


# =========================
# 数据缓存
# =========================

ax_data = deque(maxlen=N)
ay_data = deque(maxlen=N)
az_data = deque(maxlen=N)

gx_data = deque(maxlen=N)
gy_data = deque(maxlen=N)
gz_data = deque(maxlen=N)


# =========================
# 建图
# =========================

fig, (acc_plot, gyro_plot) = plt.subplots(2, 1, figsize=(10, 8))

# 加速度
line_ax, = acc_plot.plot([], [], label="ax")
line_ay, = acc_plot.plot([], [], label="ay")
line_az, = acc_plot.plot([], [], label="az")

acc_plot.set_title("Accelerometer")
acc_plot.set_ylabel("m/s^2")
acc_plot.set_xlim(0, N)
acc_plot.set_ylim(-40, 40)
acc_plot.grid(True)
acc_plot.legend()

# 陀螺仪
line_gx, = gyro_plot.plot([], [], label="gx")
line_gy, = gyro_plot.plot([], [], label="gy")
line_gz, = gyro_plot.plot([], [], label="gz")

gyro_plot.set_title("Gyroscope")
gyro_plot.set_xlabel("Samples")
gyro_plot.set_ylabel("rad/s")
gyro_plot.set_xlim(0, N)
gyro_plot.set_ylim(-20, 20)
gyro_plot.grid(True)
gyro_plot.legend()


def update(frame):

    # 把当前已经到达的 UDP 数据全部读掉
    while True:
        try:
            packet, addr = sock.recvfrom(1024)
        except BlockingIOError:
            break

        try:
            text = packet.decode("utf-8").strip()
            parts = text.split(",")

            if len(parts) != 7:
                continue

            t, ax, ay, az, gx, gy, gz = map(float, parts)

            ax_data.append(ax)
            ay_data.append(ay)
            az_data.append(az)

            gx_data.append(gx)
            gy_data.append(gy)
            gz_data.append(gz)

        except ValueError:
            continue

    n = len(ax_data)
    x = list(range(N - n, N))

    line_ax.set_data(x, ax_data)
    line_ay.set_data(x, ay_data)
    line_az.set_data(x, az_data)

    line_gx.set_data(x, gx_data)
    line_gy.set_data(x, gy_data)
    line_gz.set_data(x, gz_data)

    return (
        line_ax, line_ay, line_az,
        line_gx, line_gy, line_gz
    )


ani = FuncAnimation(
    fig,
    update,
    interval=30,
    cache_frame_data=False
)

plt.tight_layout()
plt.show()

sock.close()