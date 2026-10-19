#!/usr/bin/env python3
"""
Pretend Sense HAT: runs one of the panel programs unchanged and shows its 8x8 LEDs in a window.

    python3 pisim.py colorchess.py                    # live Lichess TV
    python3 pisim.py colorchess.py capture.ndjson     # replay
    python3 pisim.py legend.py

Arrow keys / Enter = joystick, R = restart. Saving any .py in this folder restarts the program.
"""

import json
import os
import subprocess
import sys
import threading
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
CELL, LED, PAD = 56, 44, 24


def mtimes():
    files = [os.path.join(HERE, f) for f in os.listdir(HERE) if f.endswith(".py")]
    files.append(os.path.join(HERE, "sim", "sense_hat.py"))
    return {f: os.path.getmtime(f) for f in files if os.path.exists(f)}


class Viewer:
    def __init__(self, argv):
        self.argv = argv
        self.child = None
        self.frame = None
        self.root = tk.Tk()
        self.root.title("Sense HAT - " + " ".join(argv))
        size = PAD * 2 + CELL * 8
        self.canvas = tk.Canvas(self.root, width=size, height=size, bg="#0b3d1f", highlightthickness=0)
        self.canvas.pack()
        self.status = tk.Label(self.root, anchor="w")
        self.status.pack(fill="x")
        off = (CELL - LED) // 2
        self.leds = [self.canvas.create_rectangle(
            PAD + c * CELL + off, PAD + r * CELL + off,
            PAD + c * CELL + off + LED, PAD + r * CELL + off + LED,
            fill="#000000", outline="#222222") for r in range(8) for c in range(8)]

        keys = {"Up": "up", "Down": "down", "Left": "left", "Right": "right", "Return": "middle"}
        for key, direction in keys.items():
            self.root.bind(f"<{key}>", lambda e, d=direction: self.press(d))
        self.root.bind("<r>", lambda e: self.start())
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self.seen = mtimes()
        self.start()
        self.tick()
        self.root.mainloop()

    def start(self):
        self.stop()
        read_fd, write_fd = os.pipe()
        env = dict(os.environ, SENSE_SIM_FD=str(write_fd),
                   PYTHONPATH=os.pathsep.join([os.path.join(HERE, "sim"), os.environ.get("PYTHONPATH", "")]))
        self.child = subprocess.Popen([sys.executable, "-u", *self.argv], cwd=HERE, env=env,
                                      stdin=subprocess.PIPE, pass_fds=(write_fd,), text=True)
        os.close(write_fd)
        threading.Thread(target=self.read, args=(os.fdopen(read_fd), self.child), daemon=True).start()
        self.status.config(text=f"running  (pid {self.child.pid})")

    def read(self, pipe, child):
        for line in pipe:
            if child is self.child:  # drop late frames from a killed run
                self.frame = json.loads(line)

    def stop(self):
        if self.child and self.child.poll() is None:
            self.child.terminate()
            self.child.wait()

    def press(self, direction):
        if self.child and self.child.poll() is None:
            try:
                self.child.stdin.write(direction + "\n")
                self.child.stdin.flush()
            except BrokenPipeError:
                pass

    def tick(self):
        if self.frame is not None:
            for item, (r, g, b) in zip(self.leds, self.frame):
                self.canvas.itemconfig(item, fill=f"#{r:02x}{g:02x}{b:02x}")
            self.frame = None

        now = mtimes()
        if now != self.seen:
            self.seen = now
            self.start()
            self.status.config(text="file changed - restarted")
        elif self.child.poll() is not None:
            self.status.config(text=f"exited (code {self.child.returncode}) - press R or save a file to rerun")

        self.root.after(30, self.tick)

    def quit(self):
        self.stop()
        self.root.destroy()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    Viewer(sys.argv[1:])
