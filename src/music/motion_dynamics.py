"""把动作时间线映射到乐谱主体；力度连续变化，配器档位按小节稳定切换。"""
from bisect import bisect_right
import math


class MotionDynamics:
    ACTIVE_RATIO = 0.05

    def __init__(self, score, timeline, mode="song"):
        if mode not in ("song", "events"):
            raise ValueError("时间映射模式必须为song或events")
        self.mode = mode
        self.bars = score["bars"]
        self.bpm = float(score["bpm"])
        self.duration = float(timeline["duration_s"])
        if not math.isfinite(self.bpm) or self.bpm <= 0 or not isinstance(self.bars, int) or self.bars < 1:
            raise ValueError("无效乐谱时长或速度")
        if not math.isfinite(self.duration) or self.duration <= 0:
            raise ValueError("无效动作时长")
        self.points = timeline["points"]
        self.times = [p["t"] for p in self.points]
        if (not self.times or self.times[0] != 0 or abs(self.times[-1] - self.duration) > 1e-5
                or any(b <= a for a, b in zip(self.times, self.times[1:]))):
            raise ValueError("能量时间线必须递增并覆盖整段动作")
        for p in self.points:
            if (not all(math.isfinite(p[k]) for k in ("t", "energy", "active_ratio"))
                    or not 0 <= p["energy"] <= 1 or not 0 <= p["active_ratio"] <= 1):
                raise ValueError("无效能量或活动比例")
        self.grid_s = 60.0 / self.bpm / 4.0
        self.intro_seconds = 0.0
        self.bar_controls = []
        tier = None
        for bar in range(self.bars):
            # 多点平均，避免一个尖峰决定整小节的鼓型。
            samples = [self.at(bar * 16 + p) for p in (2, 6, 10, 14)]
            energy = sum(p[0] for p in samples) / 4
            activity = sum(p[1] for p in samples) / 4
            if activity < self.ACTIVE_RATIO:
                tier = "calm"
            elif tier is None:
                tier = "calm" if energy < 0.33 else "neutral" if energy < 0.7 else "intense"
            elif energy >= 0.75:
                tier = "intense"
            elif energy < 0.28:
                tier = "calm"
            elif tier == "calm" and energy >= 0.38:
                tier = "neutral"
            elif tier == "intense" and energy < 0.65:
                tier = "neutral"
            self.bar_controls.append({"bar": bar, "energy": energy,
                                      "active_ratio": activity, "tier": tier})

    def source_time(self, position):
        if self.mode == "events":
            return position * self.grid_s
        return position / (self.bars * 16) * self.duration

    def at(self, position):
        t = self.source_time(position)
        # 事件乐谱可能补足8小节；超出真实动作部分不持续沿用最后的强度。
        if t < 0 or t > self.duration + 1e-6:
            return 0.0, 0.0
        t = min(self.duration, t)
        i = max(0, min(len(self.times) - 1, bisect_right(self.times, t) - 1))
        a = self.points[i]
        b = self.points[min(i + 1, len(self.points) - 1)]
        f = 0.0 if a["t"] == b["t"] else (t - a["t"]) / (b["t"] - a["t"])
        return tuple(a[k] + f * (b[k] - a[k]) for k in ("energy", "active_ratio"))

    def active(self, position):
        return self.at(position)[1] >= self.ACTIVE_RATIO

    def gain(self, position):
        return 0.55 + 0.60 * self.at(position)[0]

    def tier(self, bar):
        return self.bar_controls[max(0, min(self.bars - 1, int(bar)))]["tier"]

    def release_position(self, start, end):
        # 静止段进入后至多一个十六分格停止持续音，避免悬挂的伴奏跨过停顿。
        for p in range(math.floor(start) + 1, math.ceil(end)):
            if not self.active(p):
                return p
        return end

    def report(self):
        return {"version": 1, "mapping": self.mode, "play_bpm": self.bpm,
                "body_start_s": self.intro_seconds, "body_duration_s": self.bars * 16 * self.grid_s,
                "motion_duration_s": self.duration, "bar_controls": self.bar_controls,
                "pitch_control": "score_unchanged", "tempo_control": "constant",
                "min_tier_hold_bars": 1, "inactive_ratio_threshold": self.ACTIVE_RATIO,
                "bar_mapping": [{"bar": b, "source_start_s": self.source_time(b * 16),
                                 "source_end_s": self.source_time((b + 1) * 16),
                                 "play_start_s": self.intro_seconds + b * 16 * self.grid_s,
                                 "play_end_s": self.intro_seconds + (b + 1) * 16 * self.grid_s}
                                for b in range(self.bars)]}
