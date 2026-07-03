# YouTube Playlist Media Player

Plays YouTube playlists automatically using yt-dlp and mpv.
Config is stored on GitHub so you can update your playlists from anywhere.

---

## Setup (Windows — for testing)

### 1. Install Python
Download from https://python.org — tick **"Add Python to PATH"** during install.

### 2. Install yt-dlp
```
pip install yt-dlp
```

### 3. Install mpv
- Download the Windows build from https://mpv.io/installation/
- Extract to somewhere like `C:\mpv\`
- Add `C:\mpv\` to your system PATH:
  - Search "Environment Variables" in the Start menu
  - Edit the `Path` variable and add `C:\mpv\`

### 4. Set up your GitHub config

1. Create a new GitHub repository (can be public or private)
2. Upload `playlists.json` to the repo
3. Open the file on GitHub, click **Raw**, and copy the URL
   - It will look like: `https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/playlists.json`
4. Open `player.py` and paste that URL into the `CONFIG_URL` variable at the top

### 5. Edit your playlists
Open `playlists.json` and replace the placeholder URLs with real YouTube playlist URLs.
Commit and push — changes take effect next time the player finishes a cycle.

### 6. Run it
```
python player.py
```

---

## Setup (Raspberry Pi)

### 1. Install dependencies
```bash
sudo apt update && sudo apt install mpv python3 python3-pip -y
pip3 install yt-dlp
```

### 2. Copy player.py to the Pi
Use SCP, a USB drive, or just clone your GitHub repo.

### 3. Run on boot with systemd

Create the service file:
```bash
sudo nano /etc/systemd/system/mediaplayer.service
```

Paste:
```ini
[Unit]
Description=YouTube Playlist Media Player
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/player.py
WorkingDirectory=/home/pi
Restart=always
RestartSec=10
User=pi
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable mediaplayer
sudo systemctl start mediaplayer
```

Check logs:
```bash
sudo journalctl -u mediaplayer -f
```

---

## Updating playlists
Just edit `playlists.json` on GitHub and commit. The player re-fetches it after every full cycle.

## Files
- `player.py` — main player script
- `playlists.json` — your playlist config (lives on GitHub)
- `player.log` — local log file (created automatically when player runs)
