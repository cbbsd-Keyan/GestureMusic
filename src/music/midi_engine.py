import pygame.midi


class MidiEngine:
    def __init__(self, device_id=1):

        pygame.midi.init()

        self.player = pygame.midi.Output(device_id)

        self.CHORD_CHANNEL = 0
        self.BASS_CHANNEL = 1
        self.MELODY_CHANNEL = 2
        self.DRUM_CHANNEL = 9

        # Piano
        self.player.set_instrument(
            0,
            self.CHORD_CHANNEL
        )

        # Bass
        self.player.set_instrument(
            32,
            self.BASS_CHANNEL
        )

        # Piano melody
        self.player.set_instrument(
            0,
            self.MELODY_CHANNEL
        )

    def note_on(self, note, velocity, channel):
        self.player.note_on(
            note,
            velocity,
            channel
        )

    def note_off(self, note, velocity, channel):
        self.player.note_off(
            note,
            velocity,
            channel
        )

    def play_chord(self, notes, velocity=60):
        for note in notes:
            self.note_on(
                note,
                velocity,
                self.CHORD_CHANNEL
            )

    def stop_chord(self, notes):
        for note in notes:
            self.note_off(
                note,
                0,
                self.CHORD_CHANNEL
            )

    def play_bass(self, note, velocity=75):
        self.note_on(
            note,
            velocity,
            self.BASS_CHANNEL
        )

    def stop_bass(self, note):
        self.note_off(
            note,
            0,
            self.BASS_CHANNEL
        )

    def play_melody(self, note, velocity=90):
        self.note_on(
            note,
            velocity,
            self.MELODY_CHANNEL
        )

    def stop_melody(self, note):
        self.note_off(
            note,
            0,
            self.MELODY_CHANNEL
        )

    def play_drum(self, note, velocity=105):
        self.note_on(
            note,
            velocity,
            self.DRUM_CHANNEL
        )

        self.note_off(
            note,
            0,
            self.DRUM_CHANNEL
        )

    def close(self):
        self.player.close()
        pygame.midi.quit()