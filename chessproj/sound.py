"""
Game sounds for the chess panel, played through whatever the system's default
audio output is -- on the Pi that can be a Bluetooth speaker.

The tones are synthesised here with the standard library and cached as WAV
files, so there are no sound files to ship. Playback runs in the background,
so a sound never holds up the LEDs.

Bluetooth speaker setup on the Pi (once):
    bluetoothctl
        power on
        scan on            # wait for the speaker's address to show up
        pair XX:XX:XX:XX:XX:XX
        trust XX:XX:XX:XX:XX:XX
        connect XX:XX:XX:XX:XX:XX
    Raspberry Pi OS then makes the speaker the default output; test it with
    `paplay /usr/share/sounds/alsa/Front_Center.wav`. Run the panel as your
    normal user, not with sudo, or it can't reach your audio session.
"""

import math
import os
import random
import shutil
import struct
import subprocess
import tempfile
import wave

SOUND = True        # set False to silence the panel
VOLUME = 0.5        # 0..1, on top of the speaker's own volume
RATE = 22050

# First player found wins: PulseAudio/PipeWire tools follow the Bluetooth
# speaker when it's the default output; aplay is the plain-ALSA fallback.
PLAYER = next((p for p in ("paplay", "pw-play", "aplay") if shutil.which(p)), None)
CACHE = os.path.join(tempfile.gettempdir(), "chess-panel-sounds")
_written = set()   # rewritten once per run, so edits to SOUNDS/VOLUME take effect


def tone(freq, seconds, decay=6.0, noise=0.0):
    """A sine tone with a fast attack and exponential fade, optionally gritty."""
    n = int(RATE * seconds)
    return [(math.sin(2 * math.pi * freq * i / RATE) * (1 - noise) + random.uniform(-1, 1) * noise)
            * min(1.0, i / 60) * math.exp(-decay * i / n)
            for i in range(n)]


def notes(*parts, gap=0.02):
    """Join (freq, seconds) notes with short silences in between."""
    out = []
    for freq, seconds in parts:
        out += tone(freq, seconds, decay=3.0) + [0.0] * int(RATE * gap)
    return out


# Short sounds for frequent events, longer and more musical for rare ones.
SOUNDS = {
    "move":    lambda: tone(520, 0.07, decay=9),                      # soft tock
    "capture": lambda: tone(180, 0.16, decay=7, noise=0.35),          # gritty thud
    "castle":  lambda: tone(520, 0.07, decay=9) + [0.0] * 1500 + tone(440, 0.07, decay=9),
    "check":   lambda: notes((988, 0.08), (988, 0.08)),               # two sharp beeps
    "promote": lambda: notes((523, 0.06), (659, 0.06), (784, 0.06), (1047, 0.14)),
    "start":   lambda: notes((392, 0.1), (523, 0.1), (659, 0.18)),
    "mate":    lambda: notes((523, 0.12), (659, 0.12), (784, 0.12), (1047, 0.45)),
    "win":     lambda: notes((659, 0.14), (784, 0.3)),                # resign / timeout
    "draw":    lambda: notes((523, 0.2), (523, 0.3)),
    "offline": lambda: notes((330, 0.15), (220, 0.3)),
}


def _path(name):
    path = os.path.join(CACHE, name + ".wav")
    if name not in _written:
        os.makedirs(CACHE, exist_ok=True)
        samples = SOUNDS[name]()
        frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * VOLUME * 32767)) for s in samples)
        tmp = path + ".tmp"
        with wave.open(tmp, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(frames)
        os.replace(tmp, path)   # never leave a half-written file to play
        _written.add(name)
    return path


def play(name):
    """Start a sound in the background. Never raises: sound is a nice-to-have."""
    if not SOUND or not PLAYER:
        return
    try:
        subprocess.Popen([PLAYER, _path(name)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
