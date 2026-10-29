"""Checks for panel.py's status animation and stream reader, on the simulator.
Run from chessproj/: python3 -B -m unittest -v test_panel.py"""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("SENSE_SIM_FD", str(os.open(os.devnull, os.O_WRONLY)))
sys.path.insert(0, os.path.join(HERE, "sim"))

import panel  # noqa: E402  (needs the simulator set up first)

frames = 0
draw = panel.sense.set_pixels


def counted(pixels):
    global frames
    frames += 1
    draw(pixels)


panel.sense.set_pixels = counted


def frame_count():
    return frames


class FakeStream:
    """Stands in for a urllib response: sends `lines` slowly, then ends or fails."""

    def __init__(self, lines, error=None):
        self.lines, self.error, self.closed = lines, error, False

    def __iter__(self):
        for line in self.lines:
            time.sleep(0.35)
            yield line
        if self.error:
            raise self.error

    def close(self):
        self.closed = True


class PanelTest(unittest.TestCase):
    def setUp(self):
        panel.should_quit = panel.restart_stream = False

    def tearDown(self):
        panel.clear()

    def test_status_keeps_animating_while_main_thread_is_busy(self):
        panel.show_status("connecting")
        before = frame_count()
        time.sleep(1.0)   # as if stuck in a network call
        self.assertGreaterEqual(frame_count() - before, 7)

    def test_board_stops_the_status_animation(self):
        panel.show_status("connecting")
        time.sleep(0.25)
        panel.render(panel.expand_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w"))
        before = frame_count()
        time.sleep(0.5)
        self.assertEqual(frame_count(), before, "status animation drew over the board")

    def read(self, stream):
        real = panel.urllib.request.urlopen
        panel.urllib.request.urlopen = lambda request, data=None, timeout=None: (
            stream if data is None and timeout == 1 else None)
        try:
            return list(panel.read_lines("request", 1))
        finally:
            panel.urllib.request.urlopen = real

    def test_read_lines_ticks_while_quiet_and_closes_the_stream(self):
        stream = FakeStream([b"a\n", b"b\n"])
        got = self.read(stream)
        self.assertEqual([raw for _, raw in got if raw is not None], [b"a\n", b"b\n"])
        self.assertGreaterEqual(sum(raw is None for _, raw in got), 4)
        time.sleep(0.1)
        self.assertTrue(stream.closed)

    def test_read_lines_raises_stream_errors(self):
        with self.assertRaises(TimeoutError):
            self.read(FakeStream([b"a\n"], TimeoutError("read timed out")))

    def test_background_returns_none_when_the_joystick_cuts_in(self):
        start = time.monotonic()
        panel.restart_stream = True
        self.assertIsNone(panel.background(time.sleep, 5))
        self.assertLess(time.monotonic() - start, 0.5)

    def test_background_returns_result_and_raises_errors(self):
        self.assertEqual(panel.background(sum, [1, 2]), 3)
        with self.assertRaises(ZeroDivisionError):
            panel.background(divmod, 1, 0)


if __name__ == "__main__":
    unittest.main()
