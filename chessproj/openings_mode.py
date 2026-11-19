#!/usr/bin/env python3
"""
Openings and famous games as a menu.py mode: no laptop or web page needed.

Plays every opening and famous game from openings_server.py one after another.
The name scrolls across first, then the moves play with the same colours and
animations as the live Lichess modes (panel.py).

Joystick, while this mode is showing:
    up / down      next / previous opening (instead of brightness)
    left / right   switch mode, as usual (handled by menu.py)

Run on its own for testing:
    python3 openings_mode.py
"""

import chess

import panel
from openings_server import OPENINGS, board_chars, idx

MOVE_SECONDS = 1.2        # pause between moves
NOTE_SECONDS = 0.8        # extra pause on moves that have a note
END_SECONDS = 3           # hold the final position before the next line
NAME_COLOUR = (255, 184, 71)

IDS = list(OPENINGS)      # openings first, then famous games
index = 0
jump = 0                  # set by the joystick: +1 next, -1 previous


def jump_to(step):
    global jump
    jump = step
    panel.restart_stream = True   # makes panel.wait() return straight away


def on_up(event):
    if event.action == "pressed":
        jump_to(1)


def on_down(event):
    if event.action == "pressed":
        jump_to(-1)


def interrupted():
    return panel.should_quit or panel.restart_stream


def play_line(op):
    """Scroll the name, then play the moves. Returns early if interrupted."""
    print(f"[{index + 1}/{len(IDS)}] {op['name']}", flush=True)
    panel.sense.show_message(op["name"], scroll_speed=0.04,
                             text_colour=panel.scaled(NAME_COLOUR))
    if interrupted():
        return

    game = chess.Board()
    prev = board_chars(game)
    panel.new_game_reveal(prev)
    panel.wait(MOVE_SECONDS)

    for i, move in enumerate(op["moves"]):
        if interrupted():
            return
        game.push(move)
        board = board_chars(game)
        panel.show_move(prev, board, (idx(move.from_square), idx(move.to_square)),
                        game.turn == chess.WHITE)
        prev = board
        panel.wait(MOVE_SECONDS + (NOTE_SECONDS if op["notes"][i] else 0))

    if game.is_checkmate():
        winner = "black" if game.turn == chess.WHITE else "white"
        panel.show_game_over(board, "mate", winner)
    else:
        panel.wait(END_SECONDS)


def run_openings():
    """menu.py mode: loops until panel.should_quit is set (a mode switch or quit)."""
    global index, jump
    while not panel.should_quit:
        jump = 0
        panel.restart_stream = False
        play_line(OPENINGS[IDS[index]])
        if panel.should_quit:
            return
        index = (index + (jump or 1)) % len(IDS)


if __name__ == "__main__":
    panel.sense.stick.direction_up = on_up
    panel.sense.stick.direction_down = on_down
    try:
        run_openings()
    except KeyboardInterrupt:
        pass
    finally:
        panel.sense.clear()
