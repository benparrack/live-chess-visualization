import time
from panel import expand_fen, render, sense

render(expand_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"))
time.sleep(20)
sense.clear()
