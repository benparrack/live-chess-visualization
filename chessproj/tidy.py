#!/usr/bin/env python3
"""
Turn a saved Lichess TV capture into two CSVs for the data milestone.

    python3 tidy.py capture.ndjson

raw.csv   one row per feed event, as Lichess sends it (board packed in a FEN string)
tidy.csv  one row per (move, square): the FEN unpivoted into 64 observations
"""

import csv
import json
import sys

# Not imported from colorchess: that module needs the Sense HAT to import.
NAMES = {"p": "pawn", "n": "knight", "b": "bishop", "r": "rook", "q": "queen", "k": "king"}


def expand_fen(fen):
    board = []
    for rank in fen.split(" ")[0].split("/"):
        for ch in rank:
            board.extend("." * int(ch) if ch.isdigit() else ch)
    return board if len(board) == 64 else None


def main(path):
    raw, tidy = [], []
    game, ply = None, 0
    for line in open(path):
        if not line.strip():
            continue
        event = json.loads(line)
        d = event["d"]
        if event["t"] == "featured":
            game, ply = d["id"], 0
        else:
            ply += 1
        fields = d["fen"].split(" ")
        raw.append({"event": event["t"], "game_id": game, "fen": d["fen"],
                    "last_move": d.get("lm", ""), "white_clock": d.get("wc", ""),
                    "black_clock": d.get("bc", "")})

        board = expand_fen(d["fen"])
        if board is None:
            continue  # malformed FEN: drop the snapshot, keep the rest
        lm = d.get("lm", "")
        for i, ch in enumerate(board):
            square = "abcdefgh"[i % 8] + str(8 - i // 8)
            tidy.append({
                "game_id": game, "ply": ply, "move_number": int(fields[5]),
                "side_to_move": "white" if fields[1] == "w" else "black",
                "square": square, "file": square[0], "rank": square[1],
                "piece": "" if ch == "." else NAMES[ch.lower()],
                "colour": "" if ch == "." else ("white" if ch.isupper() else "black"),
                "moved_from": square == lm[0:2], "moved_to": square == lm[2:4],
            })

    for name, rows in (("raw.csv", raw), ("tidy.csv", tidy)):
        with open(name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
    print(f"{len(raw)} events -> {len(tidy)} tidy rows")


if __name__ == "__main__":
    main(sys.argv[1])
