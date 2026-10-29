#!/usr/bin/env python3
"""Standalone Raspberry Pi Bluetooth speaker picker; see bluetooth_speakers.md."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

AUDIO_SINK = "0000110b-0000-1000-8000-00805f9b34fb"
DEVICE = "org.bluez.Device1"
ADAPTER = "org.bluez.Adapter1"
PROPERTIES = "org.freedesktop.DBus.Properties"


def speaker_candidate(props):
    """Accept A2DP receivers and recognized Bluetooth audio-output classes."""
    klass = int(props.get("Class", 0))
    audio_class = (klass & 0x1F00) == 0x0400
    minor = (klass >> 2) & 0x3F
    sink = AUDIO_SINK in {str(uuid).lower() for uuid in props.get("UUIDs", [])}
    # Headset, hands-free, speaker, headphones, portable/car/hi-fi audio.
    output_class = audio_class and minor in (1, 2, 5, 6, 7, 8, 10)
    output_icon = str(props.get("Icon", "")) in ("audio-headphones", "audio-headset")
    return sink or output_class or output_icon


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or str(args))
    return result.stdout


def find_sink(objects, address):
    """Match the chosen speaker exactly, not another connected Bluetooth sink."""
    token = address.upper().replace(":", "_")
    for obj in objects:
        props = obj.get("info", {}).get("props", {})
        if props.get("media.class") != "Audio/Sink":
            continue
        if (str(props.get("api.bluez5.address", "")).upper() == address.upper()
                or str(props.get("node.name", "")).upper().startswith(
                    "BLUEZ_OUTPUT." + token + ".")):
            return obj["id"]
    return None


def select_audio(address, volume):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        node = find_sink(json.loads(command("pw-dump")), address)
        if node is not None:
            command("wpctl", "set-default", str(node))
            command("wpctl", "set-mute", str(node), "0")
            command("wpctl", "set-volume", str(node), f"{volume}%")
            return
        time.sleep(0.5)
    raise RuntimeError(
        "Bluetooth connected, but no PipeWire playback sink appeared. "
        "Check wpctl status and systemctl --user status wireplumber. "
        "See bluetooth_speakers.md for headless session setup.")


class Bluetooth:
    def __init__(self, adapter=None):
        try:
            import dbus
            import dbus.service
            from dbus.mainloop.glib import DBusGMainLoop
            from gi.repository import GLib
        except ImportError as exc:
            raise RuntimeError("Install python3-dbus python3-gi; use /usr/bin/python3.") from exc
        DBusGMainLoop(set_as_default=True)
        self.dbus, self.glib = dbus, GLib
        self.bus = dbus.SystemBus()
        self.manager = dbus.Interface(self.bus.get_object("org.bluez", "/"),
                                      "org.freedesktop.DBus.ObjectManager")
        adapters = sorted(str(path) for path, interfaces in self.objects().items()
                          if ADAPTER in interfaces)
        if adapter:
            adapters = [p for p in adapters if p.rsplit("/", 1)[-1] == adapter]
        if not adapters:
            raise RuntimeError("No Bluetooth adapter found. Check bluetooth service and rfkill.")
        self.path = adapters[0]
        self.adapter = self.interface(self.path, ADAPTER)
        self.target = None
        owner = self

        class Agent(dbus.service.Object):
            def check(self, device):
                if str(device) != owner.target:
                    raise dbus.exceptions.DBusException(
                        "Only the selected speaker is authorized",
                        name="org.bluez.Error.Rejected")

            @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
            def Release(self):
                pass

            @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
            def RequestAuthorization(self, device):
                self.check(device)

            @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
            def RequestConfirmation(self, device, passkey):
                self.check(device)

            @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
            def AuthorizeService(self, device, uuid):
                self.check(device)

            @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
            def Cancel(self):
                pass

        self.agent_path = "/speaker_picker/agent"
        self.agent = Agent(self.bus, self.agent_path)
        self.agent_manager = self.interface("/org/bluez", "org.bluez.AgentManager1")
        # App-specific agent: do not replace another application's default agent.
        self.agent_manager.RegisterAgent(self.agent_path, "NoInputNoOutput")

    def interface(self, path, interface):
        return self.dbus.Interface(self.bus.get_object("org.bluez", path), interface)

    def objects(self):
        return self.manager.GetManagedObjects()

    def wait(self, seconds):
        loop = self.glib.MainLoop()
        timer = self.glib.timeout_add(int(seconds * 1000), lambda: (loop.quit(), False)[1])
        try:
            loop.run()
        finally:
            context = self.glib.MainContext.default()
            if context.find_source_by_id(timer):
                self.glib.source_remove(timer)

    def scan(self, seconds):
        self.interface(self.path, PROPERTIES).Set(ADAPTER, "Powered", self.dbus.Boolean(True))
        # Discovery belongs to this D-Bus client; StopDiscovery releases only our session.
        self.adapter.SetDiscoveryFilter({"Transport": self.dbus.String("bredr")})
        self.adapter.StartDiscovery()
        try:
            self.wait(seconds)
            speakers = []
            for path, interfaces in self.objects().items():
                props = interfaces.get(DEVICE, {})
                if str(props.get("Adapter")) == self.path and speaker_candidate(props):
                    speakers.append({"path": str(path), "address": str(props["Address"]),
                                     "name": str(props.get("Alias", props.get("Name", props["Address"]))),
                                     "paired": bool(props.get("Paired")),
                                     "connected": bool(props.get("Connected"))})
            return sorted(speakers, key=lambda s: (s["name"].casefold(), s["address"]))
        finally:
            self.adapter.StopDiscovery()

    def call_async(self, method):
        # Keep the GLib loop running so BlueZ can call the pairing agent.
        loop = self.glib.MainLoop()
        errors = []

        def done(*unused):
            loop.quit()

        def failed(error):
            errors.append(error)
            loop.quit()

        method(reply_handler=done, error_handler=failed, timeout=65)
        loop.run()
        if errors:
            raise RuntimeError(str(errors[0]))

    def device_path(self, address):
        return self.path + "/dev_" + address.replace(":", "_")

    def connect(self, address):
        path = self.device_path(address)
        device = self.interface(path, DEVICE)
        props = self.interface(path, PROPERTIES)
        self.target = path
        try:
            if not props.Get(DEVICE, "Paired"):
                try:
                    self.call_async(device.Pair)
                except BaseException:
                    try:
                        device.CancelPairing()
                    except self.dbus.DBusException:
                        pass
                    raise
            props.Set(DEVICE, "Trusted", self.dbus.Boolean(True))
            if not props.Get(DEVICE, "Connected"):
                self.call_async(device.Connect)
        finally:
            self.target = None

    def forget(self, address):
        self.adapter.RemoveDevice(self.device_path(address))

    def close(self):
        try:
            self.agent_manager.UnregisterAgent(self.agent_path)
        finally:
            self.agent.remove_from_connection()


# Compact 3x5 font: scrolling is frame-based so joystick input stays responsive.
FONT = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-?:. ", [
    "010/101/111/101/101", "110/101/110/101/110", "011/100/100/100/011",
    "110/101/101/101/110", "111/100/110/100/111", "111/100/110/100/100",
    "011/100/101/101/011", "101/101/111/101/101", "111/010/010/010/111",
    "001/001/001/101/010", "101/101/110/101/101", "100/100/100/100/111",
    "101/111/111/101/101", "101/111/111/111/101", "010/101/101/101/010",
    "110/101/110/100/100", "010/101/101/111/011", "110/101/110/101/101",
    "011/100/010/001/110", "111/010/010/010/010", "101/101/101/101/111",
    "101/101/101/101/010", "101/101/111/111/101", "101/101/010/101/101",
    "101/101/010/010/010", "111/001/010/100/111",
    "111/101/101/101/111", "010/110/010/010/111", "110/001/010/100/111",
    "110/001/010/001/110", "101/101/111/001/001", "111/100/110/001/110",
    "011/100/111/101/111", "111/001/010/010/010", "111/101/111/101/111",
    "111/101/111/001/110", "000/000/111/000/000", "110/001/010/000/010",
    "000/010/000/010/000", "000/000/000/000/010", "000/000/000/000/000",
]))


def columns(text):
    result = [[0] * 5 for _ in range(8)]
    for char in text.upper():
        rows = FONT.get(char, FONT["?"]).split("/")
        result.extend([[int(rows[y][x]) for y in range(5)] for x in range(3)])
        result.append([0] * 5)
    return result + [[0] * 5 for _ in range(8)]


def pick(sense, labels, colour=(0, 100, 180), timeout=None):
    """Return selected index, or None after timeout; middle selects, up/down wrap."""
    selected, offset = 0, 0
    strip = columns(labels[selected])
    print(labels[selected], flush=True)
    started = time.monotonic()
    next_frame = 0
    sense.stick.get_events()  # Discard presses made during scan/connect.
    while timeout is None or time.monotonic() - started < timeout:
        for event in sense.stick.get_events():
            if event.action != "pressed":
                continue
            if event.direction == "middle":
                return selected
            if event.direction in ("up", "down"):
                selected = (selected + (1 if event.direction == "down" else -1)) % len(labels)
                strip, offset = columns(labels[selected]), 0
                next_frame = 0
                print(labels[selected], flush=True)
        now = time.monotonic()
        if now >= next_frame:
            pixels = [(0, 0, 0)] * 64
            for x in range(8):
                for y in range(5):
                    if strip[offset + x][y]:
                        pixels[(y + 1) * 8 + x] = colour
            sense.set_pixels(pixels)
            offset = (offset + 1) % (len(strip) - 7)
            next_frame = now + 0.08
        time.sleep(0.02)
    return None


def speaker_labels(speakers):
    # Include address suffix to distinguish identical advertised names.
    return [f"{i}. {s['name']} {s['address'][-5:]}" for i, s in enumerate(speakers, 1)]


def address_arg(value):
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", value):
        raise argparse.ArgumentTypeError("Expected a Bluetooth address: AA:BB:CC:DD:EE:FF")
    return value.upper()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="Scan/list candidates without Sense HAT")
    mode.add_argument("--connect", type=address_arg, metavar="MAC", help="Connect without Sense HAT")
    mode.add_argument("--forget", type=address_arg, metavar="MAC", help="Remove stored pairing")
    parser.add_argument("--scan-seconds", type=int, default=15)
    parser.add_argument("--adapter", help="Bluetooth adapter name, e.g. hci0")
    parser.add_argument("--volume", type=int, default=40, help="Playback volume 0-100 (default 40)")
    parser.add_argument("--play", type=Path, metavar="WAV", help="Play a WAV after connecting")
    parser.add_argument("--rotation", type=int, choices=(0, 90, 180, 270), default=0)
    args = parser.parse_args()
    if args.scan_seconds < 1 or not 0 <= args.volume <= 100:
        parser.error("scan-seconds must be positive and volume must be 0-100")
    if args.play and (args.list or args.forget):
        parser.error("--play requires connection mode")
    if args.play and not args.play.is_file():
        parser.error(f"Test file does not exist: {args.play}")
    for executable in (() if args.list or args.forget else ("pw-dump", "wpctl")):
        if not shutil.which(executable):
            parser.error(f"Missing {executable}; install pipewire-audio pipewire-bin wireplumber")
    if args.play and not shutil.which("pw-play"):
        parser.error("Missing pw-play; install pipewire-bin")
    bluetooth, sense = None, None
    try:
        if not (args.list or args.connect or args.forget):
            from sense_hat import SenseHat
            sense = SenseHat()
            sense.set_rotation(args.rotation)
            sense.low_light = True
        bluetooth = Bluetooth(args.adapter)
        if args.forget:
            bluetooth.forget(args.forget)
            print(f"Forgot {args.forget}")
            return 0

        def connect(address):
            bluetooth.connect(address)
            select_audio(address, args.volume)
            print(f"Connected and selected audio output: {address}", flush=True)
            if args.play:
                subprocess.run(["pw-play", str(args.play.resolve())], check=True)

        if args.connect:
            # Discover the device first; BlueZ must know its object before pairing.
            bluetooth.scan(args.scan_seconds)
            connect(args.connect)
            return 0
        while True:
            print("Scanning; put your speaker in pairing mode...", flush=True)
            if sense:
                sense.show_letter("S", text_colour=[0, 80, 180])
            speakers = bluetooth.scan(args.scan_seconds)
            for index, speaker in enumerate(speakers, 1):
                state = "connected" if speaker["connected"] else "paired" if speaker["paired"] else "new"
                print(f"{index}. {speaker['name']}  {speaker['address']}  [{state}]")
            if not speakers:
                print("No speaker candidates found. Try pairing mode and scan again.")
            if args.list:
                return 0
            selected = pick(sense, speaker_labels(speakers) + ["RESCAN", "QUIT"])
            if selected == len(speakers) + 1:
                return 0
            if selected == len(speakers):
                continue
            speaker = speakers[selected]
            sense.show_letter("C", text_colour=[180, 100, 0])
            try:
                connect(speaker["address"])
            except Exception as exc:
                print(f"Connection/playback failed: {exc}", file=sys.stderr, flush=True)
                pick(sense, ["ERROR - MIDDLE TO RETRY"], colour=(180, 0, 0), timeout=5)
            else:
                pick(sense, ["CONNECTED " + speaker["name"]], colour=(0, 160, 0), timeout=4)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if sense:
            sense.clear()
        if bluetooth:
            bluetooth.close()


if __name__ == "__main__":
    sys.exit(main())
