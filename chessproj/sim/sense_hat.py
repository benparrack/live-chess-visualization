"""
Stand-in for the real sense_hat module, used by pisim.py.

Frames go to the viewer as JSON lines on the fd in SENSE_SIM_FD;
joystick presses come back as direction names on stdin.
"""

import json
import os
import sys
import threading
from collections import namedtuple

InputEvent = namedtuple("InputEvent", "timestamp direction action")

_out = os.fdopen(int(os.environ["SENSE_SIM_FD"]), "w", buffering=1)


class SenseStick:
    def __init__(self):
        for d in ("up", "down", "left", "right", "middle", "any"):
            setattr(self, "direction_" + d, None)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        import time
        for line in sys.stdin:
            direction = line.strip()
            for action in ("pressed", "released"):
                event = InputEvent(time.time(), direction, action)
                for cb in (getattr(self, "direction_" + direction, None), self.direction_any):
                    if cb:
                        cb(event)


class SenseHat:
    def __init__(self):
        self._pixels = [[0, 0, 0]] * 64
        self.low_light = False
        self.stick = SenseStick()
        self._send()

    # shortcut: rotation is ignored -- the window shows the image as you'd see it
    # with the panel mounted the way ROTATION assumes.
    def set_rotation(self, r=0, redraw=True):
        pass

    def _send(self):
        try:
            _out.write(json.dumps(self._pixels) + "\n")
        except BrokenPipeError:
            os._exit(0)  # viewer closed

    def set_pixels(self, pixels):
        if len(pixels) != 64:
            raise ValueError("Pixel lists must have 64 elements")
        self._pixels = [[max(0, min(255, int(c))) for c in p] for p in pixels]
        self._send()

    def get_pixels(self):
        return [list(p) for p in self._pixels]

    def set_pixel(self, x, y, *rgb):
        self._pixels[y * 8 + x] = [int(c) for c in (rgb[0] if len(rgb) == 1 else rgb)]
        self._send()

    def get_pixel(self, x, y):
        return list(self._pixels[y * 8 + x])

    def clear(self, *rgb):
        colour = list(rgb[0] if len(rgb) == 1 else rgb) if rgb else [0, 0, 0]
        self.set_pixels([colour] * 64)
