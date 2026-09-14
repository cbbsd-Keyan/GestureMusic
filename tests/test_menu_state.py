from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from desktop.menu_state import MenuState, Phase


class MenuStateTests(unittest.TestCase):
    def test_home_selection_and_compose_countdown(self):
        state = MenuState()
        self.assertEqual(state.snapshot()['selected'], '动作作曲')
        state.rotate(1)
        self.assertEqual(state.snapshot()['selected'], '音乐指挥')
        state.rotate(-1)
        state.short_press(10.)
        self.assertEqual(state.phase, Phase.COMPOSE_STYLE)
        state.short_press(10.)
        self.assertEqual(state.phase, Phase.COMPOSE_READY)
        self.assertTrue(state.static_energy)
        self.assertEqual(state.consume_intents(), ['prepare_compose'])
        state.short_press(20.)
        self.assertEqual(state.phase, Phase.COMPOSE_COUNTDOWN)
        self.assertFalse(state.tick(22.9))
        self.assertTrue(state.tick(23.))
        self.assertEqual(state.phase, Phase.COMPOSE_RECORDING)
        self.assertEqual(state.consume_intents(), ['start_recording'])

    def test_compose_style_and_result_actions(self):
        state = MenuState()
        state.short_press(0.)
        state.rotate(1); state.short_press(0.)
        self.assertFalse(state.static_energy)
        self.assertEqual(state.consume_intents(), ['prepare_compose'])
        state.external('generation_complete')
        state.short_press(0.)
        self.assertEqual(state.phase, Phase.COMPOSE_PREVIEW)
        self.assertEqual(state.consume_intents(), ['preview_score'])
        state.external('preview_finished')
        state.rotate(1); state.short_press(0.)
        self.assertEqual(state.consume_intents(), ['save_score'])

    def test_record_cancel_requires_confirmation(self):
        state = MenuState(phase=Phase.COMPOSE_RECORDING)
        state.long_press()
        self.assertEqual(state.phase, Phase.COMPOSE_CANCEL_CONFIRM)
        state.long_press()
        self.assertEqual(state.phase, Phase.COMPOSE_RECORDING)
        state.long_press(); state.short_press(0.)
        self.assertEqual(state.phase, Phase.COMPOSE_READY)
        self.assertEqual(state.consume_intents(), ['cancel_recording'])

    def test_conductor_selection_and_external_wand_transitions(self):
        state = MenuState()
        state.rotate(1); state.short_press(0.)
        self.assertEqual(state.phase, Phase.CONDUCT_LIBRARY)
        state.short_press(0.)
        self.assertEqual(state.phase, Phase.CONDUCT_ARMED)
        self.assertEqual(state.consume_intents(), ['arm_conductor'])
        self.assertTrue(state.external('wand_started'))
        self.assertEqual(state.phase, Phase.CONDUCT_PLAYING)
        state.short_press(0.)
        self.assertEqual(state.phase, Phase.CONDUCT_PAUSED)
        self.assertEqual(state.consume_intents(), ['pause_conductor'])
        state.short_press(0.)
        self.assertEqual(state.phase, Phase.CONDUCT_ARMED)
        self.assertEqual(state.consume_intents(), ['resume_conductor'])

    def test_conductor_library_remembers_the_selected_song(self):
        state = MenuState()
        state.rotate(1)
        state.short_press(0.)
        state.rotate(1)
        self.assertEqual(state.snapshot()['selected'], '卡农摇滚（分轨）')
        state.short_press(0.)
        self.assertEqual(state.snapshot()['song_index'], 1)
        self.assertEqual(state.consume_intents(), ['arm_conductor'])

    def test_long_press_returns_to_menu_without_immediate_cancel(self):
        state = MenuState(phase=Phase.CONDUCT_ARMED)
        state.long_press()
        self.assertEqual(state.phase, Phase.MENU)
        self.assertEqual(state.consume_intents(), ['leave_current_mode'])

    def test_personal_calibration_has_three_visible_segments_and_explicit_save(self):
        state = MenuState()
        state.short_press(0.)
        state.rotate(2)
        state.short_press(0.)
        self.assertEqual(state.phase, Phase.CALIBRATION_READY)
        self.assertEqual(state.snapshot()['calibration_scene'], 'vigorous')
        self.assertEqual(state.consume_intents(), ['prepare_calibration'])

        state.short_press(10.)
        self.assertEqual(state.phase, Phase.CALIBRATION_COUNTDOWN)
        self.assertTrue(state.tick(13.))
        self.assertEqual(state.phase, Phase.CALIBRATION_RECORDING)
        self.assertEqual(state.consume_intents(), ['start_calibration_segment'])

        self.assertTrue(state.external('calibration_segment_finished'))
        self.assertEqual(state.snapshot()['calibration_scene'], 'gentle')
        self.assertEqual(state.consume_intents(), ['prepare_next_calibration_segment'])
        self.assertTrue(state.external('calibration_segment_finished'))
        self.assertEqual(state.snapshot()['calibration_scene'], 'free')
        self.assertTrue(state.external('calibration_segment_finished'))
        self.assertEqual(state.phase, Phase.CALIBRATION_REVIEW)
        self.assertEqual(state.consume_intents(), ['prepare_next_calibration_segment', 'compute_calibration'])

        state.short_press(14.)
        self.assertEqual(state.phase, Phase.COMPOSE_STYLE)
        self.assertEqual(state.consume_intents(), ['save_calibration'])

    def test_personal_calibration_cancel_and_restart_keep_confirmation_separate(self):
        state = MenuState(phase=Phase.CALIBRATION_RECORDING)
        state.long_press()
        self.assertEqual(state.phase, Phase.CALIBRATION_CANCEL_CONFIRM)
        state.long_press()
        self.assertEqual(state.phase, Phase.CALIBRATION_RECORDING)
        state.long_press()
        state.short_press(0.)
        self.assertEqual(state.phase, Phase.COMPOSE_STYLE)
        self.assertEqual(state.consume_intents(), ['cancel_calibration'])

        state = MenuState(phase=Phase.CALIBRATION_REVIEW, calibration_scene=2)
        state.long_press()
        self.assertEqual(state.phase, Phase.CALIBRATION_READY)
        self.assertEqual(state.snapshot()['calibration_scene'], 'vigorous')
        self.assertEqual(state.consume_intents(), ['restart_calibration'])


if __name__ == '__main__':
    unittest.main()
