#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Marthakal Media Player — Raspberry Pi One-Click Setup
#  Run with:
#  curl -sSL https://raw.githubusercontent.com/BARKcommunications/marthakal_media_player/main/setup.sh | bash
# ─────────────────────────────────────────────────────────────

set -e  # Exit immediately if any command fails

REPO_RAW="https://raw.githubusercontent.com/BARKcommunications/marthakal_media_player/main"
INSTALL_DIR="/home/pi"
SERVICE_NAME="mediaplayer"
PLAYER_FILE="$INSTALL_DIR/player.py"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

# ── Colours for output ────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No colour

info()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
section() { echo -e "\n${YELLOW}── $1 ──${NC}"; }

# ── Check we're running on a Pi as the right user ─────────────
section "Checking environment"

if [ "$EUID" -eq 0 ]; then
  error "Please don't run this as root. Run as the 'pi' user without sudo."
fi

if [ "$(whoami)" != "pi" ]; then
  warn "Current user is '$(whoami)', not 'pi'. Files will still install to /home/pi."
fi

if ! grep -qi "raspberry" /proc/cpuinfo 2>/dev/null && ! grep -qi "raspberry" /etc/os-release 2>/dev/null; then
  warn "This doesn't look like a Raspberry Pi — continuing anyway."
fi

info "Environment looks good"

# ── System update & install apt packages ──────────────────────
section "Installing system packages"

sudo apt-get update -qq
sudo apt-get install -y -qq \
  mpv \
  python3 \
  python3-pip \
  curl

info "mpv, python3, pip installed"

# ── Install yt-dlp ────────────────────────────────────────────
section "Installing yt-dlp"

pip3 install --quiet --break-system-packages --upgrade yt-dlp
info "yt-dlp installed"

# ── Download player.py from GitHub ───────────────────────────
section "Downloading player.py"

curl -sSL "$REPO_RAW/player.py" -o "$PLAYER_FILE"
chmod +x "$PLAYER_FILE"
info "player.py saved to $PLAYER_FILE"

# ── Write the systemd service file ───────────────────────────
section "Setting up autostart service"

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Marthakal YouTube Playlist Media Player
After=network-online.target graphical.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 $PLAYER_FILE
WorkingDirectory=$INSTALL_DIR
Restart=always
RestartSec=15
User=pi
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/pi/.Xauthority

[Install]
WantedBy=graphical.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
info "Service enabled — will start on every boot"

# ── Quick dependency check ────────────────────────────────────
section "Verifying installation"

python3 -c "import urllib.request, json, subprocess, sys" && info "Python dependencies OK"
mpv --version > /dev/null 2>&1 && info "mpv OK"
yt-dlp --version > /dev/null 2>&1 && info "yt-dlp OK"
[ -f "$PLAYER_FILE" ] && info "player.py OK"

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup complete! Rebooting in 5 seconds...${NC}"
echo -e "${GREEN}  The player will start automatically on boot.${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  To check logs after reboot, run:"
echo "    sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "  To stop the player:"
echo "    sudo systemctl stop $SERVICE_NAME"
echo ""
echo "  To restart it:"
echo "    sudo systemctl restart $SERVICE_NAME"
echo ""

sleep 5
sudo reboot
