import time
from colorchess import PIECE_COLOURS, sense, scaled

order = "PNBRQK"
pixels = [(0, 0, 0)] * 64
for i, ch in enumerate(order):
    pixels[8 + i + 1] = scaled(PIECE_COLOURS[ch])
    pixels[40 + i + 1] = scaled(PIECE_COLOURS[ch.lower()])
sense.set_pixels(pixels)
time.sleep(30)
sense.clear()
