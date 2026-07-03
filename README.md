# Marthakal Media Player

A Raspberry Pi media player that automatically plays videos from YouTube playlists, fullscreen, on boot. Playlists are managed from a simple JSON file in this repo — edit it from anywhere and the Pi picks up changes automatically.

---

## How it works

```
Pi powers on
  → auto-logs in
    → Wi-Fi connects
      → mediaplayer service starts
        → player.py fetches playlists.json from GitHub
          → videos play fullscreen (via yt-dlp + mpv)
            → after the last video, it re-fetches the config and loops
```

- **Streaming, not downloading** — videos stream directly from YouTube, nothing is saved to disk.
- **Fullscreen with no desktop** — uses mpv's DRM output to render straight to the screen, so it runs on the lightweight Pi OS Lite.
- **Self-updating playlists** — edit `playlists.json` on GitHub and the Pi picks it up after the current cycle finishes.
- **Crash-proof** — if the player stops for any reason, systemd restarts it automatically.

---

## Files

| File | Purpose |
|------|---------|
| `player.py` | The main player script (runs on the Pi) |
| `playlists.json` | Your playlist configuration — **this is the file you edit** |
| `setup.sh` | One-click installer for the Pi |

---

## Configuring playlists

Edit `playlists.json`:

```json
{
  "playlists": [
    "https://www.youtube.com/playlist?list=YOUR_PLAYLIST_ID",
    "https://www.youtube.com/playlist?list=ANOTHER_PLAYLIST_ID"
  ],
  "shuffle": false,
  "refresh_interval_hours": 6
}
```

- **`playlists`** — a list of YouTube playlist URLs. They play in order, top to bottom.
- **`shuffle`** — reserved for future use (currently plays in order).
- **`refresh_interval_hours`** — reserved for future use (currently refreshes after each full cycle).

Commit your changes and the Pi will pick them up the next time it finishes playing through all videos.

---

## Setup

### Part 1 — On your computer

1. **Install Raspberry Pi Imager** from https://www.raspberrypi.com/software/

2. **Flash the SD card:**
   - Choose **Raspberry Pi OS Lite (64-bit)**
   - Click the **gear icon** (⚙️) for advanced settings and set:
     - **Hostname:** `marthakalmedia001`
     - **Username:** `marthakalmedia001` (and a password you'll remember)
     - **Wi-Fi:** your network name and password
     - **Enable SSH:** yes, use password authentication
   - Write the card

3. **Connect the hardware:**
   - Plug the HDMI cable into your TV/display **first** (before powering on — the Pi needs the display connected at boot to initialise video output)
   - Insert the SD card
   - Power on the Pi

### Part 2 — On the Pi (via SSH)

1. **Connect to the Pi** from your computer's terminal (PowerShell, Command Prompt, or Terminal):
   ```bash
   ssh marthakalmedia001@marthakalmedia001.local
   ```
   (Enter the password you set in the Imager.)

2. **Run the one-click installer:**
   ```bash
   curl -sSL https://raw.githubusercontent.com/BARKcommunications/marthakal_media_player/main/setup.sh | bash
   ```

That's it. The script installs everything, configures auto-start, and reboots. After the reboot, videos play automatically.

---

## What the installer does

The `setup.sh` script:

1. Auto-detects your username (works with any username)
2. Installs `mpv`, `python3`, `pip`, and video drivers via `apt`
3. Installs `yt-dlp` via `pip`
4. Configures the Pi to auto-login on boot (skips the password prompt)
5. Downloads `player.py` from this repo
6. Creates a `systemd` service so the player starts on every boot and restarts if it crashes
7. Verifies everything installed correctly
8. Reboots

---

## Adding a second Wi-Fi network (optional)

Useful if the Pi moves between locations. SSH into the Pi and run:

```bash
sudo nmcli connection add type wifi con-name "Network2" ssid "SECOND_WIFI_NAME"
sudo nmcli connection modify "Network2" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "SECOND_WIFI_PASSWORD"
```

The Pi will connect to whichever saved network is available at boot. To prefer one network over another:

```bash
sudo nmcli connection modify "Network2" connection.autoconnect-priority 10
```

Higher number = higher priority.

> **Note:** Wi-Fi credentials are entered directly on the Pi and never stored in this public repo.

---

## Managing the player

SSH into the Pi and use these commands:

```bash
sudo journalctl -u mediaplayer -f    # Watch live logs
sudo systemctl stop mediaplayer      # Stop playback
sudo systemctl start mediaplayer     # Start playback
sudo systemctl restart mediaplayer   # Restart playback
sudo systemctl status mediaplayer    # Check if it's running
```

---

## Updating the player script

Changes to `playlists.json` are picked up automatically. But if you update `player.py` itself, the Pi needs to re-download it. SSH in and run:

```bash
curl -sSL https://raw.githubusercontent.com/BARKcommunications/marthakal_media_player/main/player.py -o ~/player.py
sudo systemctl restart mediaplayer
```

---

## Troubleshooting

**Nothing appears on screen**
- Make sure the HDMI cable was connected *before* the Pi powered on. Reboot with it plugged in.
- Check the service is running: `sudo systemctl status mediaplayer`

**Videos won't load / "no videos found"**
- Check the Pi has internet: `ping youtube.com`
- Check your playlist is public or unlisted (private playlists won't work)
- View logs for detail: `sudo journalctl -u mediaplayer -f`

**A video is skipped**
- The player retries a failed video 3 times, then moves on. Check the logs to see which one and why (often a deleted or region-locked video).

**yt-dlp errors after YouTube changes**
- YouTube occasionally changes things that break yt-dlp. Update it: `pip3 install --break-system-packages --upgrade yt-dlp` then `sudo systemctl restart mediaplayer`.

---

## Testing on Windows (optional)

Before deploying to the Pi, you can test your playlists on a Windows PC:

1. Install Python from https://python.org (tick "Add to PATH")
2. Install yt-dlp: `pip install yt-dlp`
3. Install mpv from https://mpv.io and add it to PATH
4. Verify a playlist loads:
   ```
   yt-dlp --flat-playlist --print url "https://www.youtube.com/playlist?list=YOUR_PLAYLIST_ID"
   ```

> Note: `player.py` is configured to run on the Pi (Linux) only. Use the command above to verify playlists on Windows; the Pi handles actual playback.
