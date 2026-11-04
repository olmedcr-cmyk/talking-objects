#!/usr/bin/env bash
#
# Talking objects — installer for a Raspberry Pi 5 (Raspberry Pi OS Bookworm).
#
# From the device/ folder on the Pi:
#   ./deploy/install.sh
#
# Idempotent: run it as many times as you like.

set -euo pipefail

DEVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="${SUDO_USER:-$(whoami)}"
USER_UID="$(id -u "$USER_NAME")"

say()  { printf "\n\033[1;32m==>\033[0m %s\n" "$*"; }
warn() { printf "\n\033[1;33m[!]\033[0m %s\n" "$*"; }

say "Installing for '$USER_NAME' (UID $USER_UID) in $DEVICE_DIR"

say "1/7  System packages"
sudo apt update
# python3-lgpio is the Pi 5 GPIO backend: the RP1 chip left RPi.GPIO behind.
sudo apt install -y python3 python3-venv python3-dev python3-lgpio \
  libportaudio2 portaudio19-dev i2c-tools alsa-utils git

say "2/7  Enabling I2C and SPI"
# Off in the stock image. Without them there is no LCD (I2C) and no LED strip (SPI).
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0

say "3/7  User groups"
for group in gpio spi i2c audio; do
  getent group "$group" >/dev/null && sudo adduser "$USER_NAME" "$group" >/dev/null 2>&1 || true
done

say "4/7  Python virtual environment"
# Bookworm marks the system Python as externally managed (PEP 668).
# --system-site-packages lets the venv see python3-lgpio from apt.
python3 -m venv --system-site-packages "$DEVICE_DIR/.venv"
"$DEVICE_DIR/.venv/bin/pip" install --upgrade pip wheel >/dev/null
"$DEVICE_DIR/.venv/bin/pip" install -r "$DEVICE_DIR/requirements.txt"

say "5/7  ALSA: USB sound card as default"
CARD=$(aplay -l 2>/dev/null | grep -iE "USB Audio" | head -1 | sed -E 's/^card ([0-9]+):.*/\1/' || true)
if [[ -n "$CARD" ]]; then
  sed "s/__CARD__/$CARD/g" "$DEVICE_DIR/deploy/asound.conf" | sudo tee /etc/asound.conf >/dev/null
  echo "   /etc/asound.conf written (card $CARD)"
else
  warn "No USB sound card found; plug it in and run the installer again."
fi

say "6/7  Configuration"
[[ -f "$DEVICE_DIR/config.env" ]] || cp "$DEVICE_DIR/config.example.env" "$DEVICE_DIR/config.env"
[[ -f "$DEVICE_DIR/rules.toml" ]] || cp "$DEVICE_DIR/rules.example.toml" "$DEVICE_DIR/rules.toml"
chmod 600 "$DEVICE_DIR/config.env"
grep -qE "^VIDIV_AGENT_SLUG=.+" "$DEVICE_DIR/config.env" || warn "VIDIV_AGENT_SLUG is empty in config.env"

say "7/7  systemd service"
sed -e "s|__DEVICE_DIR__|$DEVICE_DIR|g" -e "s|__USER__|$USER_NAME|g" -e "s|__UID__|$USER_UID|g" \
  "$DEVICE_DIR/deploy/talking-objects.service" | sudo tee /etc/systemd/system/talking-objects.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable talking-objects.service

cat <<EOF

──────────────────────────────────────────────────────────────────────
Done. Before starting:

  1. If I2C or SPI were off, reboot:          sudo reboot
  2. Fill in config.env                       nano $DEVICE_DIR/config.env
  3. Find the LCD address, if you have one:   sudo i2cdetect -y 1

Try it by hand, watching the log:
    cd $DEVICE_DIR && .venv/bin/python -m talking_objects -v

Without touching the switch:
    TRIGGER_MODE=keyboard .venv/bin/python -m talking_objects

As a service:
    sudo systemctl start talking-objects
    journalctl -u talking-objects -f
──────────────────────────────────────────────────────────────────────
EOF
