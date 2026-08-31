import pygame.midi
import time

pygame.midi.init()

player = pygame.midi.Output(1)

# GM 标准里 channel 10 是鼓组
# pygame 从 0 开始编号，所以这里 channel=9

pattern = [
    36,  # Kick
    42,  # Closed Hi-hat
    38,  # Snare
    42   # Closed Hi-hat
]

for note in pattern:
    player.note_on(note, 110, channel=9)
    time.sleep(0.4)
    player.note_off(note, 110, channel=9)

player.close()
pygame.midi.quit()