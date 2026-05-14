#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Marthakal Media Player — Raspberry Pi One-Click Setup
#  Designed for Raspberry Pi OS Lite (64-bit)
#  Run with:
#  curl -sSL https://raw.githubusercontent.com/BARKcommunications/marthakal_media_player/main/setup.sh | bash
# ─────────────────────────────────────────────────────────────

set -e

REPO_RAW="https://raw.githubusercontent.com/BARKcommunications/marthakal_media_player/main"
INSTALL_DIR="/home/pi"
SERVICE_NAME="mediaplayer"
PLAYER_FILE="$INSTALL_DIR/player.py"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
section() { echo -e "\n${YELLOW}── $1 ──${NC}"; }

# ── Checks ────────────────────────────────────────────────────
section "Checking environment"

if [ "$EUID" -eq 0 ]; then
  error "Please run as the 'pi' user without sudo."
fi

info "Environment OK"

# ── System packages ───────────────────────────────────────────
section "Installing system packages"

sudo apt-get update -qq
sudo apt-get install -y -qq \
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

# ── Auto-login on boot (no password prompt) ───────────────────
section "Configuring auto-login"

sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf > /dev/null <<AUTOLOGIN
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin pi --noclear %I \$TERM
AUTOLOGIN

info "Auto-login configured"

# ── Download player.py ────────────────────────────────────────
section "Downloading player.py"

curl -sSL "$REPO_RAW/player.py" -o "$PLAYER_FILE"
chmod +x "$PLAYER_FILE"
info "player.py saved to $PLAYER_FILE"

# ── Systemd service ───────────────────────────────────────────
section "Setting up autostart service"

sudo tee "$SERVICE_FILE" > /dev/null <<SERVICE
[Unit]
Description=Marthakal YouTube Playlist Media Player
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 $PLAYER_FILE
WorkingDirectory=$INSTALL_DIR
Restart=always
RestartSec=15
User=pi
StandardInput=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
info "Service enabled"

# ── Verify ────────────────────────────────────────────────────
section "Verifying installation"

mpv --version > /dev/null 2>&1 && info "mpv OK"
yt-dlp --version > /dev/null 2>&1 && info "yt-dlp OK"
python3 --version > /dev/null 2>&1 && info "Python OK"
[ -f "$PLAYER_FILE" ] && info "player.py OK"

# ── Done ──────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup complete! Rebooting in 5 seconds...${NC}"
echo -e "${GREEN}  Videos will play fullscreen automatically.${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Useful commands:"
echo "    sudo journalctl -u $SERVICE_NAME -f   # live logs"
echo "    sudo systemctl stop $SERVICE_NAME     # stop player"
echo "    sudo systemctl restart $SERVICE_NAME  # restart player"
echo ""

sleep 5
sudo reboot
