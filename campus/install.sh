#!/bin/bash
# Install the campus laptop side. Run as root on that laptop.
#
#   sudo ./install.sh /etc/hpc-relay/campus.env
#
# The env file is created by hand from config/campus.env.example.
# This does not unlock the disk, does not change GDM, and does not print secrets.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the campus laptop." >&2
  exit 1
fi

HERE=$(cd "$(dirname "$0")" && pwd)
ENV_FILE=${1:-/etc/hpc-relay/campus.env}
for command in systemctl nmcli python3 ssh ssh-keygen flock iw rfkill getent stat; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing $command. See docs/setup.md for Ubuntu dependencies." >&2
    exit 1
  fi
done
if [[ ! -d /run/systemd/system ]]; then
  echo "This installer requires a running Linux systemd host." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  echo "Copy config/campus.env.example, fill in the host and interface, and pass that path." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

for key in CAMPUS_USER WIFI_IFACE WIFI_CONNECTION RELAY_HOST RELAY_USER TUNNEL_KEY; do
  if [[ -z "${!key:-}" ]]; then
    echo "campus.env is missing $key" >&2
    exit 1
  fi
done

if [[ ! "$CAMPUS_USER" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
  echo "CAMPUS_USER must be a plain username." >&2
  exit 1
fi
if ! id "$CAMPUS_USER" >/dev/null 2>&1; then
  echo "User $CAMPUS_USER does not exist on this laptop." >&2
  exit 1
fi
CAMPUS_GROUP=$(id -g "$CAMPUS_USER")
RELAY_PORT=${RELAY_PORT:-2222}
if [[ ! "$RELAY_PORT" =~ ^[0-9]+$ ]] || (( 10#$RELAY_PORT < 1 || 10#$RELAY_PORT > 65535 )); then
  echo "RELAY_PORT must be between 1 and 65535." >&2
  exit 1
fi
if [[ "${PORTAL_ENABLED:-1}" != 0 && "${PORTAL_ENABLED:-1}" != 1 ]]; then
  echo "PORTAL_ENABLED must be 0 or 1." >&2
  exit 1
fi
if [[ "${PORTAL_ENABLED:-1}" == 1 ]]; then
  : "${PORTAL_GATEWAY:?Set PORTAL_GATEWAY for the Sophos adapter}"
  if [[ ! -s /etc/nitj-portal/credentials ]]; then
    echo "Create /etc/nitj-portal/credentials before enabling the portal adapter." >&2
    exit 1
  fi
  python3 - "$HERE/rootfs/usr/local/sbin/nitj-portal-login" "$ENV_FILE" <<'PY'
import runpy
import sys
from pathlib import Path

load = runpy.run_path(sys.argv[1])["load_file"]
config = load(Path(sys.argv[2]), shell_values=True)
creds = load(Path("/etc/nitj-portal/credentials"))
if not creds.get("username") or not creds.get("password"):
    raise SystemExit("Portal username and password must be nonempty.")
if config.get("PORTAL_TLS_VERIFY", "1") not in ("0", "1"):
    raise SystemExit("PORTAL_TLS_VERIFY must be 0 or 1.")
ca = config.get("PORTAL_CA_FILE")
if ca and not Path(ca).is_file():
    raise SystemExit("PORTAL_CA_FILE does not exist.")
PY
  chown root:root /etc/nitj-portal/credentials
  chmod 600 /etc/nitj-portal/credentials
fi
if [[ "$TUNNEL_KEY" != /* || ! -s "$TUNNEL_KEY" ]] || [[ "$(stat -c '%U' "$TUNNEL_KEY")" != "$CAMPUS_USER" ]]; then
  echo "TUNNEL_KEY must be an existing absolute path owned by $CAMPUS_USER. Create it first." >&2
  exit 1
fi
key_mode=$(stat -c '%a' "$TUNNEL_KEY")
if (( (8#$key_mode & 077) != 0 )); then
  echo "TUNNEL_KEY is readable by other users. Set mode 600 before installing." >&2
  exit 1
fi
# Loaded from campus.env and validated through the required-key loop above.
# shellcheck disable=SC2153
if ! ssh-keygen -F "$RELAY_HOST" -f /etc/ssh/ssh_known_hosts >/dev/null 2>&1; then
  echo "Pin the relay key with campus/pin-relay-key.sh before installing." >&2
  exit 1
fi
if [[ "$(nmcli -g connection.type connection show "$WIFI_CONNECTION" 2>/dev/null)" != 802-11-wireless ]]; then
  echo "Save the Wi-Fi profile '$WIFI_CONNECTION' before installing." >&2
  exit 1
fi

install -d -m 755 /etc/hpc-relay /usr/local/sbin /etc/nitj-portal
if [[ "$(readlink -f "$ENV_FILE")" != "/etc/hpc-relay/campus.env" ]]; then
  install -m 644 "$ENV_FILE" /etc/hpc-relay/campus.env
fi
chown root:root /etc/hpc-relay/campus.env
chmod 644 /etc/hpc-relay/campus.env

install -m 755 \
  "$HERE/rootfs/usr/local/sbin/aws-reverse-tunnel" \
  "$HERE/rootfs/usr/local/sbin/nitj-portal-login" \
  "$HERE/rootfs/usr/local/sbin/nitj-wifi-ensure" \
  /usr/local/sbin/

units=(
  nitj-boot.service
  nitj-portal.service
  nitj-portal.timer
  nitj-wifi-ensure.service
  nitj-wifi-ensure.timer
)
for unit in "${units[@]}"; do
  install -m 644 "$HERE/rootfs/etc/systemd/system/$unit" "/etc/systemd/system/$unit"
done
sed -e "s/__CAMPUS_USER__/${CAMPUS_USER}/g" -e "s/__CAMPUS_GROUP__/${CAMPUS_GROUP}/g" \
  "$HERE/rootfs/etc/systemd/system/aws-reverse-tunnel.service" \
  > /etc/systemd/system/aws-reverse-tunnel.service
chmod 644 /etc/systemd/system/aws-reverse-tunnel.service

install -d -m 755 \
  /etc/NetworkManager/conf.d \
  /etc/NetworkManager/dispatcher.d \
  /etc/systemd/sleep.conf.d \
  /etc/systemd/logind.conf.d \
  /etc/systemd/journald.conf.d

install -m 644 \
  "$HERE/rootfs/etc/NetworkManager/conf.d/nitj-wifi.conf" \
  /etc/NetworkManager/conf.d/nitj-wifi.conf
install -m 755 \
  "$HERE/rootfs/etc/NetworkManager/dispatcher.d/90-nitj-portal" \
  /etc/NetworkManager/dispatcher.d/90-nitj-portal
install -m 644 \
  "$HERE/rootfs/etc/systemd/sleep.conf.d/no-sleep.conf" \
  /etc/systemd/sleep.conf.d/no-sleep.conf
install -m 644 \
  "$HERE/rootfs/etc/systemd/logind.conf.d/no-suspend.conf" \
  /etc/systemd/logind.conf.d/no-suspend.conf
install -m 644 \
  "$HERE/rootfs/etc/systemd/journald.conf.d/persistent.conf" \
  /etc/systemd/journald.conf.d/persistent.conf

if nmcli connection show "$WIFI_CONNECTION" >/dev/null 2>&1; then
  nmcli connection modify "$WIFI_CONNECTION" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    connection.autoconnect-retries 0 \
    802-11-wireless.cloned-mac-address permanent \
    802-11-wireless.powersave 2
else
  echo "Wi-Fi profile '$WIFI_CONNECTION' is not saved yet. Join that network once, then re-run this installer."
fi

systemctl mask \
  sleep.target \
  suspend.target \
  hibernate.target \
  hybrid-sleep.target \
  suspend-then-hibernate.target

systemctl daemon-reload
systemctl restart systemd-journald
systemctl reload NetworkManager 2>/dev/null || true

systemctl enable aws-reverse-tunnel.service
systemctl enable nitj-boot.service
if [[ "${PORTAL_ENABLED:-1}" == 1 ]]; then
  systemctl enable nitj-portal.timer
  systemctl restart nitj-portal.timer
else
  systemctl disable --now nitj-portal.timer
  systemctl stop nitj-portal.service
fi
systemctl enable nitj-wifi-ensure.timer
systemctl restart nitj-wifi-ensure.timer
systemctl restart aws-reverse-tunnel.service

echo
echo "Campus side installed. logind was not restarted; the lid settings apply on the next boot."
echo "Disk unlock and the desktop login are separate. See docs/setup.md before the next reboot."
