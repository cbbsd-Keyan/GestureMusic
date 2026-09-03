import json
import time
import argparse

from midi_engine import MidiEngine


CHORDS = {
    "C":  [60, 64, 67],
    "Dm": [62, 65, 69],
    "Em": [64, 67, 71],
    "F":  [65, 69, 72],
    "G":  [67, 71, 74],
    "Am": [69, 72, 76],
    "E":  [64, 68, 71],
}


def load_score(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_events(score):
    bpm = score["bpm"]

    # 一个十六分音符持续多少秒
    grid_sec = 60.0 / bpm / 4.0

    events = []

    # -------------------------
    # 旋律
    # -------------------------
    for item in score.get("melody", []):
        bar = item["bar"]
        start = item["start"]
        dur = item["dur"]
        note = item["note"]
        velocity = item.get("velocity", 90)

        start_time = (bar * 16 + start) * grid_sec
        end_time = start_time + dur * grid_sec

        events.append(
            (start_time, "melody_on", note, velocity)
        )

        events.append(
            (end_time, "melody_off", note, 0)
        )

    # -------------------------
    # 和弦
    # -------------------------
    chords = score.get("chords", [])

    for i, item in enumerate(chords):
        bar = item["bar"]
        symbol = item["symbol"]

        notes = CHORDS.get(symbol)

        if notes is None:
            print(f"[警告] 暂不支持和弦: {symbol}")
            continue

        start_time = bar * 16 * grid_sec

        if i + 1 < len(chords):
            next_bar = chords[i + 1]["bar"]
        else:
            next_bar = score["bars"]

        end_time = next_bar * 16 * grid_sec

        events.append(
            (start_time, "chord_on", notes, 60)
        )

        events.append(
            (end_time, "chord_off", notes, 0)
        )

    events.sort(key=lambda x: x[0])

    return events


def play_score(score, device_id):
    engine = MidiEngine(device_id)

    events = build_events(score)

    print(
        f"[播放] {score['bars']}小节 | "
        f"{score['bpm']} BPM | "
        f"{len(score.get('melody', []))}个旋律音"
    )

    start_clock = time.perf_counter()

    try:
        for event_time, event_type, data, velocity in events:

            while True:
                now = time.perf_counter() - start_clock

                wait = event_time - now

                if wait <= 0:
                    break

                time.sleep(min(wait, 0.01))

            if event_type == "melody_on":
                engine.play_melody(
                    data,
                    velocity
                )

            elif event_type == "melody_off":
                engine.stop_melody(
                    data
                )

            elif event_type == "chord_on":
                engine.play_chord(
                    data,
                    velocity
                )

            elif event_type == "chord_off":
                engine.stop_chord(
                    data
                )

    finally:
        engine.close()

    print("[播放完成]")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "score",
        help="乐谱 JSON 文件"
    )

    parser.add_argument(
        "--device",
        type=int,
        required=True,
        help="MIDI 输出设备 ID"
    )

    args = parser.parse_args()

    score = load_score(args.score)

    play_score(
        score,
        args.device
    )


if __name__ == "__main__":
    main()