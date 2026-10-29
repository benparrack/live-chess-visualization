"""Checks for menu.py's middle button and Bluetooth screen, on the simulator.
Run from chessproj/: python3 -B -m unittest -v test_menu.py"""

import os
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("SENSE_SIM_FD", str(os.open(os.devnull, os.O_WRONLY)))
sys.path.insert(0, os.path.join(HERE, "sim"))

import menu  # noqa: E402  (needs the simulator set up first)
import panel  # noqa: E402

SPEAKERS = [{"name": "Desk", "address": "AA:BB:CC:DD:EE:01"},
            {"name": "Party", "address": "AA:BB:CC:DD:EE:02"}]


def press(direction, action="pressed"):
    return SimpleNamespace(direction=direction, action=action)


def press_later(*directions):
    """Joystick presses that arrive once the speaker list is up."""
    def send():
        time.sleep(0.3)
        for d in directions:
            menu.stick_events.put(press(d))
    threading.Thread(target=send, daemon=True).start()


class MenuTest(unittest.TestCase):
    def setUp(self):
        panel.should_quit = panel.restart_stream = False
        menu.want_bluetooth = menu.switching = False
        menu.pressed_at = None

    def test_click_opens_bluetooth(self):
        menu.on_middle(press("middle"))
        menu.on_middle(press("middle", "released"))
        self.assertTrue(menu.want_bluetooth and menu.switching and panel.should_quit)

    def test_hold_quits_instead(self):
        menu.on_middle(press("middle"))
        menu.pressed_at -= menu.QUIT_HOLD_SECONDS
        menu.on_middle(press("middle", "held"))
        menu.on_middle(press("middle", "released"))
        self.assertTrue(panel.should_quit)
        self.assertFalse(menu.want_bluetooth or menu.switching)

    @patch.object(menu, "message")
    @patch.object(menu.bluetooth_speakers, "select_audio")
    def test_scroll_down_and_connect(self, select_audio, message):
        bt = Mock(scan=Mock(return_value=SPEAKERS))
        with patch.object(menu.bluetooth_speakers, "Bluetooth", return_value=bt):
            press_later("down", "middle")
            menu.run_bluetooth()
        bt.connect.assert_called_once_with("AA:BB:CC:DD:EE:02")
        select_audio.assert_called_once_with("AA:BB:CC:DD:EE:02", menu.SPEAKER_VOLUME)
        self.assertIn("CONNECTED", message.call_args.args[0])
        bt.close.assert_called_once()
        self.assertFalse(menu.in_bluetooth)

    def test_back_leaves_without_connecting(self):
        bt = Mock(scan=Mock(return_value=SPEAKERS))
        with patch.object(menu.bluetooth_speakers, "Bluetooth", return_value=bt):
            press_later("up", "middle")   # wraps from the first speaker to BACK
            menu.run_bluetooth()
        bt.connect.assert_not_called()

    @patch.object(menu, "message")
    def test_no_bluetooth_shows_an_error(self, message):
        with patch.object(menu.bluetooth_speakers, "Bluetooth", side_effect=RuntimeError("no adapter")):
            menu.run_bluetooth()
        self.assertEqual(message.call_args.args[0], "NO BLUETOOTH")
        self.assertFalse(menu.in_bluetooth)


if __name__ == "__main__":
    unittest.main()
