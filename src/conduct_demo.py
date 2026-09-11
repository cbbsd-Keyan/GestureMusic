import argparse
import sys
import time
import threading
import statistics
import math
from pathlib import Path

import numpy as np

try:
    import sounddevice as sd
    import soundfile as sf
except ImportError:
    print("需要: .venv\\Scripts\\python.exe -m pip install sounddevice soundfile")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "input"))

from udp_reader import UDPReader


# =========================
# 参数
# =========================

CONTROL_INTERVAL = 0.1      # 控制循环周期(秒)
ENERGY_WINDOW = 1.0         # 能量滑窗(秒)
PAUSE_THRESHOLD = 0.05      # 活跃度低于此值触发暂停
PAUSE_DELAY = 0.5           # 暂停前的等待时间
FADE_TIME = 0.4             # 淡入淡出时间(秒)
GAIN_FLOOR = 0.15           # 活跃时最低音量
GAIN_CEIL = 1.0             # 最大音量
TEMPO_MIN = 0.7             # 最慢播放速度
TEMPO_MAX = 1.3             # 最快播放速度
TEMPO_REF_RATE = 1.5        # 参考挥动频率(次/秒, 约90BPM)

SAMPLE_RATE = 44100
BLOCK_SIZE = 1024


# =========================
# 音频加载
# =========================

def load_audio(path):
    data, sr = sf.read(str(path), dtype="float32")
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    return data, sr


# =========================
# 控制参数(线程共享)
# =========================

class Params:
    def __init__(self):
        self.gain = 0.0
        self.stride = 1.0
        self.paused = True
        self.running = True
        self.position = 0.0
        self.energy = 0.0
        self.rate = 0.0
        self.active = 0.0
        self._lock = threading.Lock()

    def set(self, **kw):
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, v)

    def get(self, key):
        with self._lock:
            return getattr(self, key)


# =========================
# 控制循环(传感器→参数)
# =========================

def control_loop(reader, params, audio_len):

    gyro_buf = []       # (monotonic, magnitude)
    last_active_time = 0.0
    pause_start = None

    while params.running:

        t0 = time.monotonic()

        # ---------- 读UDP ----------

        for _ in range(50):

            line = reader.read()

            if line is None:
                break

            parts = line.split(",")

            if len(parts) != 7:
                continue

            try:

                now = time.monotonic()
                vals = [float(x) for x in parts]
                mag = math.sqrt(vals[4]**2 + vals[5]**2 + vals[6]**2)
                gyro_buf.append((now, mag))

            except ValueError:
                continue

        now = time.monotonic()

        # 清旧数据
        cutoff = now - ENERGY_WINDOW - 0.5

        gyro_buf = [(t, m) for t, m in gyro_buf if t > cutoff]

        if not gyro_buf:
            time.sleep(CONTROL_INTERVAL)
            continue

        mags = [m for _, m in gyro_buf]

        # ---------- 能量 ----------

        rms = math.sqrt(statistics.fmean(m * m for m in mags))

        energy = max(0.0, min(1.0, (rms - 0.5) / 4.0))

        # ---------- 活跃度 ----------

        active_thr = 0.5

        active_count = sum(1 for m in mags if m > active_thr)

        active_ratio = active_count / len(mags)

        # ---------- 挥动频率 ----------

        # 简化峰计数: 超过中位数+0.5*MAD的局部峰
        med = statistics.median(mags)
        mad = statistics.median(abs(m - med) for m in mags)
        peak_thr = med + max(0.3, 1.5 * mad)

        peaks = 0
        for i in range(1, len(mags) - 1):
            if mags[i] >= mags[i-1] and mags[i] > mags[i+1] and mags[i] > peak_thr:
                peaks += 1

        span = max(0.1, gyro_buf[-1][0] - gyro_buf[0][0])
        rate = peaks / span  # 次/秒

        # ---------- 暂停判断 ----------

        if active_ratio < PAUSE_THRESHOLD:

            if pause_start is None:
                pause_start = now

            if now - pause_start > PAUSE_DELAY:
                params.set(paused=True, energy=0, rate=0, active=active_ratio)

        else:

            pause_start = None

            # ---------- 增益 ----------

            target_gain = GAIN_FLOOR + (GAIN_CEIL - GAIN_FLOOR) * energy

            # 平滑
            current = params.get("gain")

            if current < 0.01:
                current = target_gain  # 从暂停恢复时不渐变

            smooth = current + (target_gain - current) * 0.3

            # ---------- 变速 ----------

            ratio = rate / TEMPO_REF_RATE

            target_stride = max(TEMPO_MIN, min(TEMPO_MAX, ratio))

            current_stride = params.get("stride")

            smooth_stride = current_stride + (target_stride - current_stride) * 0.2

            params.set(
                gain=smooth,
                stride=smooth_stride,
                paused=False,
                energy=energy,
                rate=rate,
                active=active_ratio,
            )

        # ---------- 控制台显示 ----------

        status = "暂停" if params.get("paused") else "播放"

        gain_pct = params.get("gain") * 100
        stride = params.get("stride")
        bar = "■" * int(energy * 10) + "□" * (10 - int(energy * 10))

        print(
            f"\r[指挥] {status} | "
            f"音量 {gain_pct:3.0f}% | "
            f"速度 {stride:.2f}x | "
            f"能量 {bar} | "
            f"频率 {rate:.1f}/s ",
            end="",
            flush=True,
        )

        elapsed = time.monotonic() - t0

        sleep_time = max(0.01, CONTROL_INTERVAL - elapsed)

        time.sleep(sleep_time)


# =========================
# 音频回调(sounddevice)
# =========================

def make_audio_callback(audio_data, params):

    def callback(outdata, frames, time_info, status):

        if status:
            pass

        paused = params.get("paused")
        gain = params.get("gain")
        stride = params.get("stride")
        pos = params.get("position")

        if paused:

            # 渐弱
            fade = np.linspace(gain, 0, frames, dtype=np.float32)

            outdata[:] = (fade[:, None] * audio_data[
                int(pos):int(pos) + frames
            ][:outdata.shape[0]]).astype(np.float32) if int(pos) + frames <= len(audio_data) else 0.0

            # 简化: 直接静音
            outdata.fill(0)

            return

        # 生成采样位置(等差, 步长=stride)
        indices = pos + stride * np.arange(frames, dtype=np.float64)

        # 循环
        indices = indices % len(audio_data)

        # 线性插值
        idx0 = indices.astype(np.int64)
        idx1 = (idx0 + 1) % len(audio_data)
        frac = (indices - idx0).astype(np.float32)

        # 双声道
        for ch in range(min(2, audio_data.shape[1])):
            samples = (
                audio_data[idx0, ch] * (1 - frac)
                + audio_data[idx1, ch] * frac
            )
            outdata[:, ch] = samples * gain

        # 更新位置
        new_pos = (pos + stride * frames) % len(audio_data)

        params.set(position=new_pos)

    return callback


# =========================
# 主入口
# =========================

def main():

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="指挥模式: 挥动控制现成音频")

    parser.add_argument("audio", help="音频文件(WAV/MP3)")

    parser.add_argument(
        "--blocksize",
        type=int,
        default=BLOCK_SIZE,
        help=f"音频块大小(默认{BLOCK_SIZE})",
    )

    args = parser.parse_args()

    audio_path = Path(args.audio)

    if not audio_path.exists():
        print(f"[错误] 文件不存在: {audio_path}")
        sys.exit(1)

    print("===== 指挥模式 =====")
    print()

    # ---------- 加载音频 ----------

    print(f"[加载] {audio_path.name}")

    try:
        audio_data, sr = load_audio(audio_path)
    except Exception as e:
        print(f"[错误] 无法读取音频: {e}")
        print("提示: 如果是MP3, 请先转换为WAV")
        sys.exit(1)

    duration = len(audio_data) / sr

    print(f"[加载] {duration:.0f}秒 | {sr}Hz | {audio_data.shape[1]}声道")

    # ---------- 连接板子 ----------

    reader = UDPReader(port=4210)

    print("[等待板子]", end="", flush=True)

    alive = 0

    t0 = time.monotonic()

    while time.monotonic() - t0 < 5.0:
        line = reader.read()
        if line is not None:
            alive += 1
        time.sleep(0.02)

    if alive == 0:
        print(" 未检测到板子")
        print("请确认: 热点开着 / 板子上电 / 防火墙放行")
        reader.close()
        sys.exit(1)

    print(f" 在线(收到{alive}包)")

    # ---------- 启动 ----------

    params = Params()

    ctrl_thread = threading.Thread(
        target=control_loop,
        args=(reader, params, len(audio_data)),
        daemon=True,
    )

    callback = make_audio_callback(audio_data, params)

    print()
    print("挥动指挥棒控制音乐:")
    print("  强度 → 音量")
    print("  频率 → 快慢")
    print("  停手 → 暂停")
    print()
    print("按 Ctrl+C 退出")
    print()

    ctrl_thread.start()

    try:

        with sd.OutputStream(
            samplerate=sr,
            channels=audio_data.shape[1],
            blocksize=args.blocksize,
            callback=callback,
        ):

            while params.running:
                time.sleep(0.5)

    except KeyboardInterrupt:

        print("\n[退出]")

    finally:

        params.set(running=False)
        ctrl_thread.join(timeout=2)
        reader.close()

        print("[完成]")


if __name__ == "__main__":

    main()
