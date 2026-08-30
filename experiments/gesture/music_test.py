import numpy as np
import sounddevice as sd
import time

SAMPLE_RATE = 44100

NOTE_FREQ = {
    "C4": 261.63,
    "D4": 293.66,
    "E4": 329.63,
    "G4": 392.00,
    "A4": 440.00,
}


def play_note(note, duration=0.30, volume=0.3):
    freq = NOTE_FREQ[note]

    t = np.linspace(
        0,
        duration,
        int(SAMPLE_RATE * duration),
        endpoint=False
    )

    wave = volume * np.sin(2 * np.pi * freq * t)

    sd.play(wave, SAMPLE_RATE)
    sd.wait()


for note in ["C4", "D4", "E4", "G4", "A4"]:
    print("Playing:", note)
    play_note(note)
    time.sleep(0.1)