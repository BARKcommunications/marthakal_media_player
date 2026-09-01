#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Marthakal Media Player — Auto-update checker
#  Run by a systemd timer every couple of minutes (as root).
#  1. Pulls the latest code + playlists from GitHub, restarts on change.
#  2. Refreshes yt-dlp at most once a day (YouTube breaks it periodically,
#     and this keeps the sign playing without any SSH access).
#
#  Because THIS script ships from the repo, its own behaviour — including how
#  often yt-dlp refreshes — can be changed later with a git push alone.
# ─────────────────────────────────────────────────────────────

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR" || exit 1

RESTART=0

# ── 1. Pull repo changes (code, playlists, images, splash) ────
git fetch origin main --quiet || exit 0
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/main)"
if [ "$LOCAL" != "$REMOTE" ]; then
    echo "Update found: $LOCAL -> $REMOTE. Pulling."
    git reset --hard origin/main --quiet
    RESTART=1
else
    echo "Repo already up to date."
fi

# ── 2. Refresh yt-dlp at most once every 24h ──────────────────
# YouTube periodically breaks yt-dlp; the --pre build carries the fixes first.
STAMP="/var/tmp/marthakal-ytdlp-updated"
NEED_YTDLP=0
if [ ! -f "$STAMP" ]; then
    NEED_YTDLP=1
elif [ "$(( $(date +%s) - $(stat -c %Y "$STAMP") ))" -gt 86400 ]; then
    NEED_YTDLP=1
fi
if [ "$NEED_YTDLP" -eq 1 ]; then
    echo "Refreshing yt-dlp…"
    BEFORE="$(yt-dlp --version 2>/dev/null)"
    if pip3 install --break-system-packages --upgrade --pre "yt-dlp[default]" --quiet; then
        touch "$STAMP"
        AFTER="$(yt-dlp --version 2>/dev/null)"
        if [ "$BEFORE" != "$AFTER" ]; then
            echo "yt-dlp updated: $BEFORE -> $AFTER"
            RESTART=1
        else
            echo "yt-dlp already current ($AFTER)."
        fi
    else
        echo "yt-dlp update failed (will retry next cycle)."
    fi
fi

# ── 3. Restart the player if anything changed ─────────────────
if [ "$RESTART" -eq 1 ]; then
    echo "Restarting media player."
    systemctl restart mediaplayer
fi
