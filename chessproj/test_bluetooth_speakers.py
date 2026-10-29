"""Hardware-independent checks. Run: python3 -B -m unittest -v test_bluetooth_speakers.py"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bluetooth_speakers as app

MAC = "AA:BB:CC:DD:EE:FF"


class SpeakerTests(unittest.TestCase):
    def test_audio_receiver_and_loudspeaker(self):
        self.assertTrue(app.speaker_candidate({"UUIDs": [app.AUDIO_SINK]}))
        self.assertTrue(app.speaker_candidate({"Class": 0x0414}))

    def test_headphones_and_headsets_are_included(self):
        for props in ({"UUIDs": [app.AUDIO_SINK], "Class": 0x0418},
                      {"Icon": "audio-headset"}, {"Class": 0x0404}):
            self.assertTrue(app.speaker_candidate(props))

    def test_no_phones_keyboards_or_microphones(self):
        for props in ({"Class": 0x020C}, {"Class": 0x0540}, {"Class": 0x0410}, {}):
            with self.subTest(props=props):
                self.assertFalse(app.speaker_candidate(props))

    def test_sink_matches_exact_address_and_playback_class(self):
        def node(index, **props):
            return {"id": index, "info": {"props": props}}
        objects = [node(1, **{"media.class": "Audio/Source", "api.bluez5.address": MAC}),
                   node(2, **{"media.class": "Audio/Sink", "api.bluez5.address": "00:11:22:33:44:55"}),
                   node(3, **{"media.class": "Audio/Sink", "api.bluez5.address": MAC.lower()})]
        self.assertEqual(app.find_sink(objects, MAC), 3)
        objects[2]["info"]["props"] = {"media.class": "Audio/Sink", "node.name": "bluez_output.AA_BB_CC_DD_EE_FF.1"}
        self.assertEqual(app.find_sink(objects, MAC), 3)
        self.assertIsNone(app.find_sink(objects, "AA:BB:CC:DD:EE:00"))

    def test_pair_trust_connect_order_and_skip_existing_pair(self):
        for paired in (False, True):
            with self.subTest(paired=paired):
                bt = app.Bluetooth.__new__(app.Bluetooth)
                bt.path = "/org/bluez/hci0"
                bt.dbus = SimpleNamespace(Boolean=bool)
                device, props = Mock(), Mock()
                props.Get.side_effect = [paired, False]
                bt.interface = Mock(side_effect=[device, props])
                bt.call_async = Mock()
                bt.connect(MAC)
                methods = [call.args[0] for call in bt.call_async.call_args_list]
                self.assertEqual(methods, [device.Connect] if paired else [device.Pair, device.Connect])
                props.Set.assert_called_once_with(app.DEVICE, "Trusted", True)
                self.assertIsNone(bt.target)

    def test_pair_failure_cancels_pairing_and_clears_target(self):
        bt = app.Bluetooth.__new__(app.Bluetooth)
        bt.path = "/org/bluez/hci0"
        bt.dbus = SimpleNamespace(Boolean=bool, DBusException=Exception)
        device, props = Mock(), Mock()
        props.Get.return_value = False
        bt.interface = Mock(side_effect=[device, props])
        bt.call_async = Mock(side_effect=RuntimeError("pairing rejected"))
        with self.assertRaisesRegex(RuntimeError, "rejected"):
            bt.connect(MAC)
        device.CancelPairing.assert_called_once()
        self.assertIsNone(bt.target)
        props.Set.assert_not_called()

    def test_audio_routes_only_selected_sink(self):
        import json
        objects = [{"id": 42, "info": {"props": {"media.class": "Audio/Sink", "api.bluez5.address": MAC}}}]
        with patch.object(app, "command", return_value=json.dumps(objects)) as cmd:
            app.select_audio(MAC, 40)
        self.assertEqual(cmd.call_args_list[1].args, ("wpctl", "set-default", "42"))
        self.assertEqual(cmd.call_args_list[2].args, ("wpctl", "set-mute", "42", "0"))
        self.assertEqual(cmd.call_args_list[3].args, ("wpctl", "set-volume", "42", "40%"))

    def test_joystick_wrap_ignores_release_and_selects(self):
        def event(direction, action="pressed"):
            return SimpleNamespace(direction=direction, action=action)
        sense = Mock()
        sense.stick.get_events.side_effect = [[], [event("down", "released")],
                                             [event("up")], [event("middle")]]
        with patch.object(app.time, "sleep"):
            self.assertEqual(app.pick(sense, ["SPEAKER", "RESCAN", "QUIT"]), 2)
        self.assertTrue(sense.set_pixels.called)
        self.assertEqual(len(sense.set_pixels.call_args.args[0]), 64)

    def test_scrolling_unknown_characters(self):
        strip = app.columns("JBL / test 🎵")
        self.assertGreater(len(strip), 8)
        self.assertTrue(all(len(column) == 5 for column in strip))
        self.assertEqual(len(app.FONT), 41)


if __name__ == "__main__":
    unittest.main()
