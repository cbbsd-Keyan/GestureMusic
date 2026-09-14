"""Desktop panel: encoder-driven menu with the conductor playback mode attached."""
import argparse
import math
from pathlib import Path
import sys
import time

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from desktop.menu_state import MenuState
from input.encoder_reader import EncoderReader
from tempo_player import ConductorSession
from audio.stem_conductor import StemConductorSession
from composition_session import CalibrationSession, ComposeSession, MidiPreview


PHASE_TEXT = {
    'menu': '主菜单', 'compose_ready': '动作作曲：准备录制',
    'compose_style': '动作作曲：选择表现方式',
    'compose_countdown': '动作作曲：倒计时', 'compose_recording': '动作作曲：录制中',
    'compose_cancel_confirm': '确认取消？短按确认，长按继续录制',
    'compose_generating': '动作作曲：规则作曲与配器中',
    'compose_result': '动作作曲：作品就绪', 'compose_preview': '动作作曲：试听中',
    'calibration_ready': '个人校准：准备录制',
    'calibration_countdown': '个人校准：倒计时',
    'calibration_recording': '个人校准：录制中',
    'calibration_cancel_confirm': '确认取消校准？短按确认，长按继续录制',
    'calibration_review': '个人校准：结果确认',
    'conduct_library': '音乐指挥：选曲',
    'conduct_armed': '音乐指挥：等待挥动',
    'conduct_playing': '音乐指挥：播放中', 'conduct_paused': '音乐指挥：暂停',
}


def print_state(state):
    snapshot = state.snapshot()
    print('\n' + PHASE_TEXT[snapshot['phase']])
    for item in snapshot['items']:
        print(('> ' if item == snapshot['selected'] else '  ') + item)
    print(flush=True)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--encoder-port', default='COM9', help='编码器串口，当前板子为 COM9')
    parser.add_argument('--conductor-audio', type=Path, default=Path('moonlight.wav'),
                        help='月光曲 WAV 文件')
    parser.add_argument('--canon-midi', type=Path, default=BASE.parent / 'assets' / 'conductor' / 'canon_rock.mid',
                        help='卡农摇滚版 MIDI 文件')
    parser.add_argument('--audio-device', type=int, default=None,
                        help='sounddevice 输出设备号；省略则用系统默认设备')
    parser.add_argument('--midi-device', type=int, default=1, help='规则作曲试听的 MIDI 输出设备号')
    parser.add_argument('--subject', default='s00', help='个人校准与会话存档编号')
    args = parser.parse_args()
    try:
        reader = EncoderReader(args.encoder_port)
    except Exception as exc:
        parser.error(f'无法打开编码器 {args.encoder_port}: {exc}')

    state = MenuState()
    session = None
    compose = None
    calibration = None
    preview = None
    composition = None
    reported_stem_layers = None
    reported_countdown = None

    def stop_session():
        nonlocal session
        if session is not None:
            session.close()
            session = None

    def stop_compose():
        nonlocal compose
        if compose is not None:
            compose.close()
            compose = None

    def stop_calibration():
        nonlocal calibration
        if calibration is not None:
            calibration.cancel()
            calibration = None

    def stop_preview():
        nonlocal preview
        if preview is not None:
            preview.stop()
            preview = None

    def run_intents():
        nonlocal session, compose, calibration, preview, composition, reported_stem_layers
        state_changed = False
        for intent in state.consume_intents():
            if intent == 'arm_conductor':
                try:
                    stop_session()
                    reported_stem_layers = None
                    if state.song_index == 0:
                        session = ConductorSession(args.conductor_audio, args.audio_device)
                        song = '月光曲'
                    else:
                        session = StemConductorSession(args.canon_midi, args.midi_device)
                        song = '卡农摇滚（分轨）'
                    session.start()
                    print(f'[指挥模式] 《{song}》已准备，开始挥动即可播放。', flush=True)
                except Exception as exc:
                    stop_session()
                    state_changed = state.external('conductor_error') or state_changed
                    print(f'[指挥模式错误] {exc}', flush=True)
            elif intent == 'pause_conductor' and session is not None:
                session.pause()
            elif intent == 'resume_conductor' and session is not None:
                session.resume()
            elif intent == 'leave_current_mode':
                stop_session()
                stop_preview()
                stop_compose()
                stop_calibration()
            elif intent in ('prepare_calibration', 'restart_calibration'):
                stop_calibration()
                calibration = CalibrationSession(args.subject)
                print('[个人校准] 第1/3段：最大自然挥动。短按后倒计时，录制5秒自动结束。', flush=True)
            elif intent == 'prepare_next_calibration_segment' and calibration is not None:
                labels = {'vigorous': '最大自然挥动', 'gentle': '舒缓挥动', 'free': '自然发挥'}
                print(f'[个人校准] 下一段 {calibration.index + 1}/3：{labels[calibration.scene]}。短按开始。', flush=True)
            elif intent == 'start_calibration_segment' and calibration is not None:
                try:
                    calibration.start_segment()
                    labels = {'vigorous': '最大自然挥动', 'gentle': '舒缓挥动', 'free': '自然发挥'}
                    print(f'[个人校准录制] {labels[calibration.scene]}，保持5秒。', flush=True)
                except Exception as exc:
                    state_changed = state.external('calibration_failed') or state_changed
                    print(f'[校准录制错误] {exc}', flush=True)
            elif intent == 'compute_calibration' and calibration is not None:
                try:
                    report = calibration.build_report()
                    segments = report['segments']
                    print('[个人校准结果] '
                          f"锚值 {report['anchor_rms']:.3f} | "
                          f"gentle {segments['gentle']['normalized']:.2f} | "
                          f"free {segments['free']['normalized']:.2f}", flush=True)
                    print('短按使用此校准；长按重新录制三段。', flush=True)
                except Exception as exc:
                    state_changed = state.external('calibration_failed') or state_changed
                    print(f'[校准计算失败] {exc}', flush=True)
            elif intent == 'save_calibration' and calibration is not None:
                try:
                    baseline, report = calibration.save_baseline()
                    print(f'[个人校准已保存] {baseline}；明细 {report}', flush=True)
                    stop_calibration()
                except Exception as exc:
                    print(f'[校准保存失败] {exc}', flush=True)
                    state_changed = state.external('calibration_failed') or state_changed
            elif intent == 'cancel_calibration':
                stop_calibration()
                print('[个人校准已取消，旧基准未改变。', flush=True)
            elif intent == 'prepare_compose':
                try:
                    stop_preview()
                    stop_compose()
                    compose = ComposeSession(args.subject, state.static_energy)
                    compose.prepare()
                    style = '整体听感' if state.static_energy else '起伏映射'
                    print(f'[作曲模式] 已准备指挥棒数据流；本次为{style}。', flush=True)
                except Exception as exc:
                    stop_compose()
                    state_changed = state.external('recording_failed') or state_changed
                    print(f'[作曲模式错误] {exc}', flush=True)
            elif intent == 'start_recording' and compose is not None:
                try:
                    compose.start_recording()
                    print('[录制中] 短按结束；15秒会自动结束。', flush=True)
                except Exception as exc:
                    state_changed = state.external('recording_failed') or state_changed
                    print(f'[录制错误] {exc}', flush=True)
            elif intent == 'finish_recording' and compose is not None:
                csv_path, error = compose.finish_recording()
                if error:
                    state_changed = state.external('recording_failed') or state_changed
                    print(f'[录制失败] {error}', flush=True)
                else:
                    try:
                        compose.start_generation(csv_path)
                        print('[生成中] 正在运行既有规则作曲与配器。', flush=True)
                    except Exception as exc:
                        state_changed = state.external('generation_error') or state_changed
                        print(f'[生成失败] {exc}', flush=True)
            elif intent == 'cancel_recording' and compose is not None:
                compose.cancel_recording()
                compose.prepare()
                print('[录制已取消] 可重新开始。', flush=True)
            elif intent == 'preview_score':
                if composition is None:
                    state_changed = state.external('preview_error') or state_changed
                    print('[试听失败] 当前没有可试听的作品。', flush=True)
                else:
                    try:
                        preview = MidiPreview(composition.events, args.midi_device)
                        preview.start()
                        print('[试听中] 长按停止并返回主菜单。', flush=True)
                    except Exception as exc:
                        preview = None
                        state_changed = state.external('preview_error') or state_changed
                        print(f'[试听失败] {exc}', flush=True)
            elif intent == 'save_score':
                if composition is not None:
                    print(f'[已保存] {composition.out_dir}', flush=True)
            else:
                print(f'[预留动作] {intent}', flush=True)
        return state_changed

    print(f'桌面控制面板已连接 {args.encoder_port}。旋转选择，短按确认，长按返回。')
    print('指挥模式和两种规则作曲模式均已接入。Ctrl+C 退出。')
    print_state(state)
    try:
        while True:
            now = time.monotonic()
            if state.phase.value in ('compose_countdown', 'calibration_countdown'):
                remaining = max(1, math.ceil(state.deadline - now))
                countdown_key = (state.phase.value, remaining)
                if countdown_key != reported_countdown:
                    print(remaining, flush=True)
                    reported_countdown = countdown_key
            else:
                reported_countdown = None
            changed = state.tick(now)
            if compose is not None:
                recording_event = compose.poll_recording()
                if recording_event == 'recording_limit' and state.phase.value == 'compose_recording':
                    changed = state.external('recording_finished') or changed
                generation = compose.poll_generation()
                if generation is not None:
                    generation_event, payload = generation
                    if generation_event == 'generation_complete':
                        composition = payload
                        print(f'[作品就绪] 《{payload.score.get("title", "") }》 已保存至 {payload.out_dir}', flush=True)
                    else:
                        print(f'[生成失败] {payload}', flush=True)
                    changed = state.external(generation_event) or changed
            if calibration is not None:
                calibration_event = calibration.poll_segment()
                if calibration_event == 'recording_limit' and state.phase.value == 'calibration_recording':
                    outcome, error = calibration.finish_segment()
                    if error:
                        print(f'[校准数据不足] {error}', flush=True)
                        changed = state.external('calibration_failed') or changed
                    else:
                        changed = state.external('calibration_segment_finished') or changed
            if preview is not None:
                preview_event = preview.poll()
                if preview_event is not None:
                    event, detail = preview_event
                    if detail:
                        print(f'[试听错误] {detail}', flush=True)
                    preview = None
                    changed = state.external(event) or changed
            if session is not None:
                conductor_event=session.update()
                snapshot = session.snapshot()
                if 'layers' in snapshot:
                    labels = {'keyboard': '键盘', 'bass': '贝斯', 'guitar': '电吉他', 'drums': '鼓组'}
                    active = tuple(group for group, level in snapshot['layers'].items() if level >= 16)
                    if active != reported_stem_layers:
                        shown = '、'.join(labels[group] for group in active) if active else '静音'
                        print(f'[卡农分轨] 当前声部：{shown}', flush=True)
                        reported_stem_layers = active
                if conductor_event == 'wand_started' and state.phase.value == 'conduct_armed':
                    changed=state.external(conductor_event) or changed
                elif conductor_event == 'wand_paused' and state.phase.value == 'conduct_playing':
                    changed=state.external(conductor_event) or changed
                elif conductor_event in ('conductor_finished','conductor_error'):
                    changed=state.external(conductor_event) or changed
                    stop_session()
            for _ in range(20):
                event = reader.read()
                if event is None:
                    break
                if event.get('delta'):
                    changed = state.rotate(event['delta']) or changed
                elif event.get('press') == 'short':
                    changed = state.short_press(time.monotonic()) or changed
                elif event.get('press') == 'long':
                    changed = state.long_press() or changed
            if changed:
                print_state(state)
                if run_intents():
                    print_state(state)
            time.sleep(.01)
    except KeyboardInterrupt:
        print('\n桌面控制面板已退出。')
    finally:
        stop_session()
        stop_preview()
        stop_compose()
        stop_calibration()
        reader.close()


if __name__ == '__main__':
    main()
