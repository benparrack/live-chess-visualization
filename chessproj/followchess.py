#!/usr/bin/env python3
"""
Follow a Lichess player's live game on the Sense HAT 8x8 LED matrix.

Watches the usernames in FOLLOW_USERS. When one of them starts a game, the
panel picks it up, shows every move, and goes back to waiting when it ends.
No Lichess account or token is needed on the Pi.
Game events also play sounds through the default audio output (see sound.py).

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
import queue
import sys
import threading
import time
import urllib.parse
import urllib.request

import panel

# ---------------------------------------------------------------- settings

FOLLOW_USERS = ["datavis"]   # Lichess usernames to watch, any number
user_index = 0               # which one wins if several are playing at once

POLL_SECONDS = 5        # how often to ask "is anyone playing (something new)?"
STREAM_TIMEOUT = 90     # a quiet game stream reconnects after this long
CATCHUP_GAP = 0.4       # stream lines closer together than this are history


# ---------------------------------------------------------------- joystick

def on_left(event):
    global user_index
    if event.action == "pressed" and len(FOLLOW_USERS) > 1:
        user_index = (user_index - 1) % len(FOLLOW_USERS)
        panel.restart_stream = True


def on_right(event):
    global user_index
    if event.action == "pressed" and len(FOLLOW_USERS) > 1:
        user_index = (user_index + 1) % len(FOLLOW_USERS)
        panel.restart_stream = True


panel.sense.stick.direction_left = on_left
panel.sense.stick.direction_right = on_right


# ---------------------------------------------------------------- lichess

def get_json(url, timeout=15):
    request = urllib.request.Request(url, headers={"User-Agent": panel.USER_AGENT,
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
    board = panel.expand_fen(data["fen"]) if "fen" in data else None

    if board:
        old_board = state.get("board")
        move = panel.parse_last_move(data.get("lm"))

        if old_board is None:
            panel.new_game_reveal(board)
        elif live and move and old_board != board:
            panel.show_move(old_board, board, move, panel.white_to_move(data["fen"]))
        else:
            # Replaying the game's history: draw it, but don't animate every move.
            panel.render(board)

        state["board"] = board

    # Lichess status ids: 10 created, 20 started, 25+ finished in some way.
    if data.get("status", {}).get("id", 0) >= 25:
        if state.get("board") and status != "aborted":
            panel.show_game_over(state["board"], status, data.get("winner"))
        return True
    return False


def read_stream(stream, lines):
    """Background reader, so the main loop isn't stuck while a game is quiet.
    Lines are timestamped on arrival, before any slow animation runs."""
    try:
        for raw in stream:
            lines.put((time.monotonic(), raw))
        lines.put((time.monotonic(), None))   # stream closed
    except Exception as exc:
        lines.put((time.monotonic(), exc))


def switched_game(game_id):
    """A different live game for the followed users, or None."""
    try:
        found = find_live_game()
    except Exception:
        return None   # a failed check isn't a reason to drop the game
    if found and found[1] != game_id:
        return found
    return None


def follow_game(game_id, watch_users=True):
    """Stream one game. Returns True once done with it, so it isn't picked again.

    With watch_users, it also gives up the game when a followed user is in a
    different one -- an unfinished game (a bot game nobody resigned) never ends
    on its own, and its stream just sits there sending a keep-alive every ~50s.
    """
    state = {"board": None}
    while not panel.should_quit and not panel.restart_stream:
        url = f"https://lichess.org/api/stream/game/{game_id}"
        request = urllib.request.Request(url, headers={"User-Agent": panel.USER_AGENT})
        if state["board"] is None:
            panel.show_status("connecting")
        try:
            stream = urllib.request.urlopen(request, timeout=STREAM_TIMEOUT)
        except Exception as exc:
            print(f"stream error: {exc}", file=sys.stderr)
            panel.wait(3, "offline")
            continue

        lines = queue.Queue()
        threading.Thread(target=read_stream, args=(stream, lines), daemon=True).start()
        # Every connect starts with the whole move history in one quick
        # burst. The first pause between lines marks the switch to live.
        live = False
        last = None
        next_check = time.monotonic() + POLL_SECONDS
        try:
            while True:
                if panel.restart_stream or panel.should_quit:
                    return False
                if watch_users and time.monotonic() >= next_check:
                    other = switched_game(game_id)
                    if other:
                        print(f"{other[0]} is in a new game, leaving {game_id}")
                        return True
                    next_check = time.monotonic() + POLL_SECONDS
                try:
                    arrived, raw = lines.get(timeout=0.1)
                except queue.Empty:
                    continue
                if raw is None:
                    break   # closed without an ending; reconnect
                if isinstance(raw, Exception):
                    # Includes the timeout during a long think; reconnecting is harmless.
                    print(f"stream error: {raw}", file=sys.stderr)
                    panel.wait(3, "offline")
                    break
                if last is not None and arrived - last > CATCHUP_GAP:
                    live = True
                last = arrived
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    if handle_line(json.loads(line), state, live):
                        return True
                except (ValueError, KeyError, IndexError):
                    continue  # skip a bad line, keep the display alive
        finally:
            stream.close()   # the reader thread then ends on its own
    return False


def run_follow():
    """Wait for a followed user to start a game, show it, repeat."""
    finished = set()   # ended (status can say "playing" for a moment after) or left for a newer game
    panel.show_status("connecting")
    while not panel.should_quit:
        panel.restart_stream = False
        try:
            found = find_live_game()
        except Exception as exc:
            print(f"status error: {exc}", file=sys.stderr)
            panel.wait(POLL_SECONDS, "offline")
            continue

        if found and found[1] not in finished:
            name, game_id = found
            print(f"following {name}: https://lichess.org/{game_id}")
            if follow_game(game_id):
                finished.add(game_id)
        else:
            panel.wait(POLL_SECONDS, "waiting")


def run_single(game_id):
    """Follow one given game, then hold the final position until quit."""
    print(f"following https://lichess.org/{game_id}")
    while not panel.should_quit:
        panel.restart_stream = False
        if follow_game(game_id, watch_users=False):
            break
    while not panel.should_quit:
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
        panel.sense.clear()
