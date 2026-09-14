"""Hardware-neutral menu state for the desktop control panel."""
from dataclasses import dataclass, field
from enum import Enum


class Phase(str, Enum):
    MENU = 'menu'
    COMPOSE_STYLE = 'compose_style'
    COMPOSE_READY = 'compose_ready'
    COMPOSE_COUNTDOWN = 'compose_countdown'
    COMPOSE_RECORDING = 'compose_recording'
    COMPOSE_CANCEL_CONFIRM = 'compose_cancel_confirm'
    COMPOSE_GENERATING = 'compose_generating'
    COMPOSE_RESULT = 'compose_result'
    COMPOSE_PREVIEW = 'compose_preview'
    CALIBRATION_READY = 'calibration_ready'
    CALIBRATION_COUNTDOWN = 'calibration_countdown'
    CALIBRATION_RECORDING = 'calibration_recording'
    CALIBRATION_CANCEL_CONFIRM = 'calibration_cancel_confirm'
    CALIBRATION_REVIEW = 'calibration_review'
    CONDUCT_LIBRARY = 'conduct_library'
    CONDUCT_ARMED = 'conduct_armed'
    CONDUCT_PLAYING = 'conduct_playing'
    CONDUCT_PAUSED = 'conduct_paused'


MENU_ITEMS = ('动作作曲', '音乐指挥')
RESULT_ITEMS = ('试听', '保存', '重录')
COMPOSE_STYLE_ITEMS = ('整体听感', '起伏映射', '个人校准')


@dataclass
class MenuState:
    """State transitions only; audio, UDP and display are attached later."""
    songs: tuple = ('月光曲', '卡农摇滚（分轨）')
    phase: Phase = Phase.MENU
    selected: int = 0
    static_energy: bool = True
    calibration_scene: int = 0
    song_index: int = 0
    sequence: int = 0
    deadline: float | None = None
    intents: list = field(default_factory=list)

    def _set(self, phase, selected=0, deadline=None, intent=None):
        self.phase = phase
        self.selected = selected
        self.deadline = deadline
        self.sequence += 1
        if intent:
            self.intents.append(intent)

    def _items(self):
        if self.phase == Phase.MENU:
            return MENU_ITEMS
        if self.phase == Phase.COMPOSE_STYLE:
            return COMPOSE_STYLE_ITEMS
        if self.phase == Phase.COMPOSE_RESULT:
            return RESULT_ITEMS
        if self.phase == Phase.CONDUCT_LIBRARY:
            return self.songs
        return ()

    def rotate(self, delta):
        items = self._items()
        if not items:
            return False
        self.selected = (self.selected + delta) % len(items)
        self.sequence += 1
        return True

    def short_press(self, now):
        if self.phase == Phase.MENU:
            self._set(Phase.COMPOSE_STYLE if self.selected == 0 else Phase.CONDUCT_LIBRARY)
        elif self.phase == Phase.COMPOSE_STYLE:
            if self.selected == 2:
                self.calibration_scene = 0
                self._set(Phase.CALIBRATION_READY, intent='prepare_calibration')
            else:
                self.static_energy = self.selected == 0
                self._set(Phase.COMPOSE_READY, intent='prepare_compose')
        elif self.phase == Phase.COMPOSE_READY:
            self._set(Phase.COMPOSE_COUNTDOWN, deadline=now + 3.)
        elif self.phase == Phase.COMPOSE_RECORDING:
            self._set(Phase.COMPOSE_GENERATING, intent='finish_recording')
        elif self.phase == Phase.COMPOSE_CANCEL_CONFIRM:
            self._set(Phase.COMPOSE_READY, intent='cancel_recording')
        elif self.phase == Phase.COMPOSE_RESULT:
            if self.selected == 0:
                self._set(Phase.COMPOSE_PREVIEW, intent='preview_score')
            elif self.selected == 1:
                self.intents.append('save_score')
            else:
                self._set(Phase.COMPOSE_READY, intent='prepare_compose')
        elif self.phase == Phase.CONDUCT_LIBRARY:
            self.song_index = self.selected
            self._set(Phase.CONDUCT_ARMED, intent='arm_conductor')
        elif self.phase == Phase.CONDUCT_PLAYING:
            self._set(Phase.CONDUCT_PAUSED, intent='pause_conductor')
        elif self.phase == Phase.CONDUCT_PAUSED:
            # Resume means waiting for a renewed gesture, not forcing audio onward.
            self._set(Phase.CONDUCT_ARMED, intent='resume_conductor')
        elif self.phase == Phase.CALIBRATION_READY:
            self._set(Phase.CALIBRATION_COUNTDOWN, deadline=now + 3.)
        elif self.phase == Phase.CALIBRATION_CANCEL_CONFIRM:
            self._set(Phase.COMPOSE_STYLE, intent='cancel_calibration')
        elif self.phase == Phase.CALIBRATION_REVIEW:
            self._set(Phase.COMPOSE_STYLE, intent='save_calibration')
        else:
            return False
        return True

    def long_press(self):
        if self.phase == Phase.MENU:
            return False
        if self.phase == Phase.COMPOSE_GENERATING:
            return False  # A rule-composition worker is allowed to finish cleanly.
        if self.phase == Phase.CALIBRATION_RECORDING:
            self._set(Phase.CALIBRATION_CANCEL_CONFIRM)
            return True
        if self.phase == Phase.CALIBRATION_CANCEL_CONFIRM:
            self._set(Phase.CALIBRATION_RECORDING)
            return True
        if self.phase == Phase.CALIBRATION_REVIEW:
            self.calibration_scene = 0
            self._set(Phase.CALIBRATION_READY, intent='restart_calibration')
            return True
        if self.phase == Phase.COMPOSE_RECORDING:
            self._set(Phase.COMPOSE_CANCEL_CONFIRM)
        elif self.phase == Phase.COMPOSE_CANCEL_CONFIRM:
            self._set(Phase.COMPOSE_RECORDING)
        else:
            self._set(Phase.MENU, intent='leave_current_mode')
        return True

    def tick(self, now):
        if self.phase == Phase.COMPOSE_COUNTDOWN and now >= self.deadline:
            self._set(Phase.COMPOSE_RECORDING, intent='start_recording')
            return True
        if self.phase == Phase.CALIBRATION_COUNTDOWN and now >= self.deadline:
            self._set(Phase.CALIBRATION_RECORDING, intent='start_calibration_segment')
            return True
        return False

    def external(self, event):
        """Reserved for later workers: recording, generation and wand playback."""
        if event == 'recording_finished':
            self._set(Phase.COMPOSE_GENERATING, intent='finish_recording')
            return True
        if event == 'recording_failed':
            self._set(Phase.COMPOSE_READY)
            return True
        if event == 'calibration_segment_finished':
            if self.calibration_scene < 2:
                self.calibration_scene += 1
                self._set(Phase.CALIBRATION_READY, intent='prepare_next_calibration_segment')
            else:
                self._set(Phase.CALIBRATION_REVIEW, intent='compute_calibration')
            return True
        if event == 'calibration_failed':
            self._set(Phase.CALIBRATION_READY)
            return True
        transitions = {
            'generation_complete': Phase.COMPOSE_RESULT,
            'generation_error': Phase.COMPOSE_READY,
            'preview_finished': Phase.COMPOSE_RESULT,
            'preview_error': Phase.COMPOSE_RESULT,
            'wand_started': Phase.CONDUCT_PLAYING,
            'wand_paused': Phase.CONDUCT_PAUSED,
            'conductor_finished': Phase.CONDUCT_LIBRARY,
            'conductor_error': Phase.CONDUCT_LIBRARY,
        }
        phase = transitions.get(event)
        if phase is None:
            return False
        self._set(phase)
        return True

    def consume_intents(self):
        intents, self.intents = self.intents, []
        return intents

    def snapshot(self):
        items = self._items()
        return {
            'type': 'state',
            'sequence': self.sequence,
            'mode': ('calibration' if self.phase.value.startswith('calibration')
                     else 'compose' if self.phase.value.startswith('compose')
                     else 'conduct' if self.phase.value.startswith('conduct')
                     else 'idle'),
            'phase': self.phase.value,
            'items': items,
            'selected': items[self.selected] if items else None,
            'compose_style': 'static' if self.static_energy else 'dynamic',
            'calibration_scene': ('vigorous', 'gentle', 'free')[self.calibration_scene],
            'song_index': self.song_index,
        }
