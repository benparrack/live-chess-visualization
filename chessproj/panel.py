"""
Shared pieces of the Sense HAT chess panel: colours, board drawing, chess
helpers, animations, connection-status screens and the common joystick keys.

colorchess.py (Lichess TV) and followchess.py (follow a player) both build on
this. Each sets its own left/right joystick handlers; up/down/middle live here.
"""

import math
import queue
import socket
import threading
import time
import urllib.request

from sense_hat import SenseHat

import sound

# ---------------------------------------------------------------- settings

ROTATION = 180          # set so that pixel (0,0) is your top-left
BRIGHTNESS = 0.6        # global scale, adjusted by the joystick
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

OFF = (0, 0, 0)
FLASH_TO = (255, 255, 255)        # a landing piece starts white and settles
CHECK_COLOUR = (255, 255, 255)
LOSS_COLOUR = (255, 0, 0)         # on the losing king
DRAW_COLOUR = (255, 255, 255)

# Connection status, shown whenever there is no board to draw. Each one also
# has its own shape, so they can be told apart without relying on colour.
CONNECTING_COLOUR = (0, 90, 255)  # blue ring with a comet: reaching Lichess
WAITING_COLOUR = (0, 200, 60)     # green ring, breathing centre: online, no game
OFFLINE_COLOUR = (255, 0, 0)      # red X: the last request failed

# ---------------------------------------------------------------- hardware

sense = SenseHat()
sense.set_rotation(ROTATION)
sense.low_light = False   # keep the full range; scale in code instead

restart_stream = False
should_quit = False
last_status = None   # status screen showing now; None while a board is up
draw_lock = threading.Lock()   # the status animation thread vs. everything else drawing


def scaled(rgb):
    return tuple(max(0, min(255, int(c * BRIGHTNESS))) for c in rgb)


def mix(a, b, t):
    """Blend colour a toward b; t=0 is a, t=1 is b."""
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


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


def white_to_move(fen):
    fields = fen.split(" ")
    return fields[1] == "w" if len(fields) > 1 else True


def square_index(name):
    """'e4' -> index into the 64-cell board list."""
    file_ = ord(name[0]) - ord("a")
    rank = int(name[1])
    return (8 - rank) * 8 + file_


def parse_last_move(lm):
    """'e2e4' (or 'e7e8q' for a promotion) -> (from_index, to_index)."""
    if not lm or len(lm) < 4:
        return None
    try:
        return square_index(lm[0:2]), square_index(lm[2:4])
    except (IndexError, ValueError):
        return None


def captured_piece(old_board, move):
    """The piece taken by `move`, or None. Handles en passant."""
    frm, to = move
    moved = old_board[frm]
    if old_board[to] != "." and old_board[to].isupper() != moved.isupper():
        return old_board[to]   # same colour = castling written king-takes-rook
    if moved in ("P", "p") and frm % 8 != to % 8:
        return "p" if moved == "P" else "P"   # en passant: destination looked empty
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


def path_between(frm, to):
    """Squares strictly between frm and to along a line (none for a knight jump)."""
    fr, fc = divmod(frm, 8)
    tr, tc = divmod(to, 8)
    dr, dc = tr - fr, tc - fc
    if dr and dc and abs(dr) != abs(dc):
        return []
    sr, sc = (dr > 0) - (dr < 0), (dc > 0) - (dc < 0)
    return [(fr + sr * k) * 8 + fc + sc * k for k in range(1, max(abs(dr), abs(dc)))]


# ---------------------------------------------------------------- drawing

def board_pixels(board):
    global last_status
    with draw_lock:
        last_status = None   # stops the status animation before a board is drawn
    pixels = []
    for i, ch in enumerate(board):
        row, col = divmod(i, 8)
        if ch == ".":
            rgb = LIGHT_SQUARE if (row + col) % 2 == 0 else DARK_SQUARE
        else:
            rgb = PIECE_COLOURS[ch]
        pixels.append(scaled(rgb))
    return pixels


def render(board):
    """Build the 64 pixel list and push it to the panel."""
    pixels = board_pixels(board)
    sense.set_pixels(pixels)
    return pixels


# ---------------------------------------------------------------- animations

MOVE_STEP_SECONDS = 0.035   # per square of a sliding move, and per landing frame
CAPTURE_SECONDS = 0.45
CHECK_SECONDS = 0.7
CHECK_PULSES = 2


def crossfade(start, end, seconds, steps=8):
    for k in range(1, steps + 1):
        sense.set_pixels([mix(a, b, k / steps) for a, b in zip(start, end)])
        time.sleep(seconds / steps)


def pulse(pixels, indices, colour, pulses, seconds):
    """Smoothly swell some squares to `colour` and back, `pulses` times."""
    steps = 10
    target = scaled(colour)
    for k in range(pulses * steps):
        t = (1 - math.cos(2 * math.pi * k / steps)) / 2
        frame = list(pixels)
        for i in indices:
            frame[i] = mix(pixels[i], target, t)
        sense.set_pixels(frame)
        time.sleep(seconds / (pulses * steps))
    sense.set_pixels(pixels)


def slide(old_pixels, new_pixels, frm, to):
    """Run the moved piece along its path, then land it with a flash that settles."""
    colour = new_pixels[to]
    for sq in path_between(frm, to):
        frame = list(new_pixels)
        frame[to] = old_pixels[to]   # the target stays visible until it's hit
        frame[sq] = colour
        sense.set_pixels(frame)
        time.sleep(MOVE_STEP_SECONDS)
    for t in (0.0, 0.35, 0.7, 1.0):
        frame = list(new_pixels)
        frame[to] = mix(scaled(FLASH_TO), colour, t)
        sense.set_pixels(frame)
        time.sleep(MOVE_STEP_SECONDS)


def shatter(pixels, index, captured):
    """The captured piece's colour bursts onto the neighbouring squares and fades."""
    row, col = divmod(index, 8)
    ring = [(row + dr) * 8 + col + dc
            for dr in (-1, 0, 1) for dc in (-1, 0, 1)
            if (dr or dc) and 0 <= row + dr < 8 and 0 <= col + dc < 8]
    colour = scaled(PIECE_COLOURS[captured])
    steps = 6
    for k in range(steps + 1):
        frame = list(pixels)
        for i in ring:
            frame[i] = mix(colour, pixels[i], 0.2 + 0.8 * k / steps)
        sense.set_pixels(frame)
        time.sleep(CAPTURE_SECONDS / steps)


def show_move(old_board, board, move, white_next):
    """Animate one live move: slide, capture burst, check pulse. Returns in_check."""
    frm, to = move
    old_pixels = board_pixels(old_board)
    pixels = board_pixels(board)
    captured = captured_piece(old_board, move)
    in_check = king_in_check(board, white_next)

    moved = old_board[frm]
    if in_check:
        sound.play("check")
    elif moved in ("P", "p") and board[to] not in ("P", "p"):
        sound.play("promote")
    elif captured:
        sound.play("capture")
    elif moved in ("K", "k") and abs(frm % 8 - to % 8) > 1:
        sound.play("castle")
    else:
        sound.play("move")

    slide(old_pixels, pixels, frm, to)
    if captured:
        shatter(pixels, to, captured)
    if in_check:
        pulse(pixels, [king_square(board, white_next)], CHECK_COLOUR, CHECK_PULSES, CHECK_SECONDS)
    sense.set_pixels(pixels)
    return in_check


def new_game_reveal(board):
    """Fade to black, then deal the ranks in from both edges toward the middle."""
    target = board_pixels(board)
    sound.play("start")
    crossfade([tuple(p) for p in sense.get_pixels()], [OFF] * 64, 0.25)
    frame = [OFF] * 64
    for ring in range(4):
        for row in (ring, 7 - ring):
            frame[row * 8:row * 8 + 8] = target[row * 8:row * 8 + 8]
        sense.set_pixels(frame)
        time.sleep(0.09)


def show_game_over(board, status, winner):
    """Mark how the game ended on the final position, then hold it."""
    pixels = render(board)
    if winner in ("white", "black"):
        sound.play("mate" if status == "mate" else "win")
        loser_white = winner == "black"
        loser = king_square(board, loser_white)
        if loser is not None:
            # slower and longer for an actual checkmate than a resign/timeout
            pulses, seconds = (4, 1.6) if status == "mate" else (2, 1.0)
            pulse(pixels, [loser], LOSS_COLOUR, pulses, seconds)
        # The losing army dims so the winning side stands out; its king stays red.
        final = list(pixels)
        for i, ch in enumerate(board):
            if ch != "." and ch.isupper() == loser_white:
                final[i] = mix(pixels[i], OFF, 0.75)
        if loser is not None:
            final[loser] = scaled(LOSS_COLOUR)
        crossfade(pixels, final, 0.6)
    elif status in ("draw", "stalemate"):
        sound.play("draw")
        kings = [i for i in (king_square(board, True), king_square(board, False)) if i is not None]
        pulse(pixels, kings, DRAW_COLOUR, 3, 1.2)
    wait(END_HOLD_SECONDS)


# ---------------------------------------------------------------- status screens

STATUS_STEP = 0.1
# The 28 edge squares, clockwise from the top-left corner.
BORDER = (list(range(8)) + [r * 8 + 7 for r in range(1, 8)]
          + list(range(62, 55, -1)) + [r * 8 for r in range(6, 0, -1)])
CENTRE = (27, 28, 35, 36)
CROSS = [r * 8 + c for r in range(8) for c in range(8) if r == c or r + c == 7]


def status_frame(kind, step):
    """One frame of a status screen. Never blank, so it can't look switched off."""
    pixels = [OFF] * 64

    def lit(colour, level):
        return scaled(tuple(c * level for c in colour))

    if kind == "connecting":
        for k, i in enumerate(BORDER):
            behind = (step - k) % len(BORDER)
            pixels[i] = lit(CONNECTING_COLOUR, max(0.2, 1 - behind * 0.25))
    elif kind == "waiting":
        for i in BORDER:
            pixels[i] = lit(WAITING_COLOUR, 0.25)
        breath = (1 - math.cos(2 * math.pi * step / 25)) / 2
        for i in CENTRE:
            pixels[i] = lit(WAITING_COLOUR, 0.15 + 0.85 * breath)
    elif kind == "offline":
        level = 1.0 if step % 10 < 5 else 0.25
        for i in CROSS:
            pixels[i] = lit(OFFLINE_COLOUR, level)
    return pixels


def draw_status():
    # the step comes from the clock so animations stay smooth across calls
    sense.set_pixels(status_frame(last_status, int(time.monotonic() / STATUS_STEP)))


def show_status(kind):
    """Put up a status screen; it keeps animating until a board is drawn."""
    global last_status
    if kind == "offline" and last_status != "offline":
        sound.play("offline")   # once when the connection drops, not every retry
    with draw_lock:
        last_status = kind
        draw_status()


def animate_status():
    # Runs on its own thread, so the screen keeps moving while the main
    # thread is stuck in a network call.
    while True:
        time.sleep(STATUS_STEP)
        with draw_lock:
            if last_status:
                draw_status()


def wait(seconds, status=None):
    """Sleep in small steps so the joystick stays responsive, showing `status`."""
    if status:
        show_status(status)
    end = time.monotonic() + seconds
    while time.monotonic() < end and not should_quit and not restart_stream:
        time.sleep(STATUS_STEP)


def clear():
    """Blank the panel for good, stopping any status animation first."""
    global last_status
    with draw_lock:
        last_status = None
        sense.clear()


# ---------------------------------------------------------------- streams

def background(fn, *args):
    """Run a blocking call (a web request) on a helper thread and wait for it in
    STATUS_STEP slices, so a joystick press isn't held up behind it. Returns its
    result, or None if the joystick asked to switch or quit first; raises its errors."""
    result = queue.Queue()

    def run():
        try:
            result.put((fn(*args), None))
        except Exception as exc:
            result.put((None, exc))

    threading.Thread(target=run, daemon=True).start()
    while not (should_quit or restart_stream):
        try:
            value, error = result.get(timeout=STATUS_STEP)
        except queue.Empty:
            continue
        if error:
            raise error
        return value
    return None


def read_lines(request, timeout):
    """Open a Lichess stream and yield (arrival_time, line) from it. Connecting
    and reading both happen off the main thread so the joystick never waits on
    the network: while nothing arrives this yields (now, None) every STATUS_STEP.
    Ends when the stream closes or the joystick interrupts the connect; raises
    connection and read errors (including the read timeout)."""
    stream = background(lambda: urllib.request.urlopen(request, timeout=timeout))
    if stream is None:
        return
    lines = queue.Queue()

    def reader():
        try:
            for raw in stream:
                lines.put((time.monotonic(), raw))   # timestamped before any slow animation
            lines.put((time.monotonic(), None))
        except Exception as exc:
            lines.put((time.monotonic(), exc))
        finally:
            stream.close()

    threading.Thread(target=reader, daemon=True).start()
    try:
        while True:
            try:
                arrived, raw = lines.get(timeout=STATUS_STEP)
            except queue.Empty:
                yield time.monotonic(), None
                continue
            if raw is None:
                return
            if isinstance(raw, Exception):
                raise raw
            yield arrived, raw
    finally:
        # Closing the stream from here would wait for the reader's blocked read
        # to finish; shutting the socket down ends that read now instead, and
        # the reader then closes the stream.
        # shortcut: reaches into urllib's private socket; without it the stream
        # still closes, just at its next line or timeout.
        try:
            stream.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        except (AttributeError, OSError):
            pass


# ---------------------------------------------------------------- joystick

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


sense.stick.direction_up = on_up
sense.stick.direction_down = on_down
sense.stick.direction_middle = on_middle

threading.Thread(target=animate_status, daemon=True).start()
