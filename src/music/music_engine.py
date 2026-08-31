import time
from collections import deque
from statistics import median


class MusicEngine:

    def __init__(
        self,
        midi,
        enable_chords=True,
        enable_bass=True,
        enable_melody=True,
        enable_drums=False,
    ):

        self.midi = midi

        # =========================
        # 音乐层开关
        # =========================

        self.enable_chords = enable_chords
        self.enable_bass = enable_bass
        self.enable_melody = enable_melody
        self.enable_drums = enable_drums

        # =========================
        # 音乐数据
        # =========================

        self.chords = [
            [60, 64, 67],  # C
            [57, 60, 64],  # Am
            [53, 57, 60],  # F
            [55, 59, 62],  # G
        ]

        self.chord_names = [
            "C",
            "Am",
            "F",
            "G",
        ]

        self.bass_notes = [
            36,
            33,
            29,
            31,
        ]

        self.melody_notes = [
            [60, 64, 67],
            [57, 60, 64],
            [53, 57, 60],
            [55, 59, 62],
        ]

        self.drum_pattern = [
            36,  # kick
            42,  # hihat
            38,  # snare
            42,  # hihat
        ]

        # =========================
        # 音乐状态
        # =========================

        self.beat = 0

        self.roll = 0.0
        self.height = 1

        self.current_chord = None
        self.current_bass = None
        self.last_melody = None

        # =========================
        # Tempo跟随
        # =========================

        self.tap_times = deque(maxlen=6)

        self.intervals = deque(maxlen=5)

        self.bpm = None

        # 是否已经进入自动播放
        self.transport_running = False

        # 下一拍应该在什么时间播放
        self.next_beat_time = None

        # 最近一次识别到真实挥动
        self.last_real_beat_time = None

        self.MIN_BPM = 30
        self.MAX_BPM = 180

        self.MIN_INTERVAL = (
            60.0 / self.MAX_BPM
        )

        self.MAX_INTERVAL = (
            60.0 / self.MIN_BPM
        )

        # 至少需要几个有效间隔才锁定节拍
        # 3个间隔 = 4次有效挥动
        self.INTERVALS_TO_LOCK = 3

        # 多久完全没有检测到挥动后停止
        self.NO_BEAT_TIMEOUT = 3.0


    # ========================================================
    # Roll
    # ========================================================

    def update_roll(self, value):

        self.roll = value

        if value < -15:
            new_height = 0

        elif value > 15:
            new_height = 2

        else:
            new_height = 1

        if new_height != self.height:

            self.height = new_height

            print(
                f"Roll {self.roll:6.1f}° -> "
                f"{['LOW', 'MID', 'HIGH'][self.height]}"
            )


    # ========================================================
    # 收到真实BEAT
    # ========================================================

    def handle_beat(self):

        now = time.perf_counter()

        self.last_real_beat_time = now

        # -------------------------
        # 计算拍间隔
        # -------------------------

        if len(self.tap_times) == 0:

            # 第一拍：只记录时间戳
            self.tap_times.append(now)

        else:

            interval = (
                now - self.tap_times[-1]
            )

            if interval < self.MIN_INTERVAL:

                # 间隔太短：同一次挥动的重复包，忽略
                pass

            elif interval > self.MAX_INTERVAL:

                # 间隔太久：之前的时间锚点已过期，
                # 以这一拍重新开始计拍
                self.tap_times.clear()
                self.tap_times.append(now)

                print(
                    f"间隔 {interval:.1f}s 太久 "
                    f"(有效范围 "
                    f"{self.MIN_INTERVAL:.1f}"
                    f"-{self.MAX_INTERVAL:.1f}s)，"
                    f"重新开始计拍"
                )

            else:

                self.tap_times.append(now)
                self.intervals.append(interval)

        # -------------------------
        # 用中位数估计Tempo
        # -------------------------

        if len(self.intervals) > 0:

            stable_interval = median(
                self.intervals
            )

            measured_bpm = (
                60.0 / stable_interval
            )

            # 已经有BPM后做一点平滑
            if self.bpm is None:

                self.bpm = measured_bpm

            else:

                self.bpm = (
                    0.75 * self.bpm
                    + 0.25 * measured_bpm
                )

        # =====================================================
        # 尚未锁定节拍：
        # 每次识别到BEAT仍然立即播放
        # =====================================================

        if not self.transport_running:

            self.play_beat()

            if (
                self.bpm is not None
                and
                len(self.intervals)
                >= self.INTERVALS_TO_LOCK
            ):

                self.transport_running = True

                period = (
                    60.0 / self.bpm
                )

                # 当前这拍刚刚已经播放，
                # 下一拍从一个period以后开始
                self.next_beat_time = (
                    now + period
                )

                print(
                    f">>> TEMPO LOCKED: "
                    f"{self.bpm:.1f} BPM"
                )

            return

        # =====================================================
        # 已锁定：
        # 不再因为真实挥动直接播放，
        # 只校准下一拍
        # =====================================================

        period = 60.0 / self.bpm

        target_next = (
            now + period
        )

        # 不直接硬跳，做轻微相位校准
        self.next_beat_time = (
            0.7 * self.next_beat_time
            + 0.3 * target_next
        )


    # ========================================================
    # 主循环不断调用
    # ========================================================

    def update(self):

        if not self.transport_running:
            return

        now = time.perf_counter()

        # -------------------------
        # 太久没有真实挥动
        # -------------------------

        if (
            self.last_real_beat_time is not None
            and
            now - self.last_real_beat_time
            > self.NO_BEAT_TIMEOUT
        ):

            print(">>> No beat detected, transport stopped")

            self.transport_running = False

            self.tap_times.clear()
            self.intervals.clear()

            self.bpm = None
            self.next_beat_time = None

            self.stop_current_sound()

            return

        # -------------------------
        # 到时间自动播放下一拍
        # -------------------------

        if (
            self.next_beat_time is not None
            and
            now >= self.next_beat_time
        ):

            self.play_beat()

            period = (
                60.0 / self.bpm
            )

            # 用+=而不是now+period，
            # 减少长期计时漂移
            self.next_beat_time += period

            # 如果电脑偶尔卡顿太严重，
            # 不要疯狂补播很多拍
            if (
                self.next_beat_time
                < now - period
            ):
                self.next_beat_time = (
                    now + period
                )


    # ========================================================
    # 真正播放一拍
    # ========================================================

    def play_beat(self):

        chord_index = (
            self.beat // 4
        ) % 4

        beat_in_bar = (
            self.beat % 4
        )

        # -------------------------
        # 每4拍换和弦
        # -------------------------

        if beat_in_bar == 0:

            if (
                self.current_chord is not None
                and self.enable_chords
            ):

                self.midi.stop_chord(
                    self.current_chord
                )

            if (
                self.current_bass is not None
                and self.enable_bass
            ):

                self.midi.stop_bass(
                    self.current_bass
                )

            self.current_chord = (
                self.chords[chord_index]
            )

            self.current_bass = (
                self.bass_notes[chord_index]
            )

            if self.enable_chords:

                self.midi.play_chord(
                    self.current_chord
                )

            if self.enable_bass:

                self.midi.play_bass(
                    self.current_bass
                )

        # -------------------------
        # Drum，可选
        # -------------------------

        if self.enable_drums:

            drum_note = (
                self.drum_pattern[
                    beat_in_bar
                ]
            )

            self.midi.play_drum(
                drum_note
            )

        # -------------------------
        # Melody
        # -------------------------

        melody_note = None

        if self.enable_melody:

            if self.last_melody is not None:

                self.midi.stop_melody(
                    self.last_melody
                )

            melody_note = (
                self.melody_notes[
                    chord_index
                ][self.height]
            )

            if self.height == 2:
                melody_note += 12

            self.midi.play_melody(
                melody_note
            )

            self.last_melody = (
                melody_note
            )

        # -------------------------
        # Debug
        # -------------------------

        bpm_text = (
            "---"
            if self.bpm is None
            else f"{self.bpm:5.1f}"
        )

        mode = (
            "AUTO"
            if self.transport_running
            else "LEARN"
        )

        print(
            f"BEAT {self.beat + 1:2d} | "
            f"{mode:5s} | "
            f"BPM {bpm_text} | "
            f"Chord {self.chord_names[chord_index]:2s} | "
            f"Roll {self.roll:6.1f}° | "
            f"{['LOW', 'MID', 'HIGH'][self.height]}"
        )

        self.beat += 1


    # ========================================================
    # 停止当前持续音
    # ========================================================

    def stop_current_sound(self):

        if self.current_chord is not None:

            self.midi.stop_chord(
                self.current_chord
            )

        if self.current_bass is not None:

            self.midi.stop_bass(
                self.current_bass
            )

        if self.last_melody is not None:

            self.midi.stop_melody(
                self.last_melody
            )

        self.current_chord = None
        self.current_bass = None
        self.last_melody = None


    # ========================================================
    # 调试开关
    # ========================================================

    def toggle_drums(self):

        self.enable_drums = (
            not self.enable_drums
        )

        print(
            "Drums:",
            "ON" if self.enable_drums else "OFF"
        )


    def toggle_bass(self):

        self.enable_bass = (
            not self.enable_bass
        )

        if (
            not self.enable_bass
            and self.current_bass is not None
        ):

            self.midi.stop_bass(
                self.current_bass
            )

        print(
            "Bass:",
            "ON" if self.enable_bass else "OFF"
        )


    def toggle_chords(self):

        self.enable_chords = (
            not self.enable_chords
        )

        if (
            not self.enable_chords
            and self.current_chord is not None
        ):

            self.midi.stop_chord(
                self.current_chord
            )

        print(
            "Chords:",
            "ON" if self.enable_chords else "OFF"
        )


    def toggle_melody(self):

        self.enable_melody = (
            not self.enable_melody
        )

        if (
            not self.enable_melody
            and self.last_melody is not None
        ):

            self.midi.stop_melody(
                self.last_melody
            )

            self.last_melody = None

        print(
            "Melody:",
            "ON" if self.enable_melody else "OFF"
        )


    def close(self):

        self.stop_current_sound()