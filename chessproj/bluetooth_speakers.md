# Bluetooth audio-output picker for Raspberry Pi + Sense HAT

`bluetooth_speakers.py` can run on its own, as described below, or from the chess menu: in `menu.py` (same folder), clicking the joystick in opens the same speaker list on the panel. When running it on its own, stop the chess LED program first so both processes do not write the display. The Mac simulator does not simulate Bluetooth.

## One-time setup on the Pi

For Raspberry Pi OS Bookworm or newer, using PipeWire:

```sh
sudo apt update
sudo apt install bluez pipewire-audio pipewire-bin wireplumber python3-dbus python3-gi sense-hat
sudo systemctl enable --now bluetooth
sudo rfkill unblock bluetooth
systemctl --user enable --now pipewire pipewire-pulse wireplumber
```

Run the script as your ordinary Pi login user, **without sudo**, using `/usr/bin/python3` so the apt-installed Python modules are available. The script powers the selected Bluetooth adapter on, but does not install packages, change service configuration, unblock rfkill, or change system permissions itself. BlueZ must allow this user to control the adapter, as it does for working `bluetoothctl` commands. If you just installed the Sense HAT drivers, reboot before the first run.

## Select using the joystick

Put your speaker in pairing mode and disconnect it from phones/laptops that automatically reconnect. From `chessproj/`:

```sh
/usr/bin/python3 bluetooth_speakers.py
# Optional WAV playback immediately after a successful connection:
/usr/bin/python3 bluetooth_speakers.py --play ~/speaker-test.wav
```

The LEDs show `S` during the default 15-second scan. The menu scrolls each speaker's name, its index, and the last two address bytes to distinguish duplicate names. Names also appear in the terminal.

- **Up / down:** previous / next entry, wrapping at either end.
- **Middle:** pair (if necessary), trust, connect, and select that speaker as the PipeWire default output. Unmute it and set its volume to 40% (override with `--volume 25`).
- **RESCAN:** scan again, useful after re-enabling a speaker's pairing mode.
- **QUIT:** clear the LEDs and exit; the speaker stays connected.
- **Ctrl+C:** stop the program and clear the LEDs.

The LEDs show amber `C` while connecting, green `CONNECTED` on success, and red `ERROR` on failure. Detailed errors appear in the terminal. Connection/pairing can take up to 65 seconds per operation; joystick input resumes when the operation finishes. The scrolling menu remains responsive to the joystick. The optional test file plays to completion; Ctrl+C stops playback and exits. After connection/playback the menu scans again so you can select another speaker or quit.

`--rotation 90` rotates the displayed text (also accepts 0, 180, 270); physical joystick directions retain the Sense HAT's original orientation. `--scan-seconds 25` scans longer, and `--adapter hci1` selects a different Bluetooth adapter.

## Audio-output filtering

Discovery uses Classic Bluetooth for A2DP audio. It lists devices advertising the Audio Sink service or a recognized audio-output class/icon, including speakers, headphones, headsets, and portable/car/hi-fi audio receivers. It does not guess from names; phones, keyboards, and microphone-only devices are excluded unless they also advertise an audio-output service. LE Audio-only devices are not supported.

The list includes cached paired speakers, which can be offline; connecting to an unavailable speaker reports an error. Some new speakers advertise their audio service only after pairing: if absent, pair them with `bluetoothctl` once and rescan. PIN/passkey-entry speakers should also be paired manually first; the script's app-specific pairing agent handles ordinary no-keyboard speaker pairing and only authorizes the speaker you selected. Existing pairings are preserved when reconnecting.

## Terminal options

No Sense HAT is required for these modes:

```sh
/usr/bin/python3 bluetooth_speakers.py --list
/usr/bin/python3 bluetooth_speakers.py --connect AA:BB:CC:DD:EE:FF
/usr/bin/python3 bluetooth_speakers.py --connect AA:BB:CC:DD:EE:FF --play ~/speaker-test.wav
/usr/bin/python3 bluetooth_speakers.py --forget AA:BB:CC:DD:EE:FF
/usr/bin/python3 bluetooth_speakers.py --help
```

`--connect` accepts an explicit address, including a device excluded by the menu's filtering. It scans first so BlueZ knows the device before attempting pairing.

To manually forget a speaker:

```sh
bluetoothctl devices
bluetoothctl remove AA:BB:CC:DD:EE:FF
```

Or, inside interactive `bluetoothctl`, enter `remove AA:BB:CC:DD:EE:FF`. Removing disconnects the device and deletes the Pi's stored pairing. To reconnect afterwards, put the speaker in pairing mode and pair again; some speakers also need their saved Pi pairing cleared.

## Transfer and play a test WAV

On your laptop (replace the username/address):

```sh
scp "/path/to/example.wav" YOUR_PI_USER@raspberrypi.local:~/speaker-test.wav
```

On the Pi:

```sh
/usr/bin/python3 bluetooth_speakers.py --play ~/speaker-test.wav
# Or, after selecting the speaker, play independently:
pw-play ~/speaker-test.wav
```

## Troubleshooting headless audio

If Bluetooth connects but audio output cannot be selected, check:

```sh
wpctl status
systemctl --user status pipewire pipewire-pulse wireplumber --no-pager
wireplumber --version
```

Run all audio commands as the same user as the script. The script matches the chosen Bluetooth address to its PipeWire playback node; it will report an error rather than accidentally selecting HDMI or another speaker.

On a dedicated headless Pi, WirePlumber's active-seat restriction can hide Bluetooth audio from an SSH user's audio session. For **WirePlumber 0.5 or newer**, create `~/.config/wireplumber/wireplumber.conf.d/51-headless-bluetooth.conf` with:

```ini
wireplumber.profiles = {
  main = {
    monitor.bluez.seat-monitoring = disabled
  }
}
```

Then run `systemctl --user restart wireplumber` and reconnect. This configuration syntax does **not** apply to WirePlumber 0.4 (commonly installed on Bookworm); consult the documentation for that installed version. Avoid running competing audio sessions under different users. To keep the user's services running after SSH logout, a dedicated Pi can use `sudo loginctl enable-linger "$USER"`.

## Local validation without hardware

From `chessproj/`:

```sh
python3 -B -m unittest -v test_bluetooth_speakers.py
```

These checks cover device filtering, matching the exact audio sink, pairing/reconnection, failed pairing cleanup, and joystick navigation using fakes. Real Bluetooth pairing, sound, and the LED matrix require validation on the Pi.

References: [BlueZ device API](https://bluez.readthedocs.io/en/latest/device-api/), [Sense HAT API](https://sense-hat.readthedocs.io/en/latest/api/), [WirePlumber Bluetooth configuration](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/bluetooth.html).
