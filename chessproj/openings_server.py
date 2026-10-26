#!/usr/bin/env python3
"""
Opening explorer: a web page of opening buttons that plays the chosen line
on the Sense HAT 8x8 LED matrix.

    python3 openings_server.py
    then open  http://ryanpi.local:8000  on a phone or laptop on the same Wi-Fi

Needs: sense_hat and python-chess   (sudo apt install -y python3-chess)
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

# (id, name, group, moves in normal chess notation)
# To add one: copy a line and paste the moves from Lichess, Wikipedia, etc.
# Move numbers like "1." are fine to leave in. A typo stops the server at
# startup and tells you which move is wrong.
OPENING_LINES = [
    ("italian", "Italian Game", "1.e4",
     "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6 O-O O-O Re1 a6 Bb3 Ba7 h3 h6 Nbd2 Re8"),
    ("ruy", "Ruy Lopez", "1.e4",
     "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Na5 Bc2 c5 d4 Qc7"),
    ("kingsgambit", "King's Gambit", "1.e4",
     "e4 e5 f4 exf4 Nf3 g5 h4 g4 Ne5 Nf6 d4 d6 Nd3 Nxe4 Bxf4 Bg7 c3 Qe7 Qe2 Bf5"),
    ("friedliver", "Fried Liver Attack", "1.e4",
     "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7 Kxf7 Qf3+ Ke6 Nc3 Ncb4 a3 Nxc2+ Kd1 Nxa1 Nxd5 Qh4"),
    ("scholars", "Scholar's Mate", "1.e4",
     "e4 e5 Bc4 Nc6 Qh5 Nf6 Qxf7#"),
    ("najdorf", "Sicilian Najdorf", "1.e4",
     "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Be3 e5 Nb3 Be6 f3 Be7 Qd2 O-O O-O-O Nbd7 g4 b5"),
    ("french", "French Defense", "1.e4",
     "e4 e6 d4 d5 Nc3 Nf6 Bg5 Be7 e5 Nfd7 Bxe7 Qxe7 f4 O-O Nf3 c5 Qd2 Nc6 O-O-O c4"),
    ("caro", "Caro-Kann", "1.e4",
     "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 h4 h6 Nf3 Nd7 h5 Bh7 Bd3 Bxd3 Qxd3 e6 Bd2 Ngf6 O-O-O Be7"),
    ("scandi", "Scandinavian", "1.e4",
     "e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6 Nf3 c6 Bc4 Bf5 Bd2 e6 Nd5 Qd8 Nxf6+ Qxf6 Qe2 Nd7"),
    ("qgd", "Queen's Gambit Declined", "1.d4",
     "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 Nbd7 Rc1 c6 Bd3 dxc4 Bxc4 Nd5 Bxe7 Qxe7 O-O Nxc3 Rxc3 e5"),
    ("qga", "Queen's Gambit Accepted", "1.d4",
     "d4 d5 c4 dxc4 Nf3 Nf6 e3 e6 Bxc4 c5 O-O a6 dxc5 Qxd1 Rxd1 Bxc5 Kf1 b5 Be2 Bb7"),
    ("kid", "King's Indian", "1.d4",
     "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5 O-O Nc6 d5 Ne7 Ne1 Nd7 Nd3 f5 Bd2 Nf6 f3 f4"),
    ("london", "London System", "1.d4",
     "d4 d5 Bf4 Nf6 e3 e6 Nf3 c5 c3 Nc6 Nbd2 Bd6 Bg3 O-O Bd3 b6 Ne5 Bb7 f4 Ne7"),
    ("english", "English Opening", "Other",
     "c4 e5 Nc3 Nf6 Nf3 Nc6 g3 d5 cxd5 Nxd5 Bg2 Nb6 O-O Be7 d3 O-O a3 Be6 b4 f6"),
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


OPENINGS = {}
for _id, _name, _group, _text in OPENING_LINES:
    _moves, _san = parse_line(_name, _text)
    OPENINGS[_id] = {"id": _id, "name": _name, "group": _group,
                     "moves": _moves, "san": _san}


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
        if not wait(max(0.0, delay - FLASH_SECONDS), my_job):
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
         font:15px/1.4 system-ui, -apple-system, Segoe UI, sans-serif; }
  main { max-width:980px; margin:0 auto; padding:20px 16px 40px;
         display:grid; gap:24px; grid-template-columns:1fr 320px; }
  @media (max-width:760px) { main { grid-template-columns:1fr; } aside { order:-1; } }
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
  .moves { color:var(--muted); font-size:14px; min-height:2.8em; }
  .moves .cur { color:var(--text); background:#3a3f4a; border-radius:4px; padding:0 3px; }
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
let openings = {}, current = null;
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
const play = id => post("/api/play", {id, delay: +delay.value});
$("replay").onclick = () => current && play(current);
$("stop").onclick = () => post("/api/stop");
$("clear").onclick = () => post("/api/clear");

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
  $("moves").innerHTML = "";
  if (o) o.san.forEach((m, i) => {
    if (i % 2 === 0) $("moves").append(`${i / 2 + 1}. `);
    const sp = document.createElement("span"); sp.textContent = m;
    if (i === s.ply - 1) sp.className = "cur";
    $("moves").append(sp, " ");
  });
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
