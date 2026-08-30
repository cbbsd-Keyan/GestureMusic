import pygame.midi

pygame.midi.init()

for i in range(pygame.midi.get_count()):
    info = pygame.midi.get_device_info(i)
    print(i, info)

pygame.midi.quit()