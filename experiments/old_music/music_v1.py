import pygame.midi
import msvcrt

pygame.midi.init()

player = pygame.midi.Output(1)

CHORD_CHANNEL = 0
BASS_CHANNEL = 1
DRUM_CHANNEL = 9

player.set_instrument(0, CHORD_CHANNEL)     # Piano
player.set_instrument(32, BASS_CHANNEL)    # Bass

chords = [
    [60, 64, 67],  # C
    [57, 60, 64],  # Am
    [53, 57, 60],  # F
    [55, 59, 62],  # G
]

chord_names = ["C", "Am", "F", "G"]
bass_notes = [36, 33, 29, 31]

beat = 0
current_chord = None
current_bass = None

print("按空格 = 一拍")
print("按 Q = 退出")

while True:
    key = msvcrt.getwch()

    if key.lower() == "q":
        break

    if key != " ":
        continue

    chord_index = (beat // 4) % 4
    beat_in_bar = beat % 4

    # 每4拍换和弦
    if beat_in_bar == 0:

        if current_chord is not None:
            for note in current_chord:
                player.note_off(note, 65, CHORD_CHANNEL)

        if current_bass is not None:
            player.note_off(current_bass, 80, BASS_CHANNEL)

        current_chord = chords[chord_index]
        current_bass = bass_notes[chord_index]

        for note in current_chord:
            player.note_on(note, 65, CHORD_CHANNEL)

        player.note_on(current_bass, 80, BASS_CHANNEL)

    # 鼓
    drum_pattern = [36, 42, 38, 42]
    drum_note = drum_pattern[beat_in_bar]

    player.note_on(drum_note, 105, DRUM_CHANNEL)
    player.note_off(drum_note, 105, DRUM_CHANNEL)

    print(
        f"Beat {beat + 1} | "
        f"Chord {chord_names[chord_index]}"
    )

    beat += 1

# 停掉还在响的声音
if current_chord:
    for note in current_chord:
        player.note_off(note, 65, CHORD_CHANNEL)

if current_bass:
    player.note_off(current_bass, 80, BASS_CHANNEL)

player.close()
pygame.midi.quit()