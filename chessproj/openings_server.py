#!/usr/bin/env python3
"""
Opening explorer: a web page of opening buttons that plays the chosen line
on the Sense HAT 8x8 LED matrix.

    python3 openings_server.py
    then open  http://ryanpi.local:8000  on a phone or laptop on the same Wi-Fi

No extra packages needed beyond sense_hat (standard library web server).
Colours match lichess.py: amber = white pieces, blue = black pieces,
brightness = piece value, white flash = the square a piece just moved to.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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

# (id, name, group, moves in UCI, moves in SAN for display)
# To add one: copy a line and type the moves as from-square + to-square.
OPENINGS = [
    ("italian", "Italian Game", "1.e4",
     "e2e4 e7e5 g1f3 b8c6 f1c4 f8c5",
     "e4 e5 Nf3 Nc6 Bc4 Bc5"),
    ("ruy", "Ruy Lopez", "1.e4",
     "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 b5a4 g8f6 e1g1",
     "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O"),
    ("kingsgambit", "King's Gambit", "1.e4",
     "e2e4 e7e5 f2f4 e5f4",
     "e4 e5 f4 exf4"),
    ("friedliver", "Fried Liver Attack", "1.e4",
     "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 f3g5 d7d5 e4d5 f6d5 g5f7 e8f7",
     "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7 Kxf7"),
    ("scholars", "Scholar's Mate", "1.e4",
     "e2e4 e7e5 f1c4 b8c6 d1h5 g8f6 h5f7",
     "e4 e5 Bc4 Nc6 Qh5 Nf6 Qxf7#"),
    ("najdorf", "Sicilian Najdorf", "1.e4",
     "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6",
     "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6"),
    ("french", "French Defense", "1.e4",
     "e2e4 e7e6 d2d4 d7d5 b1c3 g8f6",
     "e4 e6 d4 d5 Nc3 Nf6"),
    ("caro", "Caro-Kann", "1.e4",
     "e2e4 c7c6 d2d4 d7d5 b1c3 d5e4 c3e4 c8f5",
     "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5"),
    ("scandi", "Scandinavian", "1.e4",
     "e2e4 d7d5 e4d5 d8d5 b1c3 d5a5",
     "e4 d5 exd5 Qxd5 Nc3 Qa5"),
    ("qgd", "Queen's Gambit Declined", "1.d4",
     "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6 c1g5 f8e7",
     "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7"),
    ("qga", "Queen's Gambit Accepted", "1.d4",
     "d2d4 d7d5 c2c4 d5c4 g1f3 g8f6 e2e3",
     "d4 d5 c4 dxc4 Nf3 Nf6 e3"),
    ("kid", "King's Indian", "1.d4",
     "d2d4 g8f6 c2c4 g7g6 b1c3 f8g7 e2e4 d7d6 g1f3 e8g8",
     "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O"),
    ("london", "London System", "1.d4",
     "d2d4 d7d5 c1f4 g8f6 e2e3 e7e6 g1f3 c7c5",
     "d4 d5 Bf4 Nf6 e3 e6 Nf3 c5"),
    ("english", "English Opening", "Other",
     "c2c4 e7e5 b1c3 g8f6 g1f3 b8c6",
     "c4 e5 Nc3 Nf6 Nf3 Nc6"),
]
OPENINGS = {o[0]: {"id": o[0], "name": o[1], "group": o[2],
                   "uci": o[3].split(), "san": o[4].split()} for o in OPENINGS}

# ---------------------------------------------------------------- board logic

START = list("rnbqkbnr" "pppppppp" + "." * 32 + "PPPPPPPP" "RNBQKBNR")  # index 0 = a8


def sq(name):
    return (8 - int(name[1])) * 8 + ord(name[0]) - ord("a")


def apply_move(board, uci):
    """Play one UCI move on a 64-char board, handling castling and en passant."""
    b = board[:]
    f, t = sq(uci[:2]), sq(uci[2:4])
    piece = b[f]
    if piece in "Pp" and f % 8 != t % 8 and b[t] == ".":      # en passant
        b[f - f % 8 + t % 8] = "."
    if piece in "Kk" and abs(f % 8 - t % 8) == 2:              # castling
        row = f - f % 8
        if t % 8 == 6:
            b[row + 5], b[row + 7] = b[row + 7], "."
        else:
            b[row + 3], b[row] = b[row], "."
    b[t], b[f] = piece, "."
    if len(uci) == 5:                                          # promotion
        b[t] = uci[4].upper() if piece.isupper() else uci[4]
    return b, (f, t)


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
    board = START[:]
    set_state(opening=opening_id, ply=0, total=len(op["uci"]), playing=True,
              board="".join(board), last=None)
    render(board)
    if not wait(delay, my_job):
        return
    for i, mv in enumerate(op["uci"]):
        board, (f, t) = apply_move(board, mv)
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
            self.send(json.dumps(list(OPENINGS.values())))
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
      b.querySelector("span").textContent = o.san.slice(0, 4).join(" ") + (o.san.length > 4 ? " …" : "");
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
