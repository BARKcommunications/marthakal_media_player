"""
Raspberry Pi YouTube Playlist Player
- Fetches config JSON from a GitHub raw URL
- Plays each playlist in order using yt-dlp + mpv
- Retries failed videos up to MAX_RETRIES times
- Refreshes config and playlist URLs after every full cycle
"""

import json
import logging
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field

# ─── Configuration ────────────────────────────────────────────────────────────

CONFIG_URL = "https://raw.githubusercontent.com/BARKcommunications/marthakal_media_player/main/playlists.json"

MAX_RETRIES = 3          # How many times to retry a failed video
RETRY_DELAY = 5          # Seconds to wait between retries
CONFIG_FETCH_RETRIES = 5 # How many times to retry fetching the config on startup

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("player.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ─── Startup check ────────────────────────────────────────────────────────────

if sys.platform == "win32":
    log.error("This script is designed to run on Raspberry Pi (Linux) only.")
    log.error("Use it on the Pi after testing your playlists.json on Windows.")
    sys.exit(1)

# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class Config:
    playlists: list[str] = field(default_factory=list)
    shuffle: bool = False
    refresh_interval_hours: float = 6.0


# ─── Helpers ──────────────────────────────────────────────────────────────────

def fetch_config(url: str, retries: int = CONFIG_FETCH_RETRIES) -> Config:
    """Download and parse the JSON config from GitHub."""
    for attempt in range(1, retries + 1):
        try:
            log.info(f"Fetching config (attempt {attempt}/{retries}): {url}")
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            cfg = Config(
                playlists=data.get("playlists", []),
                shuffle=data.get("shuffle", False),
                refresh_interval_hours=data.get("refresh_interval_hours", 6.0),
            )
            log.info(f"Config loaded — {len(cfg.playlists)} playlist(s), shuffle={cfg.shuffle}")
            return cfg
        except Exception as exc:
            log.warning(f"Config fetch failed: {exc}")
            if attempt < retries:
                time.sleep(RETRY_DELAY)
    log.error("Could not fetch config after all retries. Exiting.")
    sys.exit(1)


def get_video_urls(playlist_url: str) -> list[str]:
    """Use yt-dlp to extract all video URLs from a playlist (no download)."""
    log.info(f"Fetching video list from: {playlist_url}")
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print", "url",
        "--no-warnings",
        playlist_url,
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
        log.error("yt-dlp not found. Install it with: pip install yt-dlp")
        sys.exit(1)


def play_video(url: str) -> bool:
    """
    Play a single video with mpv.
    Returns True if playback succeeded, False otherwise.
    """
    cmd = [
        "mpv",
        "--keep-open=no",
        "--really-quiet",
        "--ytdl-format=bestvideo[height<=1080]+bestaudio/best",
        url,
    ]
    log.info(f"Playing: {url}")
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
        log.error("mpv not found. Install it with: sudo apt install mpv")
        sys.exit(1)


def play_with_retry(url: str, max_retries: int = MAX_RETRIES) -> None:
    """Try to play a video, retrying up to max_retries times on failure."""
    for attempt in range(1, max_retries + 1):
        success = play_video(url)
        if success:
            return
        if attempt < max_retries:
            log.warning(f"Retry {attempt}/{max_retries - 1} in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
        else:
            log.error(f"Giving up on: {url}")


# ─── Main loop ────────────────────────────────────────────────────────────────

def run() -> None:
    while True:
        cfg = fetch_config(CONFIG_URL)

        if not cfg.playlists:
            log.warning("No playlists in config. Waiting 60s before retrying...")
            time.sleep(60)
            continue

        # Build the full video queue: each playlist in order
        all_videos: list[tuple[str, str]] = []
        for playlist_url in cfg.playlists:
            urls = get_video_urls(playlist_url)
            for video_url in urls:
                all_videos.append((playlist_url, video_url))

        if not all_videos:
            log.warning("No videos found across all playlists. Retrying in 60s...")
            time.sleep(60)
            continue

        log.info(f"Starting playback — {len(all_videos)} video(s) across {len(cfg.playlists)} playlist(s)")

        current_playlist = None
        for playlist_url, video_url in all_videos:
            if playlist_url != current_playlist:
                log.info(f"\n── Playlist: {playlist_url} ──")
                current_playlist = playlist_url
            play_with_retry(video_url)

        log.info("All playlists finished. Refreshing config and starting again...")


if __name__ == "__main__":
    run()
