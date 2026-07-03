#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Marthakal Media Player — Auto-update checker
#  Run by a systemd timer every few minutes (as root).
#  Pulls the latest code + playlists from GitHub and restarts
#  the player only if something actually changed.
# ─────────────────────────────────────────────────────────────

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR" || exit 1

# Fetch the latest refs without changing files yet
git fetch origin main --quiet || exit 0

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/main)"

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "Update found: $LOCAL -> $REMOTE. Pulling and restarting."
    # Force local to match remote exactly (device is a consumer of the repo)
    git reset --hard origin/main --quiet
    systemctl restart mediaplayer
else
    echo "Already up to date."
fi
