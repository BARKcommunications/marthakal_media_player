#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Marthakal Media Player — Raspberry Pi One-Click Setup
#  Raspberry Pi OS Lite (64-bit). Auto-detects the current user.
#  Clones the repo and sets up auto-update on git push.
#  Run with:
#  curl -sSL https://raw.githubusercontent.com/BARKcommunications/marthakal_media_player/main/setup.sh | bash
# ─────────────────────────────────────────────────────────────

set -e

CURRENT_USER="$(whoami)"
REPO_URL="https://github.com/BARKcommunications/marthakal_media_player.git"
REPO_DIR="$HOME/marthakal_media_player"
SERVICE_NAME="mediaplayer"
PLAYER_FILE="$REPO_DIR/player.py"
UPDATE_SCRIPT="$REPO_DIR/update.sh"

SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
UPDATE_SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME-update.service"
UPDATE_TIMER_FILE="/etc/systemd/system/$SERVICE_NAME-update.timer"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
section() { echo -e "\n${YELLOW}── $1 ──${NC}"; }

# ── Checks ────────────────────────────────────────────────────
section "Checking environment"
if [ "$EUID" -eq 0 ]; then
  error "Please run as your normal user without sudo (e.g. just: bash setup.sh)."
fi
info "Running as user: $CURRENT_USER"
info "Repo directory: $REPO_DIR"

# ── System packages ───────────────────────────────────────────
section "Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq \
  git \
  mpv \
  python3 \
  python3-pip \
  curl \
  libdrm2
info "Packages installed"

# ── yt-dlp ────────────────────────────────────────────────────
section "Installing yt-dlp"
pip3 install --quiet --break-system-packages --upgrade yt-dlp
info "yt-dlp installed"

# ── Clone (or update) the repo ────────────────────────────────
section "Fetching the media player from GitHub"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" reset --hard origin/main --quiet
  git -C "$REPO_DIR" pull --quiet
  info "Existing repo updated"
else
  git clone --quiet "$REPO_URL" "$REPO_DIR"
  info "Repo cloned to $REPO_DIR"
fi
chmod +x "$UPDATE_SCRIPT" 2>/dev/null || true

# Allow root (the update timer runs as root) to use the repo without warnings
sudo git config --system --add safe.directory "$REPO_DIR" || true

# ── Free up tty1 for the player ───────────────────────────────
# The player takes over /dev/tty1 directly for fullscreen DRM output,
# so the login shell must not hold that console (otherwise they fight
# over it and the player is killed with SIGHUP on start).
section "Freeing up the console for video"
sudo systemctl disable getty@tty1.service > /dev/null 2>&1 || true
info "Console tty1 reserved for the player"

# ── Player service ────────────────────────────────────────────
section "Setting up the player service"
sudo tee "$SERVICE_FILE" > /dev/null <<SERVICE
[Unit]
Description=Marthakal YouTube Playlist Media Player
After=network-online.target getty@tty1.service
Wants=network-online.target
Conflicts=getty@tty1.service

[Service]
ExecStart=/usr/bin/python3 $PLAYER_FILE
WorkingDirectory=$REPO_DIR
Restart=always
RestartSec=15
User=$CURRENT_USER
TTYPath=/dev/tty1
StandardInput=tty-force
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE
info "Player service created"

# ── Auto-update service + timer ───────────────────────────────
section "Setting up auto-update on git push"
sudo tee "$UPDATE_SERVICE_FILE" > /dev/null <<UPDSERVICE
[Unit]
Description=Check GitHub for Marthakal Media Player updates
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash $UPDATE_SCRIPT
UPDSERVICE

sudo tee "$UPDATE_TIMER_FILE" > /dev/null <<UPDTIMER
[Unit]
Description=Periodically check GitHub for updates

[Timer]
OnBootSec=1min
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
UPDTIMER
info "Auto-update timer created (checks every 2 minutes)"

# ── Enable everything ─────────────────────────────────────────
section "Enabling services"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl enable "$SERVICE_NAME-update.timer"
info "Services enabled"

# ── Verify ────────────────────────────────────────────────────
section "Verifying installation"
mpv --version > /dev/null 2>&1 && info "mpv OK"
yt-dlp --version > /dev/null 2>&1 && info "yt-dlp OK"
python3 --version > /dev/null 2>&1 && info "Python OK"
[ -f "$PLAYER_FILE" ] && info "player.py OK"
[ -f "$REPO_DIR/playlists.json" ] && info "playlists.json OK"

# ── Done ──────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup complete! Rebooting in 5 seconds...${NC}"
echo -e "${GREEN}  Videos will play fullscreen automatically.${NC}"
echo -e "${GREEN}  Pushes to GitHub apply within ~2 minutes.${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Useful commands:"
echo "    sudo journalctl -u $SERVICE_NAME -f          # live player logs"
echo "    sudo systemctl restart $SERVICE_NAME         # restart player"
echo "    sudo systemctl start $SERVICE_NAME-update    # force an update check now"
echo ""

sleep 5
sudo reboot
