import socket
import time


class UDPReader:
    def __init__(self, port=4210):
        self.sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        # 允许发送广播（Windows 必需）
        self.sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_BROADCAST,
            1
        )

        self.sock.bind(
            ("0.0.0.0", port)
        )

        self.sock.setblocking(False)

        self._register()

    def _register(self):

        # 向板子(4211端口)宣告本机地址，
        # 板子收到后切换为对本机单播
        try:

            self.sock.sendto(
                b"PC_HERE",
                ("255.255.255.255", 4211)
            )

        except OSError:
            pass

        self._last_register = (
            time.monotonic()
        )

    def read(self):

        # 每3秒重新注册一次，
        # 覆盖板子重启/换网的情况
        if (
            time.monotonic()
            - self._last_register
            > 3.0
        ):

            self._register()

        try:
            data, address = self.sock.recvfrom(1024)

            message = (
                data.decode(errors="ignore")
                .strip()
            )

            if not message:
                return None

            return message

        except BlockingIOError:
            return None

    def close(self):
        self.sock.close()