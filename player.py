"""
Marthakal Media Player — Raspberry Pi YouTube Playlist Player
- Reads a local playlists.json (kept up to date via git auto-update)
- Schedule-aware: plays different content by day of week + time of day
- Falls back to a default playlist when nothing is scheduled
- Multiple items per slot play in order, then loop
- Fullscreen via DRM (no desktop needed) using yt-dlp + mpv
"""

import datetime
import json
import logging
import os
import subprocess
import sys
import time

# ─── Configuration ────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "playlists.json")

MAX_RETRIES = 3          # How many times to retry a failed video
RETRY_DELAY = 5          # Seconds between retries
EMPTY_WAIT = 30          # Seconds to wait when there's nothing to play

# Max video height (resolution). The Pi 4 hardware-decodes H.264 but NOT VP9,
# so we cap the height and prefer H.264 to keep playback smooth. Lower this
# (e.g. 480) if a display still stutters. Can be overridden per-config with
# "max_height" in playlists.json.
DEFAULT_MAX_HEIGHT = 720
MAX_HEIGHT = DEFAULT_MAX_HEIGHT  # updated from config at runtime

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(SCRIPT_DIR, "player.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ─── Platform check ───────────────────────────────────────────────────────────

if sys.platform == "win32":
    log.error("This script runs on Raspberry Pi (Linux) only.")
    log.error("Use scheduler.html to build playlists.json, then push to GitHub.")
    sys.exit(1)

# ─── Config loading ───────────────────────────────────────────────────────────

_last_good_config = None

def load_config():
    """
    Read playlists.json from disk. Returns the parsed dict.
    Falls back to the last good config if the file is temporarily invalid
    (e.g. mid git-pull), so a bad commit never takes the screen down.
    """
    global _last_good_config
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        _last_good_config = cfg
        return cfg
    except Exception as exc:
        if _last_good_config is not None:
            log.warning(f"Config unreadable ({exc}); using last good config.")
            return _last_good_config
        log.error(f"Config unreadable and no previous config to fall back on: {exc}")
        return {"schedule": [], "default": []}


# ─── Schedule resolution ──────────────────────────────────────────────────────

def _parse_hhmm(s: str) -> int:
    """'09:30' -> minutes since midnight (570)."""
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def _block_active(block: dict, now: datetime.datetime) -> bool:
    """Is this schedule block active at `now`?"""
    day = DAY_KEYS[now.weekday()]
    if day not in block.get("days", []):
        return False
    mins = now.hour * 60 + now.minute
    start = _parse_hhmm(block.get("start", "00:00"))
    end = _parse_hhmm(block.get("end", "23:59"))
    if start <= end:
        return start <= mins < end
    # Range wraps past midnight (e.g. 22:00–02:00)
    return mins >= start or mins < end


def resolve_active_source(cfg: dict, now: datetime.datetime):
    """
    Decide what should be playing right now.
    Returns (source_id, items_list).
    - Checks schedule blocks in order; first match wins.
    - Falls back to 'default' if no block matches.
    Supports the old {"playlists": [...]} schema as default-only.
    """
    schedule = cfg.get("schedule", [])
    for i, block in enumerate(schedule):
        if _block_active(block, now):
            name = block.get("name", f"block-{i}")
            return (f"schedule:{i}:{name}", block.get("items", []))

    # Fallbacks
    if "default" in cfg:
        return ("default", cfg.get("default", []))
    if "playlists" in cfg:  # backward compatibility with old schema
        return ("default", cfg.get("playlists", []))
    return ("default", [])


# ─── yt-dlp / mpv ─────────────────────────────────────────────────────────────

def get_video_urls(playlist_url: str) -> list:
    """Expand a playlist URL into a list of video URLs (no download)."""
    log.info(f"Fetching video list from: {playlist_url}")
    cmd = [
        "yt-dlp", "--flat-playlist", "--print", "url",
        "--no-warnings", playlist_url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        urls = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        log.info(f"  → {len(urls)} video(s) found")
        return urls
    except subprocess.TimeoutExpired:
        log.warning("yt-dlp timed out fetching playlist.")
        return []
    except FileNotFoundError:
        log.error("yt-dlp not found. Run setup.sh to install.")
        sys.exit(1)


def expand_items(items: list) -> list:
    """
    Turn a list of items (playlist URLs and/or single video URLs)
    into a flat list of playable video URLs, in order.
    """
    videos = []
    for item in items:
        if "list=" in item:
            videos.extend(get_video_urls(item))
        elif item.strip():
            videos.append(item.strip())
    return videos


def ytdl_format(max_h: int) -> str:
    """
    Build a yt-dlp format string that keeps playback smooth on a Pi 4:
    1. Prefer H.264 video (avc1) + AAC audio — both hardware-decodable.
    2. Fall back to any codec at the height cap if H.264 isn't offered.
    3. Fall back to a single best file, then absolute best, as a last resort.
    """
    return (
        f"bestvideo[height<={max_h}][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
        f"bestvideo[height<={max_h}]+bestaudio/"
        f"best[height<={max_h}]/best"
    )


def play_video(url: str) -> bool:
    """Play a single video fullscreen via DRM. True on success."""
    cmd = [
        "mpv",
        "--vo=drm",
        "--hwdec=auto-safe",     # use hardware decoding when it's known-safe
        "--fullscreen",
        "--keep-open=no",
        "--really-quiet",
        "--cache=yes",           # buffer ahead to smooth out network jitter
        "--cache-secs=20",
        f"--ytdl-format={ytdl_format(MAX_HEIGHT)}",
        url,
    ]
    log.info(f"Playing (max {MAX_HEIGHT}p): {url}")
    try:
        result = subprocess.run(cmd, timeout=7200)
        if result.returncode == 0:
            return True
        log.warning(f"mpv exited with code {result.returncode}")
        return False
    except subprocess.TimeoutExpired:
        log.warning("Video hit 2-hour timeout, skipping.")
        return False
    except FileNotFoundError:
        log.error("mpv not found. Run: sudo apt install mpv")
        sys.exit(1)


def play_with_retry(url: str, max_retries: int = MAX_RETRIES) -> None:
    """Play a video, retrying on failure before giving up."""
    for attempt in range(1, max_retries + 1):
        if play_video(url):
            return
        if attempt < max_retries:
            log.warning(f"Retry {attempt}/{max_retries - 1} in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
        else:
            log.error(f"Giving up on: {url}")


# ─── Main loop ────────────────────────────────────────────────────────────────

def run() -> None:
    log.info("Marthakal Media Player starting up.")
    current_source = None
    queue = []
    index = 0

    while True:
        cfg = load_config()

        # Apply the quality cap from config (falls back to the default).
        global MAX_HEIGHT
        try:
            MAX_HEIGHT = int(cfg.get("max_height", DEFAULT_MAX_HEIGHT))
        except (ValueError, TypeError):
            MAX_HEIGHT = DEFAULT_MAX_HEIGHT

        source_id, items = resolve_active_source(cfg, datetime.datetime.now())

        # (Re)build the queue when the active source changes or the queue runs out.
        if source_id != current_source or index >= len(queue):
            if source_id != current_source:
                log.info(f"\n── Now playing source: {source_id} ──")
            queue = expand_items(items)
            index = 0
            current_source = source_id

            if not queue:
                log.warning(f"Nothing to play for '{source_id}'. Waiting {EMPTY_WAIT}s...")
                time.sleep(EMPTY_WAIT)
                current_source = None  # force a fresh check next loop
                continue

        video = queue[index]
        play_with_retry(video)
        index += 1


if __name__ == "__main__":
    run()
