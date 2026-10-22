#!/usr/bin/env python3
"""
Player Account for the project:
username: datavis,
password: test2026.

Follow a Lichess player's live game on the Sense HAT 8x8 LED matrix.

Watches the usernames in FOLLOW_USERS. When one of them starts a game, the
panel picks it up, shows every move, and goes back to waiting when it ends.
No Lichess account or token is needed on the Pi.

Usage:
    python3 followchess.py                 # wait for FOLLOW_USERS to play
    python3 followchess.py abcd1234        # follow one specific game id
    python3 followchess.py https://lichess.org/abcd1234/black   # or its URL

Joystick:
    left / right   switch which followed user is preferred
    up / down      brightness
    middle         clear and quit
"""

import json
import sys
import time
import urllib.parse
import urllib.request

from sense_hat import SenseHat

# ---------------------------------------------------------------- settings

FOLLOW_USERS = ["datavis"]   # Lichess usernames to watch, any number
user_index = 0               # which one wins if several are playing at once

ROTATION = 180          # set so that pixel (0,0) is your top-left
BRIGHTNESS = 0.6        # global scale, adjusted by the joystick

POLL_SECONDS = 5        # how often to ask "is anyone playing?" while idle
STREAM_TIMEOUT = 90     # a quiet game stream reconnects after this long
CATCHUP_GAP = 0.4       # stream lines closer together than this are history
END_HOLD_SECONDS = 6    # how long the final position stays up

USER_AGENT = "sense-hat-chess-panel (student project)"

# Empty squares. Dark squares are fully off; light squares just barely glow.
LIGHT_SQUARE = (26, 26, 28)
DARK_SQUARE = (0, 0, 0)

# Every piece gets its own hue, not just its own brightness -- two pieces
# that only differ by brightness wash into each other on this panel.
PIECE_COLOURS = {
    # white side: warm hues
    "P": (140, 100, 55),     # dim brown
    "N": (255, 100, 0),      # orange
    "B": (255, 215, 4),      # gold/yellow
    "R": (230, 20, 20),      # red
    "Q": (255, 175, 120),    # peach
    "K": (255, 55, 140),     # pink
    # black side: cool hues
    "p": (40, 55, 115),      # dim slate
    "n": (192, 209, 0),      # yellow-green
    "b": (30, 200, 85),      # green
    "r": (45, 55, 255),      # blue
    "q": (0, 228, 217),      # cyan
    "k": (190, 70, 255),     # purple
}

IDLE_DOT = (110, 110, 110)         # the corner blink while waiting for a game
WIN_FLASH_COLOUR = (255, 0, 0)   # on the losing king
DRAW_FLASH_COLOUR = (255, 255, 255)

# ---------------------------------------------------------------- hardware

sense = SenseHat()
sense.set_rotation(ROTATION)
sense.low_light = False   # keep the full range; scale in code instead

restart_stream = False
should_quit = False


def scaled(rgb):
    return tuple(max(0, min(255, int(c * BRIGHTNESS))) for c in rgb)


def piece_colour(ch):
    return PIECE_COLOURS[ch]


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


def render(board):
    """Build the 64 pixel list and push it to the panel."""
    pixels = []
    for i, ch in enumerate(board):
        row, col = divmod(i, 8)
        if ch == ".":
            rgb = LIGHT_SQUARE if (row + col) % 2 == 0 else DARK_SQUARE
        else:
            rgb = piece_colour(ch)
        pixels.append(scaled(rgb))
    sense.set_pixels(pixels)
    return pixels


def render_idle(dot_on):
    """Empty board with one blinking corner pixel: 'waiting for a game'."""
    pixels = [scaled(LIGHT_SQUARE if (i // 8 + i % 8) % 2 == 0 else DARK_SQUARE)
              for i in range(64)]
    if dot_on:
        pixels[63] = scaled(IDLE_DOT)
    sense.set_pixels(pixels)


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

MATE_FLASH_SECONDS = 1.2
MATE_FLASH_TOGGLES = 5


def _blink(pixels, indices, on_colour, toggles, seconds):
    """Toggle some squares between `on_colour` and their current colour."""
    live = list(pixels)
    originals = {i: live[i] for i in indices}
    step = seconds / (toggles * 2)
    for _ in range(toggles):
        for i in indices:
            live[i] = scaled(on_colour)
        sense.set_pixels(live)
        time.sleep(step)
        for i in indices:
            live[i] = originals[i]
        sense.set_pixels(live)
        time.sleep(step)
    return live


def flash_capture(pixels, index):
    """Quick off/on blink on the square a piece just landed on, to mark a capture."""
    _blink(pixels, [index], (0, 0, 0), CAPTURE_FLASH_TOGGLES, CAPTURE_FLASH_SECONDS)


def flash_check(pixels, king_index):
    """Quick white pulse on the checked king's square."""
    _blink(pixels, [king_index], CHECK_FLASH_COLOUR, CHECK_FLASH_TOGGLES, CHECK_FLASH_SECONDS)


def show_game_over(board, status, winner):
    """Mark how the game ended on the final position, then hold it."""
    pixels = render(board)
    if winner in ("white", "black"):
        # mate, resign, timeout...: red pulse on the loser's king,
        # slower and longer for an actual checkmate.
        loser = king_square(board, white=(winner == "black"))
        if loser is not None:
            if status == "mate":
                _blink(pixels, [loser], WIN_FLASH_COLOUR, MATE_FLASH_TOGGLES, MATE_FLASH_SECONDS)
            else:
                _blink(pixels, [loser], WIN_FLASH_COLOUR, 2, 1.0)
    elif status in ("draw", "stalemate"):
        kings = [i for i in (king_square(board, True), king_square(board, False)) if i is not None]
        _blink(pixels, kings, DRAW_FLASH_COLOUR, 3, 1.2)
    sense.set_pixels(pixels)
    wait(END_HOLD_SECONDS)


# ---------------------------------------------------------------- joystick

def on_left(event):
    global user_index, restart_stream
    if event.action == "pressed" and len(FOLLOW_USERS) > 1:
        user_index = (user_index - 1) % len(FOLLOW_USERS)
        restart_stream = True


def on_right(event):
    global user_index, restart_stream
    if event.action == "pressed" and len(FOLLOW_USERS) > 1:
        user_index = (user_index + 1) % len(FOLLOW_USERS)
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


# ---------------------------------------------------------------- lichess

def wait(seconds):
    """Sleep in small steps so the joystick still feels responsive."""
    end = time.monotonic() + seconds
    while time.monotonic() < end and not should_quit and not restart_stream:
        time.sleep(0.1)


def get_json(url, timeout=15):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                  "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def current_game(user_id):
    """The user's ongoing game id from /current-game, or None if it has ended."""
    try:
        game = get_json(f"https://lichess.org/api/user/{user_id}/current-game?moves=false")
    except Exception:
        return None   # e.g. 404 for a user with no games yet
    # This endpoint falls back to the last finished game, so check it's live.
    if game.get("status") in ("created", "started"):
        return game.get("id")
    return None


def find_live_game():
    """Return (username, game_id) for a followed user who is playing, or None."""
    ids = ",".join(FOLLOW_USERS)
    statuses = get_json(f"https://lichess.org/api/users/status?ids={ids}&withGameIds=true")
    playing = {s["id"]: s["playingId"] for s in statuses if s.get("playingId")}

    # Games against the computer (and no-clock games) don't count as "playing"
    # above, so for anyone online without a playingId, check their latest game.
    for s in statuses:
        if s.get("online") and s["id"] not in playing:
            game = current_game(s["id"])
            if game:
                playing[s["id"]] = game

    # Prefer the user picked with the joystick, then the rest in list order.
    order = FOLLOW_USERS[user_index:] + FOLLOW_USERS[:user_index]
    for name in order:
        if name.lower() in playing:
            return name, playing[name.lower()]
    return None


def game_id_from_arg(arg):
    """Accept 'abcd1234' or any lichess.org game URL; game ids are 8 characters."""
    path = urllib.parse.urlparse(arg).path if "://" in arg else arg
    return path.strip("/").split("/")[0][:8]


def handle_line(data, state, live):
    """Process one line of /api/stream/game. Returns True once the game is over."""
    status = data.get("status", {}).get("name")
    board = expand_fen(data["fen"]) if "fen" in data else None

    if board:
        old_board = state.get("board")
        move = parse_last_move(data.get("lm"))
        pixels = render(board)

        fields = data["fen"].split(" ")
        white_to_move = fields[1] == "w" if len(fields) > 1 else True

        # Replaying the game's history: draw it, but don't animate every move.
        if live and old_board and move and status is None:
            frm, to = move
            moved = old_board[frm]
            if old_board[to] != "." or (moved in ("P", "p") and frm % 8 != to % 8):
                flash_capture(pixels, to)  # includes en passant
            if king_in_check(board, white_to_move):
                king_index = king_square(board, white_to_move)
                if king_index is not None:
                    flash_check(pixels, king_index)

        state["board"] = board

    # Lichess status ids: 10 created, 20 started, 25+ finished in some way.
    if data.get("status", {}).get("id", 0) >= 25:
        if state.get("board") and status != "aborted":
            show_game_over(state["board"], status, data.get("winner"))
        return True
    return False


def follow_game(game_id):
    """Stream one game until it ends. Returns True if it finished normally."""
    global restart_stream
    state = {"board": None}
    new_game_sweep()
    while not should_quit and not restart_stream:
        url = f"https://lichess.org/api/stream/game/{game_id}"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=STREAM_TIMEOUT) as stream:
                # Every connect starts with the whole move history in one quick
                # burst. The first pause between lines marks the switch to live.
                live = False
                last = None
                for raw in stream:
                    if restart_stream or should_quit:
                        return False
                    now = time.monotonic()
                    if last is not None and now - last > CATCHUP_GAP:
                        live = True
                    last = now
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        if handle_line(json.loads(line), state, live):
                            return True
                    except (ValueError, KeyError, IndexError):
                        continue  # skip a bad line, keep the display alive
        except Exception as exc:
            # Includes the timeout during a long think; reconnecting is harmless.
            print(f"stream error: {exc}", file=sys.stderr)
            wait(3)
    return False


def run_follow():
    """Wait for a followed user to start a game, show it, repeat."""
    global restart_stream
    finished = set()   # status can still say "playing" for a moment after the end
    dot_on = False
    while not should_quit:
        restart_stream = False
        try:
            found = find_live_game()
        except Exception as exc:
            print(f"status error: {exc}", file=sys.stderr)
            found = None

        if found and found[1] not in finished:
            name, game_id = found
            print(f"following {name}: https://lichess.org/{game_id}")
            if follow_game(game_id):
                finished.add(game_id)
        else:
            dot_on = not dot_on
            render_idle(dot_on)
            wait(POLL_SECONDS)


def run_single(game_id):
    """Follow one given game, then hold the final position until quit."""
    global restart_stream
    print(f"following https://lichess.org/{game_id}")
    while not should_quit:
        restart_stream = False
        if follow_game(game_id):
            break
    while not should_quit:
        time.sleep(0.2)


# ---------------------------------------------------------------- entry

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            run_single(game_id_from_arg(sys.argv[1]))
        else:
            run_follow()
    except KeyboardInterrupt:
        pass
    finally:
        sense.clear()
