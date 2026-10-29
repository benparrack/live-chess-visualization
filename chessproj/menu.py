#!/usr/bin/env python3
"""
Run every panel mode from one program and flip between them with the joystick.

Modes, in order:
    colorchess    the featured Lichess TV game
    followchess   our own live game (FOLLOW_USERS in followchess.py)

Usage:
    python3 menu.py

Joystick:
    left / right   previous / next mode
    up / down      brightness
    middle         clear and quit
"""

import colorchess
import followchess
import panel

MODES = [colorchess.run_live, followchess.run_follow]
mode_index = 0
switching = False


# ---------------------------------------------------------------- joystick

def switch(step):
    global mode_index, switching
    mode_index = (mode_index + step) % len(MODES)
    switching = True
    # should_quit is what makes every loop in a mode return; run() clears it again
    panel.should_quit = True
    panel.restart_stream = True


def on_left(event):
    if event.action == "pressed":
        switch(-1)


def on_right(event):
    if event.action == "pressed":
        switch(1)


def on_middle(event):
    global switching
    if event.action == "pressed":
        switching = False   # quitting wins over a mode switch still in progress
    panel.on_middle(event)


# set after the imports above, which install their own left/right handlers
panel.sense.stick.direction_left = on_left
panel.sense.stick.direction_right = on_right
panel.sense.stick.direction_middle = on_middle


# ---------------------------------------------------------------- entry

def run():
    global switching
    while True:
        MODES[mode_index]()
        if not switching:
            return   # the middle button, not a mode switch
        switching = False
        panel.should_quit = False


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
    finally:
        panel.clear()
