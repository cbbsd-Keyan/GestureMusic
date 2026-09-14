"""UDP motion control, independent of audio processing and device libraries."""
from collections import deque
import math


class WandControl:
    def __init__(self):
        self.samples = deque(maxlen=1000)
        self.last_packet = None
        self.last_stamp = None
        self.quiet_since = None
        self.paused = True
        self.volume = .15
        self.rms = 0.
        self.rate = 0.  # Retained for snapshot compatibility; it no longer controls speed.
        self.tempo = 1.
        self.tempo_status = 'FIXED'
        self.status = 'WAITING'
        self.enabled = True

    def ingest(self, line, now):
        try:
            values = [float(v) for v in line.split(',')]
        except ValueError:
            return False
        if len(values) != 7 or not all(map(math.isfinite, values)):
            return False
        stamp = values[0] / 1000.
        if stamp < 0:
            return False
        # Duplicate/out-of-order packets cannot keep a dead connection alive.
        if self.last_stamp is not None and stamp <= self.last_stamp:
            if stamp == self.last_stamp or (self.last_packet is not None and now - self.last_packet < 1.):
                return False
        if self.last_packet is not None and now - self.last_packet >= 1.:
            # Also handles a stalled UI polling again after the board reconnects.
            self.samples.clear()
            self.quiet_since = None
            self.paused = True
        self.last_stamp = stamp
        self.last_packet = now
        self.samples.append((now, stamp, math.hypot(*values[4:])))
        return True

    def update(self, now):
        if self.last_packet is None or now - self.last_packet >= 1.:
            self.status = 'WAITING' if self.last_packet is None else 'DISCONNECTED'
            self.paused = True
            self.samples.clear()
            self.quiet_since = None
            self.rms = self.rate = 0.
            self.tempo = 1.
            self.tempo_status = 'FIXED'
            self.volume = .15
            return
        while self.samples and self.samples[0][0] < now - 1.5:
            self.samples.popleft()
        mags = [s[2] for s in self.samples]
        self.rms = math.hypot(*mags) / math.sqrt(len(mags))
        # Preserve the existing conductor's gyro mapping for this integration.
        energy = max(0., min(1., (self.rms - .5) / 4.))
        self.volume += .3 * (.15 + .85 * energy - self.volume)
        active = sum(m > .5 for m in mags) / len(mags)
        if active < .05:
            if self.quiet_since is None:
                self.quiet_since = now
            if now - self.quiet_since >= .5:
                self.paused = True
        else:
            self.quiet_since = None
            self.paused = False
        self.status = 'QUIET' if self.paused else 'ACTIVE'
        # Real-time speed control is intentionally disabled in the product.
        self.tempo = 1.
        self.tempo_status = 'FIXED'

    def poll(self, reader, now):
        for _ in range(200):
            line = reader.read()
            if line is None:
                break
            self.ingest(line, now)
        self.update(now)

    def apply(self, playback):
        if self.enabled:
            playback.paused = self.paused
            playback.set_volume(self.volume)
