# Marthakal Media Player

Raspberry Pi digital signage that plays YouTube playlists and images fullscreen on
boot, on a schedule. Content is managed in a visual scheduler that publishes straight
to this repo — **hit Publish and the sign updates itself within ~2 minutes.**

No SSH needed for day-to-day use. Each sign reads its own schedule based on its
hostname, so adding a screen is just: flash a Pi, publish a schedule.

---

## How it works

```
Pi powers on
  → network connects
    → mediaplayer service starts, mpv takes the screen (splash shows)
      → player.py reads devices/<hostname>/playlists.json
        → picks the block scheduled for right now (or the default)
          → plays those items fullscreen, then loops
  ↺ every 2 min: pulls repo changes    ↺ daily: refreshes yt-dlp
```

- **Per-device schedules** — each Pi reads its own config, keyed by hostname.
- **Scheduled** — different content by day of week and time of day, with shuffle.
- **Videos and images** — mix YouTube playlists, single videos, and still images.
- **Self-updating** — pulls playlists and code from this repo automatically.
- **Self-healing** — refreshes yt-dlp daily, so YouTube changes don't kill the sign.
- **Fullscreen, no desktop** — one persistent mpv instance owns the screen, so the
  terminal never shows. A splash image covers gaps between items.
- **Crash-proof** — systemd restarts the player if it ever stops.

---

## Files

| File | Purpose |
|------|---------|
| `scheduler.html` | The visual editor. Open in a browser; publishes to this repo. |
| `devices/<hostname>/playlists.json` | Each sign's own schedule (created by publishing) |
| `playlists.json` | Shared fallback, used by any Pi without its own device folder |
| `player.py` | The player that runs on the Pi |
| `splash.png` | Shown between items while the next one loads |
| `images/` | Images uploaded via the scheduler |
| `setup.sh` | One-command installer for a new Pi |
| `update.sh` | Auto-updater (pulls repo, refreshes yt-dlp) — run by a timer on the Pi |

---

## Using the scheduler

Open **`scheduler.html`** in any browser (double-click it — no server needed). It loads
the sign's current live schedule automatically.

1. **Pick the device** — the `Device` box in the header (`001`, `002`, …). It loads that
   sign's schedule. A brand-new number starts from the shared default.
2. **Add schedule blocks** — name, days, start/end time, and the items to play.
   Blocks are checked top to bottom; **the first one matching the current day and time
   wins**, so don't overlap days/times between blocks unless you mean to.
3. **Add items** — *+ Add item* for a YouTube playlist or single video URL.
   *+ Add image* to upload an image (it's committed to the repo automatically); set how
   many seconds it stays on screen.
4. **Shuffle** — the *⤨ Shuffle* toggle on any block plays its items in a random order,
   re-shuffled each loop. Off by default.
5. **Set the default** — plays whenever no block matches (e.g. overnight).
6. **Max quality** — leave at **720p**. See the warning below.
7. Click **Publish to Pi**. The sign updates within ~2 minutes.

> **Quality warning:** 1080p causes stuttering and dropped videos on a Pi 4 — YouTube
> serves VP9 at that resolution, which the Pi can't decode in hardware. **Use 720p.**

### First-time setup (once per browser)

Click **⚙ Settings** and enter a **GitHub token**. Create it at GitHub → Settings →
Developer settings → Personal access tokens → **Fine-grained tokens**:

- **Repository access:** Only select repositories → this repo
- **Permissions:** Repository permissions → **Contents: Read and write** (nothing else)

The token is stored only in that browser. Note its expiry date and renew before it lapses.

---

## playlists.json format

```json
{
  "max_height": 720,
  "audio_device": "alsa/hdmi:CARD=vc4hdmi0,DEV=0",
  "schedule": [
    {
      "name": "Weekday mornings",
      "days": ["mon", "tue", "wed", "thu", "fri"],
      "start": "08:00",
      "end": "17:00",
      "items": [
        "https://www.youtube.com/playlist?list=PLxxxx",
        "https://www.youtube.com/watch?v=singlevideo",
        { "type": "image", "src": "images/promo.png", "duration": 10 }
      ],
      "shuffle": true
    }
  ],
  "default": ["https://www.youtube.com/playlist?list=PLdefault"],
  "default_shuffle": true
}
```

- **`max_height`** — quality cap. Keep at `720`.
- **`audio_device`** — which HDMI port carries audio. `vc4hdmi0` is the port nearest the
  USB-C power connector; `vc4hdmi1` is the other one. **Must match where the cable is
  plugged in**, or there's no sound. Standardise on one port across all signs.
- **`start`/`end`** — 24-hour, the Pi's local clock. An end earlier than the start
  (e.g. `22:00`–`02:00`) wraps past midnight.
- **`shuffle` / `default_shuffle`** — omit or `false` to play in order.

---

## Adding a new sign

1. **Flash the SD card** with Raspberry Pi Imager:
   - **Raspberry Pi OS Lite (64-bit)**
   - Gear icon (⚙️) → **Hostname AND Username both set to** `marthakalmedia002`
     (next free number) + a password
   - Set Wi-Fi, and **enable SSH**
2. **Plug HDMI in before powering on** — into the same port on every unit (see
   `audio_device` above). The Pi won't initialise video if the display isn't connected
   at boot.
3. **SSH in and run the installer:**
   ```bash
   ssh marthakalmedia002@marthakalmedia002.local
   curl -sSL https://raw.githubusercontent.com/BARKcommunications/marthakal_media_player/main/setup.sh | bash
   ```
   It installs everything, sets up auto-start and auto-update, and reboots.
4. **Open the scheduler**, set Device to `002`, build the schedule, **Publish**.

Until you publish, the new sign plays the shared `playlists.json` from the repo root.

### What the installer does

1. Auto-detects the username and hostname
2. Installs `git`, `mpv`, `python3`, `pip`, video libraries
3. Installs **yt-dlp (pre-release)** and **Deno** (required — YouTube needs a JS runtime
   to extract streams)
4. Clones this repo to `~/marthakal_media_player`
5. Frees `tty1` so the player can own the screen (disables the login console there)
6. Creates the `mediaplayer` service and the `mediaplayer-update` timer
7. Reboots

---

## How updating works

| What | How it updates |
|------|----------------|
| Schedules, images, splash | Publish in the scheduler → Pi pulls within ~2 min |
| `player.py`, `update.sh` | Push to the repo → Pi pulls within ~2 min |
| `yt-dlp` | Auto-refreshed daily by `update.sh` |
| System packages, Deno | Manual (SSH) — only needed for a rebuild |

Force an update immediately instead of waiting:
```bash
sudo systemctl start mediaplayer-update
```

Because `update.sh` itself ships from the repo, the update behaviour can be changed
later with a git push alone — no SSH required.

---

## Remote access (Tailscale)

The Pis run [Tailscale](https://tailscale.com) so they can be reached for support from
anywhere, without touching the venue's firewall. The Tailscale address never changes,
even if the local network does.

```bash
ssh marthakalmedia001@marthakalmedia001      # via Tailscale, from anywhere
```

In the Tailscale admin console, make sure each machine has **key expiry disabled**, or
it will drop off the network after ~90 days. Keep 2FA on the Tailscale account.

> Remote access only works while the Pi is online. A dead SD card or a network outage
> still needs someone on site.

---

## Second Wi-Fi network (optional)

Useful if a sign moves between locations. SSH in and run:

```bash
sudo nmcli device wifi connect "NETWORK_NAME" password "PASSWORD"
```

The Pi joins whichever saved network is available at boot. To prefer one:
```bash
sudo nmcli connection modify "NETWORK_NAME" connection.autoconnect-priority 10
```

> Wi-Fi credentials are entered on the Pi and never stored in this public repo.

---

## Managing the player

```bash
sudo journalctl -u mediaplayer -f          # Watch live logs
sudo systemctl restart mediaplayer         # Restart playback
sudo systemctl stop mediaplayer            # Stop playback
sudo systemctl status mediaplayer          # Check status
sudo systemctl start mediaplayer-update    # Force an update check now
```

---

## Troubleshooting

**Nothing on screen / stuck on the terminal**
HDMI must be connected *before* the Pi powers on — reboot with it plugged in. Then check
`sudo systemctl status mediaplayer`. If the service starts and dies within a second with
no log output from the player, something else is holding `tty1` — confirm
`getty@tty1.service` is disabled.

**No sound**
`audio_device` in the config must match the HDMI port the cable is in. List the options
with `mpv --audio-device=help | grep -i hdmi`, then test one directly:
```bash
mpv --vo=null --audio-device='alsa/hdmi:CARD=vc4hdmi0,DEV=0' "https://www.youtube.com/watch?v=SOME_ID"
```

**Videos fail after a couple of seconds ("Playback ended almost immediately")**
Usually one of two things:
1. **Quality set to 1080p** — drop it to 720p in the scheduler.
2. **yt-dlp is behind a YouTube change.** It auto-refreshes daily, but to force it:
   ```bash
   pip3 install --break-system-packages --upgrade --pre "yt-dlp[default]"
   sudo systemctl restart mediaplayer
   ```
   To diagnose, resolve a failing video by hand and read the error:
   ```bash
   yt-dlp --remote-components ejs:github -g "https://www.youtube.com/watch?v=SOME_ID"
   ```

**"Nothing to play"**
The active block has no valid items, or there's no internet. Check `ping youtube.com`
and confirm the playlists are public or unlisted (private playlists won't work).

**A block never plays**
Blocks match top to bottom, first match wins. An earlier block covering the same days
and times will shadow a later one.

**Nothing updates**
Check the timer is running: `systemctl status mediaplayer-update.timer` (should be
`active (waiting)`). Then `sudo systemctl start mediaplayer-update` and read
`journalctl -u mediaplayer-update -n 30`.

**Player exits instantly with no output**
The repo copy of `player.py` may be empty or the git checkout corrupted (this can happen
after a power cut). Re-clone:
```bash
sudo rm -rf ~/marthakal_media_player
git clone https://github.com/BARKcommunications/marthakal_media_player.git ~/marthakal_media_player
sudo systemctl restart mediaplayer
```

---

## Known limitations

- **Videos stream from YouTube, so every play counts as a view** and contributes watch
  time to the creator's analytics. Switching to download-once-and-play-locally would
  eliminate this (and improve reliability) — not implemented.
- **1080p is unreliable on a Pi 4** because of VP9 software decoding. 720p is the
  practical ceiling.
- **YouTube periodically breaks yt-dlp.** The daily refresh handles this
  automatically, but a fix can lag by a day or two.
- **Deleting an image from a schedule doesn't delete the file** from `images/`; unused
  files accumulate in the repo.
- **A dead SD card or network outage needs someone on site** — no remote fix.

---

## Hardware notes

- **Raspberry Pi 4 or 5**, 2GB is plenty. A Pi 5 handles video more comfortably but
  needs active cooling and a 5V/5A USB-C supply.
- Both use **micro-HDMI** — a micro-HDMI-to-HDMI cable is required.
- Use a **high-endurance microSD card** (SanDisk Extreme, Samsung Pro Endurance). Looping
  video all day is hard on cheap cards, and card corruption is the most likely failure.
