import pygame.midi
import time

pygame.midi.init()

player = pygame.midi.Output(1)  # GS Wavetable Synth

player.set_instrument(0)  # 0 = Acoustic Grand Piano

notes = [60, 64, 67]  # C4 E4 G4

for note in notes:
    player.note_on(note, 100)

time.sleep(2)

for note in notes:
    player.note_off(note, 100)

player.close()
pygame.midi.quit()