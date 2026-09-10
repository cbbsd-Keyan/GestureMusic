"""把设备相对时间映射到主机单调时钟，不依赖系统日期。"""
import math


class SessionClock:
    def __init__(self):
        self.first_device_ms = None
        self.last_device_ms = None
        self.first_received = None
        self.origin = None
        self.max_offset = None
        self.samples = 0
        self.duplicates = 0

    def observe(self, device_ms, received_at):
        if not math.isfinite(device_ms) or not math.isfinite(received_at):
            raise ValueError("动作时间戳必须为有限数值")
        if self.last_device_ms is not None:
            if device_ms < self.last_device_ms:
                raise ValueError("动作时间戳倒退，可能发生乱序或开发板重启，请重新录制")
            if device_ms == self.last_device_ms:
                self.duplicates += 1
                return False
        if self.first_device_ms is None:
            self.first_device_ms = device_ms
            self.first_received = received_at
        offset = received_at - (device_ms - self.first_device_ms) / 1000.0
        self.origin = offset if self.origin is None else min(self.origin, offset)
        self.max_offset = offset if self.max_offset is None else max(self.max_offset, offset)
        self.last_device_ms = device_ms
        self.samples += 1
        return True

    def summary(self):
        return {
            "method": "minimum_receive_offset",
            "first_sample_monotonic": self.first_received,
            "host_origin_monotonic": self.origin,
            "first_device_ms": self.first_device_ms,
            "duration_s": ((self.last_device_ms - self.first_device_ms) / 1000.0
                           if self.samples else 0.0),
            "samples": self.samples,
            "duplicate_samples": self.duplicates,
            "receive_offset_span_s": (self.max_offset - self.origin if self.samples else 0.0),
        }
