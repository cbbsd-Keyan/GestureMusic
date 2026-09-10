import threading
import time


# =========================
# 信标追踪: 纯numpy检测 + cv2采集
# =========================

MIN_AREA = 20
MAX_AREA_FRAC = 0.30

CALIB_SECONDS = 6.0
CAMERA_TIMEOUT = 2.0
MAX_FRAME_READ_S = 0.30


def detect_brightest(frame):

    """
    找画面中最亮的高亮团(手机手电筒模式)。
    frame: BGR uint8数组
    返回 (cx, cy, area) 或 None
    """

    import numpy as np

    gray = frame.mean(axis=2)

    peak = gray.max()

    if peak < 180:
        return None

    mask = gray > max(170.0, peak * 0.85)

    area = int(mask.sum())

    if not (MIN_AREA <= area <= mask.size * MAX_AREA_FRAC):
        return None

    ys, xs = np.nonzero(mask)

    return (
        float(xs.mean()),
        float(ys.mean()),
        area,
    )


def detect_green(frame):

    """
    找纯绿亮点(灯带模式)。
    """

    import numpy as np

    b = frame[:, :, 0].astype("int32")
    g = frame[:, :, 1].astype("int32")
    r = frame[:, :, 2].astype("int32")

    mask = (
        (g > 170)
        & (g > 1.4 * r)
        & (g > 1.4 * b)
    )

    area = int(mask.sum())

    if not (MIN_AREA <= area <= mask.size * MAX_AREA_FRAC):
        return None

    ys, xs = np.nonzero(mask)

    return (
        float(xs.mean()),
        float(ys.mean()),
        area,
    )


DETECTORS = {
    "bright": detect_brightest,
    "green": detect_green,
}


# 对角线权重: 组长裁决"向上优先于向右"
WEIGHT_VERTICAL = 0.65
WEIGHT_HORIZONTAL = 0.35


def level_from_pos(
    pos,
    box,
    lo=0.40,
    hi=0.60,
):

    """
    位置 -> 对角线音区(-1/0/+1)。
    画面y向下, 所以右上 = x大 + y小。
    垂直分量权重高于水平(向上优先)。
    """

    x, y = pos

    minx, miny, maxx, maxy = box

    if maxx - minx < 10 and maxy - miny < 10:
        return 0

    nx = min(
        1.0,
        max(0.0, (x - minx) / max(1, maxx - minx)),
    )

    ny = min(
        1.0,
        max(0.0, (y - miny) / max(1, maxy - miny)),
    )

    diag = (
        WEIGHT_VERTICAL * (1.0 - ny)
        + WEIGHT_HORIZONTAL * nx
    )

    if diag < lo:
        return -1

    if diag > hi:
        return 1

    return 0


class BeaconTracker:

    """
    摄像头信标追踪器。
    calibrate() -> 个人键盘区域
    start()/stop() -> 录制期间后台采集
    levels() -> [(时刻, 音区)]
    """

    def __init__(self, beacon="bright", camera_id=0, mirror=False):

        self.mode = beacon
        self.camera_id = camera_id
        self.mirror = mirror
        self.detect = DETECTORS[beacon]

        self.positions = []
        self._running = False
        self._thread = None
        self.cap = None
        self.box = None
        self.error = None
        self._ready = threading.Event()
        self._positions_lock = threading.Lock()

    def _open(self):
        self.error = None
        try:
            import cv2
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                self.error = "摄像头打不开"
                self._release()
                return False
            return True
        except ImportError:
            self.error = "缺少OpenCV，请安装requirements-vision.txt"
        except Exception as exc:
            self.error = f"摄像头打开失败: {exc}"
        self._release()
        return False

    def _release(self):
        if self.cap is not None:
            cap = self.cap
            self.cap = None
            cap.release()

    def calibrate(self, seconds=CALIB_SECONDS):

        """
        采集数秒位置样本, 用5/95分位定键盘区域。
        返回 True/False。
        """

        self.box = None
        import numpy as np

        # 读取在后台线程内；主线程的校准与Ctrl+C不被cap.read阻塞。
        success = False
        try:
            if not self.start():
                return False
            print(f"[校准] 拿着发光的棒尖，在舒适范围内右上-左下来回移动 {seconds:.0f} 秒...")
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if self.error or not self._running:
                    self.error = self.error or "校准期间视觉采集已停止"
                    return False
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

            with self._positions_lock:
                samples = [(x, y) for _, x, y in self.positions]
            if len(samples) < 20:
                self.error = f"校准只采到{len(samples)}个点"
                return False
            arr = np.array(samples)
            box = (float(np.percentile(arr[:, 0], 5)),
                   float(np.percentile(arr[:, 1], 5)),
                   float(np.percentile(arr[:, 0], 95)),
                   float(np.percentile(arr[:, 1], 95)))
            if box[2] - box[0] < 10 and box[3] - box[1] < 10:
                self.error = "校准移动范围太小"
                return False
            self.box = box
            print(f"[校准] 完成，键盘区域 x {box[0]:.0f}~{box[2]:.0f} "
                  f"y {box[1]:.0f}~{box[3]:.0f}")
            success = True
            # 成功后持续取帧，避免等待回车时在相机后端积压旧帧。
            return True
        finally:
            if not success:
                self.stop()

    def _loop(self):
        cap = None
        try:
            if self.cap is None and not self._open():
                return
            cap = self.cap
            while self._running:
                read_started = time.monotonic()
                ok, frame = cap.read()
                captured_at = time.monotonic()
                if not self._running:
                    break
                if not ok:
                    self.error = "录制时摄像头读取失败"
                    break
                if captured_at - read_started > MAX_FRAME_READ_S:
                    # 阻塞后返回的帧曝光时刻不明，不把它当作当前姿态。
                    continue
                hit = self.detect(frame)
                if hit is not None:
                    with self._positions_lock:
                        self.positions.append((captured_at, hit[0], hit[1]))
                        # 校准后等待用户时仍读帧；限制缓存，保留约数分钟数据。
                        if len(self.positions) > 20000:
                            del self.positions[:10000]
                self._ready.set()
        except Exception as exc:
            self.error = f"视觉跟踪失败: {exc}"
        finally:
            self._running = False
            try:
                if cap is not None:
                    cap.release()
            except Exception as exc:
                self.error = self.error or f"摄像头释放失败: {exc}"
            finally:
                self.cap = None
                self._ready.set()

    def start(self):

        if self._thread is not None and self._thread.is_alive():
            if self.error or not self._running:
                self.error = self.error or "视觉采集线程尚未停止"
                return False
            # 校准结束后沿用相同摄像头，只清空会话样本。
            with self._positions_lock:
                self.positions.clear()
            return True
        # 校准成功后的相机断开不静默重开，交给调用方明确回退。
        if self.box is not None and self.error:
            return False
        with self._positions_lock:
            self.positions.clear()
        self._ready.clear()
        self.error = None

        self._running = True

        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
        )

        try:
            self._thread.start()
            if not self._ready.wait(CAMERA_TIMEOUT):
                self.error = "摄像头未及时就绪，本次视觉数据弃用"
                self._running = False
                return False
            return self._running and self.error is None
        except Exception as exc:
            self.error = f"视觉采集启动失败: {exc}"
            self._running = False
            self._thread = None
            self._release()
            return False

    def stop(self):

        self._running = False

        if self._thread is not None:

            self._thread.join(timeout=CAMERA_TIMEOUT)

            if self._thread.is_alive():
                self.error = "摄像头读取未及时结束，本次视觉数据弃用"
                # 不在另一线程read期间release；由采集线程退出时回收。
                return
            self._thread = None

        self._release()

    def levels(self, origin=0.0, duration=None):

        """
        返回 [(相对origin的秒数, -1/0/+1)]。
        origin为SessionClock估计的CSV起点；duration指定时只保留录制区间。
        """

        if self.box is None:
            return []

        with self._positions_lock:
            positions = list(self.positions)

        minx, _, maxx, _ = self.box

        out = []

        for t, x, y in positions:

            if not (duration is None or 0.0 <= t - origin <= duration):
                continue

            if self.mirror:

                x = minx + (maxx - x)

            out.append(
                (
                    t - origin,
                    level_from_pos(
                        (x, y), self.box
                    ),
                )
            )

        return out
