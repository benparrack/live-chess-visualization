# Running the project on the Pi

**Pi details:** hostname `ryanpi` · username `pi` · password: ask Ryan

## 1. Connect

1. Turn on your phone hotspot. On an iPhone, turn on **Maximize Compatibility**. The Pi must already have your hotspot saved. If it doesn't, plug in a screen and keyboard and run `sudo nmtui` to add it.
2. Connect your laptop to the same hotspot.
3. SSH in:

```
ssh pi@ryanpi.local
```

If that fails, get the Pi's IP with `hostname -I` and run `ssh pi@<IP>` instead.

## 2. First-time setup

```
sudo apt update
sudo apt install -y git sense-hat python3-pip
pip install chess --break-system-packages
git clone https://github.com/benparrack/live-chess-visualization.git
```

## 3. Run

**Openings explorer (`ryan` branch):**

```
cd ~/live-chess-visualization
git checkout ryan && git pull
cd chessproj
python3 openings_server.py
```

Then open **http://ryanpi.local:8000** on a device connected to the same hotspot.

**Live Lichess games (`main` branch):**

```
cd ~/live-chess-visualization
git checkout main && git pull
cd chessproj
python3 colorchess.py
```

## 4. Stop and shut down

- Stop the program: **Ctrl+C**
- Shut down before unplugging: `sudo halt`

## Common fixes

- **Can't find `ryanpi.local`:** Make sure the Pi and your laptop are on the same hotspot, or use the IP address instead.
- **`No module named 'chess'`:** Run `pip install chess --break-system-packages`.
- **`.git/objects ... is empty`:** The repo got corrupted. Delete the folder with `rm -rf ~/live-chess-visualization`, then clone it again.
- **Board is upside down:** Change `ROTATION = 180` to `0` near the top of the script.
