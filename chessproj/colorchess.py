#!/usr/bin/env python3
"""
Live chess on the Sense HAT 8x8 LED matrix.

Streams the featured game from Lichess TV and renders it on the panel.
Every piece has its own hue: warm for white, cool for black (see panel.py).

Usage:
    python3 colorchess.py                  # live stream
    python3 colorchess.py capture.ndjson   # replay a saved capture

Joystick:
    left / right   change TV channel
    up / down      brightness
    middle         clear and quit
"""

import json
import sys
import time
import urllib.request

import panel

# ---------------------------------------------------------------- settings

CHANNELS = ["", "bullet", "blitz", "rapid"]   # "" = whatever is featured
channel_index = 1


# ---------------------------------------------------------------- joystick

def on_left(event):
    global channel_index
    if event.action == "pressed":
        channel_index = (channel_index - 1) % len(CHANNELS)
        panel.restart_stream = True


def on_right(event):
    global channel_index
    if event.action == "pressed":
        channel_index = (channel_index + 1) % len(CHANNELS)
        panel.restart_stream = True


panel.sense.stick.direction_left = on_left
panel.sense.stick.direction_right = on_right


# ---------------------------------------------------------------- streaming

def feed_url():
    channel = CHANNELS[channel_index]
    if channel:
        return f"https://lichess.org/api/tv/{channel}/feed"
    return "https://lichess.org/api/tv/feed"


def open_stream():
    request = urllib.request.Request(feed_url(), headers={"User-Agent": panel.USER_AGENT})
    return urllib.request.urlopen(request, timeout=30)


def handle_event(data, state):
    """Process one decoded line from the feed. Returns the updated state."""
    kind = data.get("t")
    payload = data.get("d", {})

    if kind == "featured":
        board = panel.expand_fen(payload.get("fen", ""))
        if board:
            prev_board = state.get("board")
            # The feed jumps straight to the next game on any game end. If the
            # side to move was in check on the last board we saw, that's checkmate
            # (nothing else in a live TV game leaves the position in check) -- so
            # hold on that final position instead of sweeping it away immediately.
            if prev_board is not None and state.get("in_check"):
                winner = "black" if state.get("white_to_move", True) else "white"
                panel.show_game_over(prev_board, "mate", winner)

            panel.new_game_reveal(board)
            state["board"] = board
            state["in_check"] = False

    elif kind == "fen":
        fen = payload.get("fen", "")
        board = panel.expand_fen(fen)
        if board:
            old_board = state.get("board")
            move = panel.parse_last_move(payload.get("lm"))
            white_next = panel.white_to_move(fen)

            if old_board and move and old_board != board:
                in_check = panel.show_move(old_board, board, move, white_next)
            else:
                panel.render(board)
                in_check = panel.king_in_check(board, white_next)

            state["board"] = board
            state["in_check"] = in_check
            state["white_to_move"] = white_next

    return state


def run_live():
    while not panel.should_quit:
        panel.restart_stream = False
        # Fresh state per connection, so a reconnect or channel switch
        # can't be mistaken for the end of a game in check.
        state = {"board": None}
        panel.show_status("connecting")
        try:
            with open_stream() as stream:
                for raw in stream:
                    if panel.restart_stream:
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
            panel.wait(3, "offline")  # back off, then reconnect


def run_replay(path):
    """Replay a saved capture, for developing offline or demoing safely."""
    state = {"board": None}
    while not panel.should_quit:
        with open(path) as handle:
            for line in handle:
                if panel.should_quit:
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
        panel.sense.clear()
