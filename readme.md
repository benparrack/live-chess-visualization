# Live chess visualization

Display Lichess games as an 8×8 grid of colored LEDs. You can run the included desktop simulator without a Raspberry Pi or Sense HAT.

## Quick start on macOS

You need Python 3 with Tkinter and a desktop session. The simulation uses only Python's standard library; no `pip install`, Sense HAT drivers, API key, or virtual environment is required.

First check whether Python is already installed:

```sh
command -v python3
python3 --version
```

For example, `/opt/homebrew/bin/python3` reporting `Python 3.14.7` is an existing Homebrew Python installation. Use it for the commands below. A `python` alias pointing to `python3` is fine; these instructions explicitly use `python3`.

Check whether that interpreter already has Tkinter:

```sh
python3 -m tkinter
```

If a small test window opens, close it and continue to the replay command below. No installation is needed.

If this fails with `No module named 'tkinter'` or `'_tkinter'`, install the matching Tkinter package. For Homebrew Python 3.14.x:

```sh
brew install python-tk@3.14
python3 -m tkinter
```

Match the package's major/minor version to `python3 --version` (for example, `python-tk@3.13` for Python 3.13.x). Homebrew may also update Python to a compatible patch release while installing the package.

Only if `python3` is missing, install Python and Tkinter together:

```sh
brew install python@3.14 python-tk@3.14
python3 -m tkinter
```

From the repository root, start with the bundled offline replay:

```sh
cd chessproj
python3 pisim.py colorchess.py capture.ndjson
```

An 8×8 LED window opens and plays the saved games repeatedly. This mode needs no internet connection. Close the window to stop the simulator and its child process.

See the [Python Tkinter documentation](https://docs.python.org/3/library/tkinter.html) and [Homebrew Python setup](https://formulae.brew.sh/formula/python%403.14).

## Watch live games

From `chessproj/`, omit the capture filename:

```sh
python3 pisim.py colorchess.py
```

This streams Lichess TV over the internet, starting with the bullet channel. Connection errors appear in the terminal, and the program retries automatically.

## Controls

Focus the simulator window to use the keyboard:

| Key | Action |
| --- | --- |
| Left / Right | Cycle live TV channels: featured, bullet, blitz, rapid |
| Up / Down | Increase / decrease brightness |
| Enter | Clear the LEDs and ask the chess program to quit |
| r | Restart the program |
| Close window | Stop the simulator and the chess program |

Channel changes apply to live mode. Changes and quitting can wait for the next stream event or timeout; closing the window stops the child directly. Brightness changes appear on the next rendered frame.

Saving a top-level `.py` file in `chessproj/` or editing `chessproj/sim/sense_hat.py` automatically restarts the program.

## Other previews

Run these from `chessproj/`:

```sh
# Starting chess position, displayed for 20 seconds
python3 pisim.py colortest.py

# Piece-color legend, displayed for 30 seconds
python3 pisim.py legend.py

# Alternative visualization using side colors and piece brightness
python3 pisim.py lichess.py capture.ndjson
```

When a preview finishes, the viewer stays open; press `r` to run it again.

## How the simulation works

`pisim.py` opens the Tkinter window and launches the chosen script with `sim/` on its Python import path. This substitutes the bundled `sim/sense_hat.py` for the real hardware module and passes LED frames and joystick events between the processes.

Launch through `pisim.py`: running `colorchess.py` directly expects the real `sense_hat` module. The simulator displays LEDs and joystick input; hardware rotation is ignored.

## Troubleshooting

- **`No module named 'tkinter'` or `'_tkinter'`:** install Tkinter for the Python interpreter you are using. For the Homebrew setup above, use `brew install python-tk@3.14` and launch with `python3`. Tkinter is not installed through `pip`.
- **`No module named 'sense_hat'`:** use `python3 pisim.py colorchess.py capture.ndjson` so the simulator supplies the hardware replacement.
- **No display / `$DISPLAY` error:** run from a graphical desktop session. The viewer needs a windowing environment.
- **Live mode stays blank or reports stream errors:** try the offline replay first to check the simulator independently of the network.
- **Windows:** the current launcher uses POSIX file descriptors (`pass_fds`) and targets macOS/Linux. On Windows, use a Linux desktop environment with GUI support or adapt the launcher.

## Bluetooth speakers on the Pi

Use the standalone [Sense HAT Bluetooth speaker picker](bluetooth_speakers.md) to scan, select, pair, connect, and test a speaker using the LED matrix and joystick. Run it separately from the chess display.
