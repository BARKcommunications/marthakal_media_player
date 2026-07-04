"""
Marthakal Media Player — Raspberry Pi YouTube Playlist Player
- Reads a local playlists.json (kept up to date via git auto-update)
- Schedule-aware: different content by day of week + time of day
- Falls back to a default playlist when nothing is scheduled
- One long-lived mpv instance holds the screen the whole time and is fed
  videos over an IPC socket, so the terminal never shows between videos
- Shows splash.png (if present in the repo) in the gaps while the next
  video's stream is being resolved
- Fullscreen via DRM (no desktop needed), H.264 preferred for smooth Pi 4 playback
"""

import datetime
import json
import logging
import os
import socket
import subprocess
import sys
import time

# ─── Paths & configuration ────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "playlists.json")
SPLASH_PATH = os.path.join(SCRIPT_DIR, "splash.png")   # optional; upload to repo
MPV_SOCKET = "/tmp/mpv-marthakal.sock"

MAX_RETRIES = 3          # How many times to retry a failed video
RETRY_DELAY = 5          # Seconds between retries
EMPTY_WAIT = 30          # Seconds to wait when there's nothing to play
MIN_PLAY_OK = 3          # A "video" shorter than this is treated as a failure
RESOLVE_TIMEOUT = 60     # Seconds allowed for yt-dlp to resolve a stream URL
VIDEO_TIMEOUT = 7200     # Hard cap per video (2 hours)

# Quality cap. The Pi 4 hardware-decodes H.264 but NOT VP9, so we prefer H.264
# and cap the height. Override per-config with "max_height" in playlists.json.
DEFAULT_MAX_HEIGHT = 720
MAX_HEIGHT = DEFAULT_MAX_HEIGHT

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

if sys.platform == "win32":
    log.error("This script runs on Raspberry Pi (Linux) only.")
    log.error("Use scheduler.html to build playlists.json, then push to GitHub.")
    sys.exit(1)

# ─── Config loading ───────────────────────────────────────────────────────────

_last_good_config = None

def load_config():
    """Read playlists.json, falling back to the last good copy if it's briefly
    invalid (e.g. mid git-pull) so a bad commit never takes the screen down."""
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
        log.error(f"Config unreadable and no previous config: {exc}")
        return {"schedule": [], "default": []}


# ─── Schedule resolution ──────────────────────────────────────────────────────

def _parse_hhmm(s: str) -> int:
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def _block_active(block: dict, now: datetime.datetime) -> bool:
    day = DAY_KEYS[now.weekday()]
    if day not in block.get("days", []):
        return False
    mins = now.hour * 60 + now.minute
    start = _parse_hhmm(block.get("start", "00:00"))
    end = _parse_hhmm(block.get("end", "23:59"))
    if start <= end:
        return start <= mins < end
    return mins >= start or mins < end   # wraps past midnight


def resolve_active_source(cfg: dict, now: datetime.datetime):
    """Decide what should play now. Returns (source_id, items_list)."""
    for i, block in enumerate(cfg.get("schedule", [])):
        if _block_active(block, now):
            name = block.get("name", f"block-{i}")
            return (f"schedule:{i}:{name}", block.get("items", []))
    if "default" in cfg:
        return ("default", cfg.get("default", []))
    if "playlists" in cfg:                # backward compatibility
        return ("default", cfg.get("playlists", []))
    return ("default", [])


# ─── yt-dlp helpers ───────────────────────────────────────────────────────────

def ytdl_format(max_h: int) -> str:
    """
    Prefer a single progressive H.264 + AAC stream so:
      - the Pi 4 can hardware-decode it (smooth playback), and
      - yt-dlp returns ONE direct URL, which we can pre-resolve and hand to
        mpv for a near-instant start (keeping the splash up during the wait).
    Falls back to any single stream at the height cap.
    """
    return (
        f"best[height<={max_h}][vcodec^=avc1][acodec^=mp4a]/"
        f"best[height<={max_h}][ext=mp4]/"
        f"best[height<={max_h}]/best"
    )


def get_video_urls(playlist_url: str) -> list:
    """Expand a playlist URL into a list of video page URLs (no download)."""
    log.info(f"Fetching video list from: {playlist_url}")
    cmd = ["yt-dlp", "--flat-playlist", "--print", "url", "--no-warnings", playlist_url]
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
    """Flatten playlist URLs + single video URLs into an ordered video list."""
    videos = []
    for item in items:
        if "list=" in item:
            videos.extend(get_video_urls(item))
        elif item.strip():
            videos.append(item.strip())
    return videos


def resolve_stream_url(page_url: str):
    """Resolve a YouTube page URL to a direct stream URL. Returns str or None."""
    cmd = ["yt-dlp", "-f", ytdl_format(MAX_HEIGHT), "-g", "--no-warnings", page_url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=RESOLVE_TIMEOUT)
        lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        if not lines:
            log.warning(f"Could not resolve stream for: {page_url}")
            return None
        return lines[0]
    except subprocess.TimeoutExpired:
        log.warning("yt-dlp -g timed out resolving stream.")
        return None
    except FileNotFoundError:
        log.error("yt-dlp not found. Run setup.sh to install.")
        sys.exit(1)


# ─── mpv IPC control ──────────────────────────────────────────────────────────

class MpvIPC:
    """Minimal JSON-IPC client for talking to a running mpv over a unix socket."""

    def __init__(self, path: str):
        self.path = path
        self.sock = None
        self.buf = b""
        self.rid = 0

    def connect(self, timeout: float = 15.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if os.path.exists(self.path):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(self.path)
                    s.settimeout(10)
                    self.sock = s
                    return True
                except OSError:
                    pass
            time.sleep(0.25)
        return False

    def _readline(self) -> bytes:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("mpv socket closed")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line

    def command(self, cmd: list):
        """Send a command, return mpv's reply dict for it (ignoring events)."""
        self.rid += 1
        rid = self.rid
        msg = json.dumps({"command": cmd, "request_id": rid}) + "\n"
        self.sock.sendall(msg.encode())
        while True:
            line = self._readline()
            try:
                obj = json.loads(line.decode())
            except ValueError:
                continue
            if obj.get("request_id") == rid:
                return obj            # a reply
            # otherwise it's an async event — ignore

    def get(self, prop: str):
        return self.command(["get_property", prop]).get("data")

    def loadfile(self, path: str):
        return self.command(["loadfile", path, "replace"])

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def start_mpv() -> subprocess.Popen:
    """Launch the long-lived mpv that owns the screen for the whole session."""
    # Clean up any stale instance/socket from a previous run
    subprocess.run(["pkill", "-f", f"--input-ipc-server={MPV_SOCKET}"],
                   capture_output=True)
    try:
        os.remove(MPV_SOCKET)
    except OSError:
        pass
    time.sleep(0.5)

    cmd = [
        "mpv",
        "--idle=yes",                       # stay alive with no file loaded
        "--force-window=immediate",         # own the screen from the very start
        "--fullscreen",
        "--vo=drm",
        "--hwdec=auto-safe",
        "--really-quiet",
        "--osc=no",
        "--no-input-default-bindings",
        "--cursor-autohide=always",
        "--image-display-duration=inf",     # splash image stays until replaced
        "--cache=yes",
        "--cache-secs=20",
        f"--input-ipc-server={MPV_SOCKET}",
    ]
    log.info("Launching mpv (persistent display).")
    return subprocess.Popen(cmd)


def show_splash(mpv: MpvIPC) -> None:
    """Display the splash image, if one has been added to the repo."""
    if os.path.exists(SPLASH_PATH):
        try:
            mpv.loadfile(SPLASH_PATH)
        except Exception as exc:
            log.warning(f"Could not show splash: {exc}")
    # If there's no splash file, mpv simply stays on a black screen — still
    # no terminal, which is the main goal.


def wait_until_idle(mpv: MpvIPC, timeout: float = VIDEO_TIMEOUT) -> float:
    """Block until the current video finishes (mpv returns to idle).
    Returns how many seconds it played."""
    start = time.time()
    time.sleep(0.8)   # let playback actually begin
    while time.time() - start < timeout:
        if mpv.get("idle-active") is True:
            break
        time.sleep(1)
    return time.time() - start


# ─── Playback ─────────────────────────────────────────────────────────────────

def play_video(mpv: MpvIPC, page_url: str) -> bool:
    """Resolve, then play a single video on the persistent mpv. True on success."""
    direct = resolve_stream_url(page_url)   # splash stays up during this wait
    if not direct:
        return False
    log.info(f"Playing (max {MAX_HEIGHT}p): {page_url}")
    try:
        mpv.loadfile(direct)
    except Exception as exc:
        log.warning(f"mpv loadfile failed: {exc}")
        return False
    played = wait_until_idle(mpv)
    show_splash(mpv)                          # cover the gap before the next one
    if played < MIN_PLAY_OK:
        log.warning(f"Playback ended almost immediately ({played:.1f}s).")
        return False
    return True


def play_with_retry(mpv: MpvIPC, page_url: str, max_retries: int = MAX_RETRIES) -> None:
    for attempt in range(1, max_retries + 1):
        if play_video(mpv, page_url):
            return
        if attempt < max_retries:
            log.warning(f"Retry {attempt}/{max_retries - 1} in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
        else:
            log.error(f"Giving up on: {page_url}")


# ─── Main loop ────────────────────────────────────────────────────────────────

def run() -> None:
    log.info("Marthakal Media Player starting up.")
    proc = start_mpv()
    mpv = MpvIPC(MPV_SOCKET)
    if not mpv.connect():
        log.error("Could not connect to mpv IPC socket. Exiting so systemd restarts.")
        proc.terminate()
        sys.exit(1)
    show_splash(mpv)

    current_source = None
    queue = []
    index = 0

    try:
        while True:
            cfg = load_config()

            global MAX_HEIGHT
            try:
                MAX_HEIGHT = int(cfg.get("max_height", DEFAULT_MAX_HEIGHT))
            except (ValueError, TypeError):
                MAX_HEIGHT = DEFAULT_MAX_HEIGHT

            source_id, items = resolve_active_source(cfg, datetime.datetime.now())

            if source_id != current_source or index >= len(queue):
                if source_id != current_source:
                    log.info(f"── Now playing source: {source_id} ──")
                queue = expand_items(items)
                index = 0
                current_source = source_id
                if not queue:
                    log.warning(f"Nothing to play for '{source_id}'. Waiting {EMPTY_WAIT}s...")
                    show_splash(mpv)
                    time.sleep(EMPTY_WAIT)
                    current_source = None
                    continue

            play_with_retry(mpv, queue[index])
            index += 1
    except ConnectionError as exc:
        log.error(f"Lost connection to mpv ({exc}). Exiting so systemd restarts.")
        sys.exit(1)
    finally:
        mpv.close()
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    run()
