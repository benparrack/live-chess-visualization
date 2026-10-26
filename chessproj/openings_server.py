#!/usr/bin/env python3
"""
Opening explorer: a web page of opening buttons that plays the chosen line
on the Sense HAT 8x8 LED matrix, with a description and move-by-move notes.

    python3 openings_server.py
    then open  http://ryanpi.local:8000  on a phone or laptop on the same Wi-Fi

Needs: sense_hat and python-chess   (pip install chess --break-system-packages)
Colours match lichess.py: amber = white pieces, blue = black pieces,
brightness = piece value, white flash = the square a piece just moved to.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import chess
from sense_hat import SenseHat

# ---------------------------------------------------------------- settings

PORT = 8000
ROTATION = 180            # same as lichess.py; change if the board looks flipped
BRIGHTNESS = 1.0
FLASH_SECONDS = 0.35
DEFAULT_DELAY = 1.2       # seconds between moves (the page slider overrides this)

LIGHT_SQUARE = (45, 38, 22)
DARK_SQUARE = (0, 0, 0)
VALUE = {"p": 95, "n": 135, "b": 135, "r": 175, "q": 255, "k": 210}
WHITE_TINT = (1.00, 0.72, 0.28)
BLACK_TINT = (0.35, 0.65, 1.00)
FLASH_TO = (255, 255, 255)
FLASH_FROM = (70, 70, 60)

# ---------------------------------------------------------------- openings
#
# To add one, copy a block and change it:
#   moves  normal chess notation, pasted from Lichess / Wikipedia is fine
#   about  a short description shown under the board
#   notes  optional comments on single moves: "3.Bc4" is White's 3rd move,
#          "3...Bc5" is Black's 3rd move
# A typo stops the server at startup and tells you exactly what's wrong.

OPENING_LINES = [
    {
        "id": "italian", "name": "Italian Game", "group": "1.e4",
        "moves": "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6 O-O O-O Re1 a6 Bb3 Ba7 h3 h6 Nbd2 Re8",
        "about": "One of the oldest openings. White develops quickly and points the bishop at f7, "
                 "the weakest square near Black's king. This slow version with c3 and d3 "
                 "(the 'Giuoco Pianissimo') is a favourite of top players: both sides castle "
                 "and manoeuvre before committing to a plan.",
        "notes": {
            "2.Nf3": "Attacks the e5 pawn while developing.",
            "2...Nc6": "Defends e5 and develops.",
            "3.Bc4": "The Italian bishop, aimed straight at f7.",
            "3...Bc5": "Black mirrors White and aims at f2.",
            "4.c3": "Prepares d4 to grab the centre later.",
            "5.d3": "The quiet approach: a solid centre and no early fight.",
            "7...a6": "Makes room for the bishop to drop back to a7 without being traded.",
            "9.h3": "Stops ...Bg4, which would pin the knight.",
            "10.Nbd2": "The knight is heading for f1 and g3, a typical Italian route.",
        },
    },
    {
        "id": "ruy", "name": "Ruy Lopez", "group": "1.e4",
        "moves": "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Na5 Bc2 c5 d4 Qc7",
        "about": "Named after a 16th-century Spanish priest, the Ruy Lopez is one of the most "
                 "deeply studied openings in chess. White pressures the knight that defends e5 "
                 "and builds slow, lasting pressure. This is the Closed Ruy Lopez, Chigorin Variation.",
        "notes": {
            "3.Bb5": "Attacks the knight that defends e5.",
            "3...a6": "The Morphy Defence: asks the bishop to decide right away.",
            "5.O-O": "White castles. Taking on e4 is possible but leads to the sharp Open Ruy Lopez.",
            "6.Re1": "Now e4 is defended, and White threatens Bxc6 followed by Nxe5.",
            "6...b5": "Kicks the bishop and gains space on the queenside.",
            "8.c3": "Prepares d4 and gives the bishop a retreat square on c2.",
            "9.h3": "Stops ...Bg4, which would pin the knight and weaken d4.",
            "9...Na5": "The Chigorin plan: chase the strong bishop, then play ...c5.",
            "11.d4": "White finally claims the centre with pawns.",
        },
    },
    {
        "id": "kingsgambit", "name": "King's Gambit", "group": "1.e4",
        "moves": "e4 e5 f4 exf4 Nf3 g5 h4 g4 Ne5 Nf6 d4 d6 Nd3 Nxe4 Bxf4 Bg7 c3 Qe7 Qe2 Bf5",
        "about": "A romantic 19th-century favourite. White gives up a pawn to rip open the f-file "
                 "and build a big centre, hoping for a fast attack. Black can grab material but "
                 "has to survive the storm. This line is the Kieseritzky Gambit.",
        "notes": {
            "2.f4": "The gambit: offers a pawn to pull Black's e-pawn away from the centre.",
            "2...exf4": "Black accepts the pawn.",
            "3...g5": "Holds on to the extra pawn on f4.",
            "4.h4": "Undermines the g5 pawn that protects f4.",
            "5.Ne5": "The Kieseritzky: the knight jumps to a strong central square.",
            "7...Nxe4": "Black grabs a second pawn.",
            "8.Bxf4": "White wins a pawn back and gets the bishop into the game.",
        },
    },
    {
        "id": "friedliver", "name": "Fried Liver Attack", "group": "1.e4",
        "moves": "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7 Kxf7 Qf3+ Ke6 Nc3 Ncb4 a3 Nxc2+ Kd1 Nxa1 Nxd5 Qh4",
        "about": "A wild attacking line from the Two Knights Defence. White sacrifices a knight on "
                 "f7 to drag Black's king into the middle of the board. It's dangerous and fun, "
                 "but Black can sidestep it completely with 5...Na5 instead of 5...Nxd5.",
        "notes": {
            "3...Nf6": "The Two Knights Defence: counterattacks e4.",
            "4.Ng5": "Teams up with the bishop against f7.",
            "4...d5": "Blocks the bishop's diagonal.",
            "5...Nxd5": "The natural recapture, but it walks into the Fried Liver.",
            "6.Nxf7": "The sacrifice! The knight forks queen and rook, so the king has to take.",
            "7.Qf3+": "Checks the king and attacks the knight on d5.",
            "7...Ke6": "The king steps forward to defend d5. It's now in the centre of the board.",
            "8...Ncb4": "Defends d5 again and eyes c2.",
            "9...Nxc2+": "Black counterattacks, forking king and rook.",
            "11.Nxd5": "White gives up the rook and piles onto d5 while Black's king is still exposed.",
        },
    },
    {
        "id": "scholars", "name": "Scholar's Mate", "group": "1.e4",
        "moves": "e4 e5 Bc4 Nc6 Qh5 Nf6 Qxf7#",
        "about": "Not a real opening but the most famous beginner trap. The queen and bishop both "
                 "aim at f7, which only Black's king defends. Easy to stop with ...g6 or ...Qe7 "
                 "once you know it.",
        "notes": {
            "3.Qh5": "Threatens Qxf7 checkmate, and also attacks e5.",
            "3...Nf6": "A natural-looking blunder: it attacks the queen but ignores f7.",
            "4.Qxf7#": "Checkmate. The bishop on c4 protects the queen, so the king can't take it.",
        },
    },
    {
        "id": "najdorf", "name": "Sicilian Najdorf", "group": "1.e4",
        "moves": "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Be3 e5 Nb3 Be6 f3 Be7 Qd2 O-O O-O-O Nbd7 g4 b5",
        "about": "The Sicilian is Black's sharpest reply to 1.e4, and the Najdorf is its most famous "
                 "form, played by Fischer and Kasparov. Black trades a side pawn for a centre pawn "
                 "and plays for the win. In this English Attack, the players castle on opposite "
                 "sides and race to attack each other's kings.",
        "notes": {
            "1...c5": "The Sicilian: fights for d4 without mirroring White.",
            "3...cxd4": "Black trades a side pawn for a centre pawn.",
            "5...a6": "The Najdorf move: keeps White's pieces off b5 and prepares ...b5.",
            "6.Be3": "The English Attack begins: Be3, f3, Qd2, castle queenside, then g4.",
            "6...e5": "Kicks the knight and grabs space in the centre.",
            "10.O-O-O": "Opposite-side castling: now it's a race.",
            "11.g4": "White's pawns storm toward Black's king.",
            "11...b5": "Black's pawn storm on the other wing.",
        },
    },
    {
        "id": "french", "name": "French Defense", "group": "1.e4",
        "moves": "e4 e6 d4 d5 Nc3 Nf6 Bg5 Be7 e5 Nfd7 Bxe7 Qxe7 f4 O-O Nf3 c5 Qd2 Nc6 O-O-O c4",
        "about": "A solid counterpunching defence. Black lets White build a big pawn centre, then "
                 "attacks its base with ...c5 and ...f6. The downside is Black's light-squared "
                 "bishop, which gets stuck behind the e6 pawn.",
        "notes": {
            "1...e6": "Prepares ...d5 to challenge e4.",
            "2...d5": "Hits the e4 pawn straight away.",
            "4.Bg5": "Pins the knight that attacks e4.",
            "5.e5": "Gains space and kicks the knight.",
            "7.f4": "Supports e5, the spearhead of White's centre.",
            "8...c5": "The typical French strike at White's pawn chain.",
            "10.O-O-O": "Opposite-side castling: both sides will attack.",
            "10...c4": "Black gains space and gets ready to storm the queenside.",
        },
    },
    {
        "id": "caro", "name": "Caro-Kann", "group": "1.e4",
        "moves": "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 h4 h6 Nf3 Nd7 h5 Bh7 Bd3 Bxd3 Qxd3 e6 Bd2 Ngf6 O-O-O Be7",
        "about": "A rock-solid defence. Like the French, Black challenges e4 with ...d5, but plays "
                 "...c6 first so the light-squared bishop can get out before ...e6. Black aims for "
                 "a sound position with no weaknesses.",
        "notes": {
            "1...c6": "Prepares ...d5 while keeping the bishop's diagonal open.",
            "3...dxe4": "Black gives up the centre in exchange for easy development.",
            "4...Bf5": "The Classical: the bishop gets out before ...e6 shuts it in.",
            "5.Ng3": "Kicks the bishop with tempo.",
            "6.h4": "Threatens h5, which would trap the bishop.",
            "8.h5": "Grabs space and makes Black's kingside harder to use.",
            "9.Bd3": "Offers a trade of light-squared bishops.",
        },
    },
    {
        "id": "scandi", "name": "Scandinavian", "group": "1.e4",
        "moves": "e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6 Nf3 c6 Bc4 Bf5 Bd2 e6 Nd5 Qd8 Nxf6+ Qxf6 Qe2 Nd7",
        "about": "Black hits e4 on move one and recaptures with the queen. The queen gets chased "
                 "around a little, but Black ends up with a simple, solid position and easy "
                 "development, much like a Caro-Kann.",
        "notes": {
            "1...d5": "Attacks e4 immediately.",
            "2...Qxd5": "The queen recaptures early, accepting that it'll be chased.",
            "3.Nc3": "Develops while attacking the queen.",
            "3...Qa5": "The queen steps aside and will pin the c3 knight against the king.",
            "5...c6": "Gives the queen a retreat on c7 and controls d5.",
            "6...Bf5": "The light-squared bishop gets out before ...e6.",
            "7.Bd2": "Breaks the pin, so the c3 knight is free to move.",
            "8.Nd5": "Discovered attack: the knight jumps away and the d2 bishop now hits the queen.",
        },
    },
    {
        "id": "qgd", "name": "Queen's Gambit Declined", "group": "1.d4",
        "moves": "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 Nbd7 Rc1 c6 Bd3 dxc4 Bxc4 Nd5 Bxe7 Qxe7 O-O Nxc3 Rxc3 e5",
        "about": "One of the most classical openings. White offers the c-pawn to pull Black's "
                 "d-pawn away from the centre. Black declines with ...e6 and keeps a strong point "
                 "on d5. This is the Orthodox Defence, finished with Capablanca's freeing manoeuvre.",
        "notes": {
            "2.c4": "The gambit: offers a pawn to pull Black's d-pawn away from the centre.",
            "2...e6": "Declines, keeping d5 solidly defended.",
            "4.Bg5": "Pins the knight that guards d5.",
            "7.Rc1": "The rook lines up on the c-file, which will open later.",
            "8...dxc4": "Black finally takes, timed so White's bishop has to move twice.",
            "9...Nd5": "Capablanca's idea: trade pieces to free Black's cramped position.",
            "12...e5": "The freeing pawn break Black was playing for.",
        },
    },
    {
        "id": "qga", "name": "Queen's Gambit Accepted", "group": "1.d4",
        "moves": "d4 d5 c4 dxc4 Nf3 Nf6 e3 e6 Bxc4 c5 O-O a6 dxc5 Qxd1 Rxd1 Bxc5 Kf1 b5 Be2 Bb7",
        "about": "White offers the c-pawn and Black takes it. Black isn't trying to keep the pawn: "
                 "the point is to let White take the centre, then hit back with ...c5. White wins "
                 "the pawn back easily and the game turns calm and positional.",
        "notes": {
            "2...dxc4": "Black accepts the pawn, but won't try to keep it.",
            "4.e3": "Opens the bishop's diagonal to win c4 back.",
            "5.Bxc4": "White regains the pawn.",
            "5...c5": "Black's key strike at the centre.",
            "7.dxc5": "Trading queens leads to a calm, roughly equal endgame.",
            "9.Kf1": "With the queens gone, the king heads for the centre, where it's useful.",
        },
    },
    {
        "id": "kid", "name": "King's Indian", "group": "1.d4",
        "moves": "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5 O-O Nc6 d5 Ne7 Ne1 Nd7 Nd3 f5 Bd2 Nf6 f3 f4",
        "about": "A fighting, hypermodern defence and Kasparov's favourite. Black lets White build "
                 "a huge centre, tucks the king behind the bishop on g7, then counterattacks. In "
                 "this Mar del Plata line, White attacks on the queenside while Black throws "
                 "everything at White's king.",
        "notes": {
            "2...g6": "Prepares to put the bishop on g7.",
            "4.e4": "White takes a big pawn centre, and Black lets it happen.",
            "6...e5": "Black finally strikes at the centre.",
            "8.d5": "Locks the centre. Now each side attacks on its own wing.",
            "9.Ne1": "The knight reroutes to d3 to support a queenside attack with c5.",
            "10...f5": "Black's key pawn break toward White's king.",
            "12...f4": "Black gains space and gets ready to push ...g5 and ...g4.",
        },
    },
    {
        "id": "london", "name": "London System", "group": "1.d4",
        "moves": "d4 d5 Bf4 Nf6 e3 e6 Nf3 c5 c3 Nc6 Nbd2 Bd6 Bg3 O-O Bd3 b6 Ne5 Bb7 f4 Ne7",
        "about": "A system rather than a sharp opening: White plays the same set-up against almost "
                 "anything. The bishop goes to f4 before e3 so it isn't locked in, then White "
                 "builds a solid pyramid of pawns. Easy to learn and very popular at club level.",
        "notes": {
            "2.Bf4": "The London bishop, developed before e3 shuts it in.",
            "3.e3": "Starts the solid pawn chain on c3, d4 and e3.",
            "5.c3": "Completes the pawn pyramid supporting d4.",
            "6...Bd6": "Black challenges White's bishop.",
            "7.Bg3": "Keeps the bishop. If Black trades, hxg3 opens the h-file for White's rook.",
            "9.Ne5": "The knight jumps to a strong outpost.",
            "10.f4": "Supports the knight and prepares a kingside attack.",
        },
    },
    {
        "id": "english", "name": "English Opening", "group": "Other",
        "moves": "c4 e5 Nc3 Nf6 Nf3 Nc6 g3 d5 cxd5 Nxd5 Bg2 Nb6 O-O Be7 d3 O-O a3 Be6 b4 f6",
        "about": "White starts on the side with 1.c4, controlling d5 without committing in the "
                 "centre. Against 1...e5 it's a Sicilian with colours reversed, so White has a "
                 "whole extra move. The bishop on g2 rakes the long diagonal.",
        "notes": {
            "1.c4": "Controls d5 from the side.",
            "1...e5": "Black takes the centre: a reversed Sicilian.",
            "4...d5": "Black grabs the centre with pawns.",
            "6.Bg2": "The bishop on g2 pressures the long diagonal toward b7 and c6.",
            "10.b4": "White grabs space on the queenside.",
            "10...f6": "Shores up e5 so the c6 knight is free to move.",
        },
    },
]

# ---------------------------------------------------------------- board logic

SKIP = {"...", "1-0", "0-1", "1/2-1/2", "*"}


def parse_line(name, text):
    """'1. e4 e5 2. Nf3 ...' -> (list of chess.Move, list of SAN strings)."""
    board = chess.Board()
    moves, san = [], []
    for token in text.replace(".", ". ").split():
        if token.rstrip(".").isdigit() or token in SKIP:
            continue
        try:
            move = board.parse_san(token)
        except ValueError:
            played = " ".join(san) or "(start)"
            raise SystemExit(f"{name}: '{token}' isn't a legal move after: {played}")
        san.append(board.san(move))
        moves.append(move)
        board.push(move)
    return moves, san


def note_ply(name, key, moves, san):
    """'3.Bc4' -> 4 (0-based ply index), checking the move matches."""
    number, sep, move = key.partition("...")
    if not sep:
        number, sep, move = key.partition(".")
    try:
        ply = (int(number) - 1) * 2 + (1 if sep == "..." else 0)
    except ValueError:
        raise SystemExit(f"{name}: can't read note key '{key}' (use '3.Bc4' or '3...Bc5')")
    if ply >= len(san):
        raise SystemExit(f"{name}: note '{key}' is past the end of the line")
    board = chess.Board()
    for m in moves[:ply]:
        board.push(m)
    try:
        same = board.parse_san(move.strip()) == moves[ply]   # accepts Ncb4 or Nb4, with/without +
    except ValueError:
        same = False
    if not same:
        actual = f"{number}{sep}{san[ply]}"
        raise SystemExit(f"{name}: note '{key}' doesn't match the move played there ({actual})")
    return ply


OPENINGS = {}
for _o in OPENING_LINES:
    _moves, _san = parse_line(_o["name"], _o["moves"])
    _notes = [""] * len(_san)
    for _key, _text in _o.get("notes", {}).items():
        _notes[note_ply(_o["name"], _key, _moves, _san)] = _text
    OPENINGS[_o["id"]] = {"id": _o["id"], "name": _o["name"], "group": _o["group"],
                          "about": _o.get("about", ""), "moves": _moves,
                          "san": _san, "notes": _notes}


def idx(square):
    """python-chess square (a1 = 0) -> panel index (a8 = 0)."""
    return (7 - chess.square_rank(square)) * 8 + chess.square_file(square)


def board_chars(board):
    """chess.Board -> list of 64 chars, index 0 = a8, '.' = empty."""
    out = ["."] * 64
    for square, piece in board.piece_map().items():
        out[idx(square)] = piece.symbol()
    return out


START = board_chars(chess.Board())

# ---------------------------------------------------------------- LEDs

sense = SenseHat()
sense.set_rotation(ROTATION)
sense.low_light = False


def scaled(rgb):
    return tuple(max(0, min(255, int(c * BRIGHTNESS))) for c in rgb)


def piece_colour(ch):
    tint = WHITE_TINT if ch.isupper() else BLACK_TINT
    v = VALUE[ch.lower()]
    return (v * tint[0], v * tint[1], v * tint[2])


def render(board, highlight=None):
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


# ---------------------------------------------------------------- player

lock = threading.Lock()
job = 0                        # bumped on every new request to cancel the old one
state = {"opening": None, "ply": 0, "total": 0, "playing": False,
         "board": "".join(START), "last": None}


def set_state(**kw):
    with lock:
        state.update(kw)


def wait(seconds, my_job):
    """Sleep, but return False early if a newer request has taken over."""
    end = time.time() + seconds
    while time.time() < end:
        if job != my_job:
            return False
        time.sleep(0.03)
    return job == my_job


def play(opening_id, delay, my_job):
    op = OPENINGS[opening_id]
    set_state(opening=opening_id, ply=0, total=len(op["moves"]), playing=True,
              board="".join(START), last=None)
    render(START)
    if not wait(delay, my_job):
        return
    game = chess.Board()
    for i, move in enumerate(op["moves"]):
        game.push(move)
        board = board_chars(game)
        f, t = idx(move.from_square), idx(move.to_square)
        set_state(ply=i + 1, board="".join(board), last=[f, t])
        render(board, (f, t))
        if not wait(FLASH_SECONDS, my_job):
            return
        render(board)
        # linger a bit longer on moves that have a note, so there's time to read it
        pause = delay * (1.8 if op["notes"][i] else 1.0)
        if not wait(max(0.0, pause - FLASH_SECONDS), my_job):
            return
    set_state(playing=False)


def start_job(target, *args):
    global job
    with lock:
        job += 1
        my_job = job
    if target:
        threading.Thread(target=target, args=(*args, my_job), daemon=True).start()


# ---------------------------------------------------------------- web

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the terminal quiet

    def send(self, body, ctype="application/json", code=200):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self.send(PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/openings":
            public = [{k: v for k, v in o.items() if k != "moves"} for o in OPENINGS.values()]
            self.send(json.dumps(public))
        elif self.path == "/api/state":
            with lock:
                self.send(json.dumps(state))
        else:
            self.send('{"error":"not found"}', code=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}

        if self.path == "/api/play" and body.get("id") in OPENINGS:
            delay = min(5.0, max(0.4, float(body.get("delay", DEFAULT_DELAY))))
            start_job(play, body["id"], delay)
            self.send('{"ok":true}')
        elif self.path == "/api/stop":
            start_job(None)
            set_state(playing=False)
            self.send('{"ok":true}')
        elif self.path == "/api/clear":
            start_job(None)
            sense.clear()
            set_state(opening=None, ply=0, total=0, playing=False,
                      board="." * 64, last=None)
            self.send('{"ok":true}')
        else:
            self.send('{"error":"bad request"}', code=400)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pi Openings</title>
<style>
  :root { --bg:#14161a; --card:#1e2127; --line:#2c3038; --text:#e8e6e1; --muted:#9097a3;
          --white:#ffb847; --black:#5aa6ff; --accent:#f0c674; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:15px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; }
  main { max-width:1000px; margin:0 auto; padding:20px 16px 40px;
         display:grid; gap:24px; grid-template-columns:1fr 340px; }
  @media (max-width:780px) { main { grid-template-columns:1fr; } aside { order:-1; position:static; } }
  h1 { font-size:22px; margin:0 0 4px; }
  .sub { color:var(--muted); margin:0 0 18px; }
  h2 { font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted);
       margin:18px 0 8px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:8px; }
  button { font:inherit; color:inherit; cursor:pointer; border-radius:10px; }
  .op { background:var(--card); border:1px solid var(--line); padding:12px; text-align:left; }
  .op:hover { border-color:#4a505c; }
  .op.active { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent) inset; }
  .op b { display:block; font-weight:600; }
  .op span { color:var(--muted); font-size:12px; }
  aside { position:sticky; top:16px; align-self:start; }
  .board { display:grid; grid-template-columns:repeat(8,1fr); aspect-ratio:1;
           border-radius:10px; overflow:hidden; border:1px solid var(--line); }
  .sq { display:flex; align-items:center; justify-content:center; font-size:min(7vw,30px); }
  .sq.l { background:#3a3326; } .sq.d { background:#0c0c0c; }
  .sq.from { background:#46463c; } .sq.to { outline:2px solid #fff; outline-offset:-2px; }
  .w { color:var(--white); } .k { color:var(--black); }
  .now { margin:12px 0 6px; font-weight:600; min-height:1.4em; }
  .moves { color:var(--muted); font-size:14px; min-height:1.4em; }
  .moves span { border-radius:4px; padding:0 2px; }
  .moves .has-note { border-bottom:1px dotted var(--muted); cursor:pointer; }
  .moves .cur { color:var(--text); background:#3a3f4a; }
  .note { margin-top:10px; padding:10px 12px; border-left:3px solid var(--accent);
          background:var(--card); border-radius:0 8px 8px 0; font-size:14px; min-height:2.6em; }
  .note:empty { display:none; }
  .note b { color:var(--accent); font-weight:600; margin-right:4px; }
  .about { color:var(--muted); font-size:14px; margin-top:12px; }
  .about:empty { display:none; }
  .controls { display:flex; gap:8px; margin-top:14px; }
  .controls button { flex:1; background:var(--card); border:1px solid var(--line); padding:9px; }
  label { display:block; margin-top:14px; color:var(--muted); font-size:13px; }
  input[type=range] { width:100%; accent-color:var(--accent); }
  .err { color:#ff7b72; font-size:13px; min-height:1.2em; margin-top:8px; }
</style>
</head>
<body>
<main>
  <section>
    <h1>Pi Openings</h1>
    <p class="sub">Tap an opening to play it on the Sense HAT.</p>
    <div id="groups"></div>
  </section>
  <aside>
    <div class="board" id="board"></div>
    <div class="now" id="now">Nothing playing</div>
    <div class="moves" id="moves"></div>
    <div class="note" id="note"></div>
    <div class="about" id="about"></div>
    <label>Speed: <span id="dval"></span> s per move
      <input type="range" id="delay" min="0.4" max="3" step="0.1" value="1.2"></label>
    <div class="controls">
      <button id="replay">Replay</button>
      <button id="stop">Stop</button>
      <button id="clear">Clear LEDs</button>
    </div>
    <div class="err" id="err"></div>
  </aside>
</main>
<script>
const GLYPH = {k:"♚",q:"♛",r:"♜",b:"♝",n:"♞",p:"♟"};
let openings = {}, current = null, lastPly = -1, pinned = null;
const $ = id => document.getElementById(id);
const delay = $("delay");
const showDelay = () => $("dval").textContent = (+delay.value).toFixed(1);
delay.oninput = showDelay; showDelay();

async function post(path, body) {
  try {
    const r = await fetch(path, {method:"POST", body: JSON.stringify(body || {})});
    if (!r.ok) throw new Error(r.status);
    $("err").textContent = "";
  } catch (e) { $("err").textContent = "Couldn't reach the Pi."; }
}
const play = id => { pinned = null; post("/api/play", {id, delay: +delay.value}); };
$("replay").onclick = () => current && play(current);
$("stop").onclick = () => post("/api/stop");
$("clear").onclick = () => post("/api/clear");

const moveLabel = i => `${Math.floor(i / 2) + 1}${i % 2 ? "..." : "."}`;

function showNote(o, i) {
  const n = $("note");
  n.innerHTML = "";
  if (!o || i < 0 || !o.notes[i]) return;
  const b = document.createElement("b");
  b.textContent = moveLabel(i) + o.san[i];
  n.append(b, o.notes[i]);
}

async function init() {
  const list = await (await fetch("/api/openings")).json();
  const groups = {};
  for (const o of list) { openings[o.id] = o; (groups[o.group] ||= []).push(o); }
  for (const [g, ops] of Object.entries(groups)) {
    const h = document.createElement("h2"); h.textContent = g; $("groups").append(h);
    const grid = document.createElement("div"); grid.className = "grid";
    for (const o of ops) {
      const b = document.createElement("button");
      b.className = "op"; b.dataset.id = o.id;
      b.innerHTML = `<b></b><span></span>`;
      b.querySelector("b").textContent = o.name;
      b.querySelector("span").textContent =
        o.san.slice(0, 4).join(" ") + " …  · " + Math.ceil(o.san.length / 2) + " moves";
      b.onclick = () => play(o.id);
      grid.append(b);
    }
    $("groups").append(grid);
  }
  for (let i = 0; i < 64; i++) {
    const d = document.createElement("div");
    d.className = "sq " + (((i >> 3) + i) % 2 ? "d" : "l");
    $("board").append(d);
  }
  poll();
}

function draw(s) {
  const changed = s.opening !== current;
  current = s.opening;
  document.querySelectorAll(".op").forEach(b => b.classList.toggle("active", b.dataset.id === s.opening));
  const cells = $("board").children;
  for (let i = 0; i < 64; i++) {
    const ch = s.board[i], c = cells[i];
    c.textContent = ch === "." ? "" : GLYPH[ch.toLowerCase()];
    c.className = "sq " + (((i >> 3) + i) % 2 ? "d" : "l") +
      (ch === "." ? "" : ch === ch.toUpperCase() ? " w" : " k");
    if (s.last && i === s.last[0]) c.classList.add("from");
    if (s.last && i === s.last[1]) c.classList.add("to");
  }
  const o = openings[s.opening];
  $("now").textContent = o ? `${o.name} — ${s.playing ? "move " + s.ply + "/" + s.total : "done"}` : "Nothing playing";
  if (changed) $("about").textContent = o ? o.about : "";

  // move list: dotted underline = has a note; tap to read it
  $("moves").innerHTML = "";
  if (o) o.san.forEach((m, i) => {
    if (i % 2 === 0) $("moves").append(`${i / 2 + 1}. `);
    const sp = document.createElement("span"); sp.textContent = m;
    if (o.notes[i]) { sp.className = "has-note"; sp.onclick = () => { pinned = i; showNote(o, i); }; }
    if (i === s.ply - 1) sp.classList.add("cur");
    $("moves").append(sp, " ");
  });

  // while playing, show the note for the latest move that has one
  if (s.ply !== lastPly || changed) {
    lastPly = s.ply;
    if (s.playing || pinned === null) {
      pinned = null;
      let i = s.ply - 1;
      while (o && i >= 0 && !o.notes[i]) i--;
      showNote(o, i);
    }
  }
}

async function poll() {
  try { draw(await (await fetch("/api/state")).json()); $("err").textContent = ""; }
  catch (e) { $("err").textContent = "Lost connection to the Pi."; }
  setTimeout(poll, 250);
}
init();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------- entry

if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Open http://ryanpi.local:{PORT} on any device on the same network (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        start_job(None)
        sense.clear()
