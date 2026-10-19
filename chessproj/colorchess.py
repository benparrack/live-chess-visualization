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
BRIGHTNESS = 0.6        # global scale, adjusted by the joystick
FLASH_SECONDS = 0.35    # how long the last move stays highlighted

CHANNELS = ["", "bullet", "blitz", "rapid"]   # "" = whatever is featured
channel_index = 1

USER_AGENT = "sense-hat-chess-panel (student project)"

# Empty squares. Dark squares are fully off; light squares just barely glow.
LIGHT_SQUARE = (26, 26, 28)
DARK_SQUARE = (0, 0, 0)

# Every piece gets its own hue, not just its own brightness -- two pieces
# that only differ by brightness wash into each other on this panel.
# Channel values are capped well under 255 so nothing blooms into white.
PIECE_COLOURS = {
    # white side: warm hues, each piece its own
    "P": (140, 100, 55),     # dim brown
    "N": (255, 100, 0),     # orange
    "B": (255, 215, 4),    # gold/yellow
    "R": (230, 20, 20),     # red
    "Q": (255, 175, 120),    # pink/magenta
    "K": (255, 55, 140),   # peach (pale, but clearly warm not pink)
    # black side: cool hues, each piece its own
    "p": (40, 55, 115),      # dim slate-teal (not blue, so it won't read as a dim rook)
    "n": (192, 209, 0),     # cyan
    "b": (30, 200, 85),      # green
    "r": (45, 55, 255),     # blue
    "q": (0, 228, 217),    # purple
    "k": (190, 70, 255),   # pale ice-blue (pale, but clearly cool not purple)
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
    return pixels


def parse_last_move(lm):
    """'e2e4' (or 'e7e8q' for a promotion) -> (from_index, to_index)."""
    if not lm or len(lm) < 4:
        return None
    try:
        return square_index(lm[0:2]), square_index(lm[2:4])
    except (IndexError, ValueError):
        return None


def king_square(board, white):
    king = "K" if white else "k"
    return board.index(king) if king in board else None


def square_attacked(board, idx, by_white):
    """Is `idx` attacked by any piece of the `by_white` side?"""
    row, col = divmod(idx, 8)

    def at(r, c):
        if 0 <= r < 8 and 0 <= c < 8:
            return board[r * 8 + c]
        return None

    pawn_row = row + 1 if by_white else row - 1
    for dc in (-1, 1):
        if at(pawn_row, col + dc) == ("P" if by_white else "p"):
            return True

    knight = "N" if by_white else "n"
    for dr, dc in ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)):
        if at(row + dr, col + dc) == knight:
            return True

    king = "K" if by_white else "k"
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if (dr or dc) and at(row + dr, col + dc) == king:
                return True

    bishop = "B" if by_white else "b"
    rook = "R" if by_white else "r"
    queen = "Q" if by_white else "q"

    for dr, dc in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        r, c = row + dr, col + dc
        while 0 <= r < 8 and 0 <= c < 8:
            ch = at(r, c)
            if ch is not None and ch != ".":
                if ch in (bishop, queen):
                    return True
                break
            r += dr
            c += dc

    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        r, c = row + dr, col + dc
        while 0 <= r < 8 and 0 <= c < 8:
            ch = at(r, c)
            if ch is not None and ch != ".":
                if ch in (rook, queen):
                    return True
                break
            r += dr
            c += dc

    return False


def king_in_check(board, white):
    idx = king_square(board, white)
    if idx is None:
        return False
    return square_attacked(board, idx, not white)


def new_game_sweep():
    """Brief wipe so the start of a game reads as an event."""
    for col in range(8):
        pixels = sense.get_pixels()
        for row in range(8):
            pixels[row * 8 + col] = scaled((90, 90, 80))
        sense.set_pixels(pixels)
        time.sleep(0.03)


# ---------------------------------------------------------------- animations

CAPTURE_FLASH_SECONDS = 0.5
CAPTURE_FLASH_TOGGLES = 4

CHECK_FLASH_COLOUR = (255, 255, 255)
CHECK_FLASH_SECONDS = 0.6
CHECK_FLASH_TOGGLES = 3

CHECKMATE_FLASH_COLOUR = (255, 0, 0)
CHECKMATE_FLASH_SECONDS = 1.2
CHECKMATE_FLASH_TOGGLES = 5
CHECKMATE_HOLD_SECONDS = 6   # how long the final, checkmated board stays up


def _blink(pixels, index, on_colour, toggles, seconds):
    """Toggle one square between `on_colour` and its current colour."""
    live = list(pixels)
    original = live[index]
    step = seconds / (toggles * 2)
    for _ in range(toggles):
        live[index] = scaled(on_colour)
        sense.set_pixels(live)
        time.sleep(step)
        live[index] = original
        sense.set_pixels(live)
        time.sleep(step)
    return live


def flash_capture(pixels, index):
    """Quick off/on blink on the square a piece just landed on, to mark a capture."""
    _blink(pixels, index, (0, 0, 0), CAPTURE_FLASH_TOGGLES, CAPTURE_FLASH_SECONDS)


def flash_check(pixels, king_index):
    """Quick white pulse on the checked king's square."""
    _blink(pixels, king_index, CHECK_FLASH_COLOUR, CHECK_FLASH_TOGGLES, CHECK_FLASH_SECONDS)


def flash_checkmate(pixels, king_index):
    """Slower red pulse on the mated king's square, then hold the final position."""
    live = _blink(pixels, king_index, CHECKMATE_FLASH_COLOUR, CHECKMATE_FLASH_TOGGLES, CHECKMATE_FLASH_SECONDS)
    sense.set_pixels(live)
    time.sleep(CHECKMATE_HOLD_SECONDS)


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
            prev_board = state.get("board")
            # The feed jumps straight to the next game on any game end. If the
            # side to move was in check on the last board we saw, that's checkmate
            # (nothing else in a live TV game leaves the position in check) -- so
            # hold on that final position instead of sweeping it away immediately.
            if prev_board is not None and state.get("in_check"):
                king_index = king_square(prev_board, state.get("white_to_move", True))
                if king_index is not None:
                    flash_checkmate(render(prev_board), king_index)

            new_game_sweep()
            render(board)
            state["board"] = board
            state["in_check"] = False

    elif kind == "fen":
        fen = payload.get("fen", "")
        board = expand_fen(fen)
        if board:
            old_board = state.get("board")
            move = parse_last_move(payload.get("lm"))

            captured = False
            if old_board and move:
                frm, to = move
                moved = old_board[frm]
                if old_board[to] != ".":
                    captured = True
                elif moved in ("P", "p") and frm % 8 != to % 8:
                    captured = True  # en passant: destination looked empty

            pixels = render(board)

            if captured and move:
                flash_capture(pixels, move[1])

            fields = fen.split(" ")
            white_to_move = fields[1] == "w" if len(fields) > 1 else True
            in_check = king_in_check(board, white_to_move)
            if in_check:
                king_index = king_square(board, white_to_move)
                if king_index is not None:
                    flash_check(pixels, king_index)

            state["board"] = board
            state["in_check"] = in_check
            state["white_to_move"] = white_to_move

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
