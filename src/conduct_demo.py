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
FILTER_MIN_HZ = 200         # 明暗: 最低截止频率(很闷)
FILTER_MAX_HZ = 12000       # 明暗: 最高截止频率(几乎透明)
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
        self.filter_alpha = 1.0  # 1.0=不过滤(透明)
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

            # ---------- 明暗(滤波) ----------

            # 指数映射: energy 0→200Hz, 1→12000Hz
            cutoff_hz = FILTER_MIN_HZ * (
                FILTER_MAX_HZ / FILTER_MIN_HZ
            ) ** energy

            # 一阶低通系数
            import struct
            filter_alpha = 1.0 - math.exp(
                -2.0 * math.pi * cutoff_hz / SAMPLE_RATE
            )

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
                filter_alpha=filter_alpha,
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
# 颗粒合成时间拉伸(不变调变速)
# =========================

GRAIN_SIZE = 2048       # ~46ms
HOP_ANALYSIS = GRAIN_SIZE // 2  # 50%重叠
GRAIN_WINDOW = None     # 延迟初始化


def _get_window():
    global GRAIN_WINDOW
    if GRAIN_WINDOW is None:
        import numpy as _np
        GRAIN_WINDOW = _np.hanning(GRAIN_SIZE).astype(np.float32)
    return GRAIN_WINDOW


class GranularPlayer:
    """
    颗粒合成变速: 源匀速读(音高不变),
    颗粒在输出域按tempo排布(速度变化)。
    绝对坐标管理: acc_offset + grain_out_pos 始终一致。
    """

    def __init__(self, audio, tempo=1.0):
        self.audio = audio
        self.tempo = tempo
        self.input_pos = 0
        self.window = _get_window()

        # 绝对坐标
        self.acc = np.zeros(0, dtype=np.float32)
        self.acc_offset = 0      # acc[0] 对应的绝对输出位置
        self.grain_out_pos = 0   # 下一颗粒应放的绝对输出位置

        # 预填几个颗粒保证有数据
        for _ in range(4):
            self._add_grain()

    def set_tempo(self, t):
        self.tempo = max(0.5, min(1.5, t))

    def get_block(self, n):
        """取 n 个输出样本。"""
        # 确保积累够 n 个
        target_end = self.acc_offset + n
        while self.grain_out_pos < target_end:
            self._add_grain()

        result = self.acc[:n].copy()
        self.acc = self.acc[n:]
        self.acc_offset += n

        # 保持最小缓冲
        min_len = GRAIN_SIZE * 2
        if len(self.acc) < min_len:
            self.acc = np.concatenate([
                self.acc,
                np.zeros(min_len - len(self.acc), dtype=np.float32),
            ])

        return result

    def _add_grain(self):
        G = GRAIN_SIZE
        Ha = HOP_ANALYSIS  # 1024
        Hs = int(Ha * self.tempo)

        # 从源读颗粒(匀速)
        src = int(self.input_pos)
        if src + G >= len(self.audio):
            self.input_pos = 0
            src = 0
        grain = self.audio[src:src+G, 0].astype(np.float32) * self.window

        # 颗粒放在绝对输出位置 grain_out_pos
        idx = self.grain_out_pos - self.acc_offset

        # 确保缓冲够长
        needed = idx + G
        if needed > len(self.acc):
            self.acc = np.concatenate([
                self.acc,
                np.zeros(needed - len(self.acc) + G, dtype=np.float32),
            ])

        # 叠加
        self.acc[idx:idx+G] += grain

        # 推进
        self.input_pos += Ha
        self.grain_out_pos += Hs

    def reset(self):
        self.input_pos = 0
        self.acc = np.zeros(0, dtype=np.float32)
        self.acc_offset = 0
        self.grain_out_pos = 0
        for _ in range(4):
            self._add_grain()

# =========================
# 音频回调(sounddevice)
# =========================

def make_audio_callback(audio_data, params, use_filter=True, use_granular=False):

    # 滤波器状态(左右声道各自独立)
    filter_state = [0.0, 0.0]

    # 上一块的参数值(用于线性斜坡消除阶跃)
    prev_gain = 0.0
    prev_alpha = 1.0

    # 颗粒播放器(不变调变速)
    granular = GranularPlayer(audio_data) if use_granular else None

    def callback(outdata, frames, time_info, status):

        nonlocal filter_state, prev_gain, prev_alpha

        if status:
            pass

        paused = params.get("paused")
        stride = params.get("stride")
        pos = params.get("position")
        target_gain = params.get("gain")
        target_alpha = (
            params.get("filter_alpha") if use_filter else 1.0
        )

        if paused:
            outdata.fill(0)
            prev_gain = 0.0
            if granular:
                granular.reset()
            return

        # ---------- 线性斜坡(消灭参数阶跃) ----------

        gain_ramp = np.linspace(
            prev_gain, target_gain, frames, dtype=np.float32
        )

        alpha_ramp = np.linspace(
            prev_alpha, target_alpha, frames
        )

        prev_gain = target_gain
        prev_alpha = target_alpha

        # ---------- 获取音频样本 ----------

        if granular:
            # 颗粒模式: 不变调变速
            granular.set_tempo(stride)
            mono = granular.get_block(frames)
            # 复制到双声道
            for ch in range(min(2, audio_data.shape[1])):
                samples = mono * gain_ramp
                if target_alpha < 0.999:
                    out = np.empty(frames, dtype=np.float32)
                    prev = filter_state[ch]
                    for i in range(frames):
                        a = alpha_ramp[i]
                        prev = a * samples[i] + (1.0 - a) * prev
                        out[i] = prev
                    filter_state[ch] = prev
                    outdata[:, ch] = out
                else:
                    outdata[:, ch] = samples

        else:
            # 普通模式: 可变步长(会变调)
            indices = pos + stride * np.arange(frames, dtype=np.float64)
            indices = indices % len(audio_data)

            idx0 = indices.astype(np.int64)
            idx1 = (idx0 + 1) % len(audio_data)
            frac = (indices - idx0).astype(np.float32)

            for ch in range(min(2, audio_data.shape[1])):
                samples = (
                    audio_data[idx0, ch] * (1 - frac)
                    + audio_data[idx1, ch] * frac
                ) * gain_ramp

                if target_alpha < 0.999:
                    out = np.empty(frames, dtype=np.float32)
                    prev = filter_state[ch]
                    for i in range(frames):
                        a = alpha_ramp[i]
                        prev = a * samples[i] + (1.0 - a) * prev
                        out[i] = prev
                    filter_state[ch] = prev
                    outdata[:, ch] = out
                else:
                    outdata[:, ch] = samples

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
        "--no-filter",
        action="store_true",
        help="关闭明暗滤波(试验开关, 默认开启)",
    )

    parser.add_argument(
        "--granular",
        action="store_true",
        help="试验: 颗粒合成不变调变速(默认关闭, 用可变步长代替)",
    )

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

    callback = make_audio_callback(
        audio_data, params,
        use_filter=not args.no_filter,
        use_granular=args.granular,
    )

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
