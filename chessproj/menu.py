#!/usr/bin/env python3
"""
Run every panel mode from one program and flip between them with the joystick.

Modes, in order:
    colorchess    the featured Lichess TV game
    followchess   our own live game (FOLLOW_USERS in followchess.py)

Clicking the stick in opens the Bluetooth speaker screen: it searches, lists
the speakers it found (one at a time, scrolling), and connects the one picked.

Usage:
    python3 menu.py

Joystick:
    left / right   previous / next mode
    up / down      brightness
    middle click   Bluetooth speakers (up / down to scroll, click to connect)
    middle hold    clear and quit (2s)
"""

import queue
import sys
import time

import bluetooth_speakers
import colorchess
import followchess
import panel
import sound

MODES = [colorchess.run_live, followchess.run_follow]
mode_index = 0
switching = False

QUIT_HOLD_SECONDS = 2
SCAN_SECONDS = 12
SPEAKER_VOLUME = 40     # percent, set on the speaker once it's connected

want_bluetooth = False
in_bluetooth = False    # while the speaker screen is up, it gets every press
stick_events = queue.Queue()
pressed_at = None       # when the middle button went down, until handled


# ---------------------------------------------------------------- joystick

def switch(step):
    global mode_index, switching
    mode_index = (mode_index + step) % len(MODES)
    switching = True
    # should_quit is what makes every loop in a mode return; run() clears it again
    panel.should_quit = True
    panel.restart_stream = True


def open_bluetooth():
    global want_bluetooth, switching
    want_bluetooth = True
    switching = True
    panel.should_quit = True
    panel.restart_stream = True


def on_left(event):
    if event.action == "pressed":
        switch(-1)


def on_right(event):
    if event.action == "pressed":
        switch(1)


def on_middle(event):
    # A click opens Bluetooth on release, so a long hold can mean quit instead.
    global pressed_at, switching
    if event.action == "pressed":
        pressed_at = time.monotonic()
    elif pressed_at is None:
        return   # this press was already handled (or began on the speaker screen)
    elif event.action == "held" and time.monotonic() - pressed_at >= QUIT_HOLD_SECONDS:
        pressed_at = None
        switching = False   # quitting wins over a mode switch still in progress
        panel.should_quit = True
        panel.restart_stream = True
    elif event.action == "released":
        pressed_at = None
        open_bluetooth()


def routed(handler):
    def handle(event):
        if in_bluetooth:
            stick_events.put(event)
        else:
            handler(event)
    return handle


# set after the imports above, which install their own handlers
panel.sense.stick.direction_left = routed(on_left)
panel.sense.stick.direction_right = routed(on_right)
panel.sense.stick.direction_up = routed(panel.on_up)
panel.sense.stick.direction_down = routed(panel.on_down)
panel.sense.stick.direction_middle = routed(on_middle)


# ---------------------------------------------------------------- bluetooth

class Screen:
    """Stands in for the SenseHat that bluetooth_speakers.pick expects: draws
    on the panel at its brightness and reads the presses queued above."""

    def __init__(self):
        self.stick = self

    def get_events(self):
        events = []
        while not stick_events.empty():
            events.append(stick_events.get())
        return events

    def set_pixels(self, pixels):
        panel.sense.set_pixels([panel.scaled(p) for p in pixels])


def message(text, colour, seconds=4):
    panel.clear()
    bluetooth_speakers.pick(Screen(), [text], colour=colour, timeout=seconds)


def run_bluetooth():
    """Search, let the joystick pick a speaker, connect it, then go back."""
    global in_bluetooth
    in_bluetooth = True
    bluetooth = None
    try:
        bluetooth = bluetooth_speakers.Bluetooth()
        while True:
            print("Searching for Bluetooth speakers...", flush=True)
            panel.show_status("searching")   # animates while the scan blocks
            speakers = bluetooth.scan(SCAN_SECONDS)
            panel.clear()
            labels = bluetooth_speakers.speaker_labels(speakers) + ["RESCAN", "BACK"]
            choice = bluetooth_speakers.pick(Screen(), labels)
            if choice == len(speakers):
                continue
            if choice == len(speakers) + 1:
                return
            speaker = speakers[choice]
            panel.show_status("connecting")
            try:
                bluetooth.connect(speaker["address"])
                bluetooth_speakers.select_audio(speaker["address"], SPEAKER_VOLUME)
            except Exception as exc:
                print(f"Bluetooth connect failed: {exc}", file=sys.stderr, flush=True)
                message("ERROR", (180, 0, 0))
                continue   # search again
            print(f"Connected {speaker['name']} {speaker['address']}", flush=True)
            sound.play("start")   # first sound through the new speaker
            message("CONNECTED " + speaker["name"], (0, 160, 0))
            return
    except Exception as exc:
        # e.g. no adapter, Bluetooth off, or python3-dbus missing (the simulator)
        print(f"Bluetooth error: {exc}", file=sys.stderr, flush=True)
        message("NO BLUETOOTH", (180, 0, 0))
    finally:
        in_bluetooth = False
        if bluetooth:
            bluetooth.close()
        panel.clear()


# ---------------------------------------------------------------- entry

def run():
    global switching, want_bluetooth
    while True:
        if want_bluetooth:
            want_bluetooth = False
            run_bluetooth()   # then back to the mode it interrupted
        else:
            MODES[mode_index]()
            if not switching:
                return   # held middle button, not a mode switch
        switching = False
        panel.should_quit = False
        panel.restart_stream = False


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
    finally:
        panel.clear()
