#!/usr/bin/env python3
"""
Live chess on the Sense HAT 8x8 LED matrix.

Streams the featured game from Lichess TV and renders it on the panel.
Hue encodes side (amber = white, blue = black), brightness encodes piece value.

Usage:
    python3 chess_panel.py              # live stream
    python3 chess_panel.py capture.ndjson   # replay a saved capture

Joystick:
    left / right   change TV channel
    up / down      brightness
    middle         clear and quit
"""

import json
import sys
import time
import urllib.request

from sense_hat import SenseHat

# ---------------------------------------------------------------- settings

ROTATION = 180          # set so that pixel (0,0) is your top-left
BRIGHTNESS = 1.0        # global scale, adjusted by the joystick
FLASH_SECONDS = 0.35    # how long the last move stays highlighted

CHANNELS = ["", "bullet", "blitz", "rapid"]   # "" = whatever is featured
channel_index = 1

USER_AGENT = "sense-hat-chess-panel (student project)"

# Empty squares. Dark squares are fully off; light squares just barely glow.
LIGHT_SQUARE = (26, 26, 28)
DARK_SQUARE = (0, 0, 0)

# Brightness level per piece type. Eight distinguishable steps on this panel,
# so every piece gets its own. Raise the low end if pawns disappear for you.
PIECE_COLOURS = {
    # white side: warm, reds through yellows into white
    "P": (140, 100, 55),    # dim cream
    "N": (255, 100, 0),     # orange
    "B": (255, 215, 40),    # yellow
    "R": (230, 20, 20),     # red
    "Q": (255, 55, 140),    # magenta
    "K": (255, 175, 120),   # pale salmon
    # black side: cool, greens through blues into violet
    "p": (40, 55, 115),     # dim slate
    "n": (0, 190, 185),     # cyan
    "b": (30, 200, 85),     # green
    "r": (45, 55, 255),     # deep blue
    "q": (205, 195, 255),   # pale lavender
    "k": (190, 70, 255),    # violet
}


def piece_colour(ch):
    return PIECE_COLOURS[ch]
# Hue tints. Amber for white, blue for black. "Black" cannot be black on an
# emissive display, so it becomes a second hue instead.

FLASH_TO = (255, 255, 255)
FLASH_FROM = (70, 70, 60)

# ---------------------------------------------------------------- hardware

sense = SenseHat()
sense.set_rotation(ROTATION)
sense.low_light = False   # keep the full range; scale in code instead

restart_stream = False
should_quit = False


def scaled(rgb):
    return tuple(max(0, min(255, int(c * BRIGHTNESS))) for c in rgb)




# ---------------------------------------------------------------- chess

def expand_fen(fen):
    """Turn a FEN into a list of 64 characters, index 0 = a8, index 63 = h1."""
    board = []
    for rank in fen.split(" ")[0].split("/"):
        for ch in rank:
            if ch.isdigit():
                board.extend("." * int(ch))
            else:
                board.append(ch)
    # Guard against a malformed line rather than crashing the display.
    if len(board) != 64:
        return None
    return board


def square_index(name):
    """'e4' -> index into the 64-cell board list."""
    file_ = ord(name[0]) - ord("a")
    rank = int(name[1])
    return (8 - rank) * 8 + file_


def render(board, highlight=None):
    """Build the 64 pixel list and push it to the panel."""
    pixels = []
    for i, ch in enumerate(board):
        row, col = divmod(i, 8)
        if ch == ".":
            rgb = LIGHT_SQUARE if (row + col) % 2 == 0 else DARK_SQUARE
        else:
            rgb = piece_colour(ch)
        pixels.append(scaled(rgb))

    if highlight:
        frm, to = highlight
        if board[frm] == ".":
            pixels[frm] = scaled(FLASH_FROM)
        pixels[to] = scaled(FLASH_TO)

    sense.set_pixels(pixels)


def new_game_sweep():
    """Brief wipe so the start of a game reads as an event."""
    for col in range(8):
        pixels = sense.get_pixels()
        for row in range(8):
            pixels[row * 8 + col] = scaled((90, 90, 80))
        sense.set_pixels(pixels)
        time.sleep(0.03)


# ---------------------------------------------------------------- joystick

def on_left(event):
    global channel_index, restart_stream
    if event.action == "pressed":
        channel_index = (channel_index - 1) % len(CHANNELS)
        restart_stream = True


def on_right(event):
    global channel_index, restart_stream
    if event.action == "pressed":
        channel_index = (channel_index + 1) % len(CHANNELS)
        restart_stream = True


def on_up(event):
    global BRIGHTNESS
    if event.action == "pressed":
        BRIGHTNESS = min(1.0, BRIGHTNESS + 0.15)


def on_down(event):
    global BRIGHTNESS
    if event.action == "pressed":
        BRIGHTNESS = max(0.15, BRIGHTNESS - 0.15)


def on_middle(event):
    global should_quit, restart_stream
    if event.action == "pressed":
        should_quit = True
        restart_stream = True


sense.stick.direction_left = on_left
sense.stick.direction_right = on_right
sense.stick.direction_up = on_up
sense.stick.direction_down = on_down
sense.stick.direction_middle = on_middle


# ---------------------------------------------------------------- streaming

def feed_url():
    channel = CHANNELS[channel_index]
    if channel:
        return f"https://lichess.org/api/tv/{channel}/feed"
    return "https://lichess.org/api/tv/feed"


def open_stream():
    request = urllib.request.Request(feed_url(), headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=30)


def handle_event(data, state):
    """Process one decoded line from the feed. Returns the current board."""
    kind = data.get("t")
    payload = data.get("d", {})

    if kind == "featured":
        board = expand_fen(payload.get("fen", ""))
        if board:
            new_game_sweep()
            render(board)
            state["board"] = board

    elif kind == "fen":
        board = expand_fen(payload.get("fen", ""))
        if board:
            state["board"] = board
            render(board)

    return state


def run_live():
    global restart_stream
    state = {"board": None}
    while not should_quit:
        restart_stream = False
        try:
            with open_stream() as stream:
                for raw in stream:
                    if restart_stream:
                        break
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        state = handle_event(json.loads(line), state)
                    except (ValueError, KeyError, IndexError):
                        continue  # skip a bad line, keep the display alive
        except Exception as exc:
            print(f"stream error: {exc}", file=sys.stderr)
            if not should_quit:
                time.sleep(3)  # back off, then reconnect


def run_replay(path):
    """Replay a saved capture, for developing offline or demoing safely."""
    state = {"board": None}
    while not should_quit:
        with open(path) as handle:
            for line in handle:
                if should_quit:
                    return
                line = line.strip()
                if not line:
                    continue
                try:
                    state = handle_event(json.loads(line), state)
                except (ValueError, KeyError, IndexError):
                    continue
                time.sleep(0.8)


# ---------------------------------------------------------------- entry

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            run_replay(sys.argv[1])
        else:
            run_live()
    except KeyboardInterrupt:
        pass
    finally:
        sense.clear()
