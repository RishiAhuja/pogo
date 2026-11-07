#!/bin/bash
# Install on a dedicated Ubuntu 24.04 relay. Keep an admin SSH session open.
set -euo pipefail
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the relay." >&2
  exit 1
fi
for command in systemctl sshd ssh-keygen useradd getent python3; do
  command -v "$command" >/dev/null 2>&1 || { echo "Missing $command; see docs/setup.md." >&2; exit 1; }
done
[[ -d /run/systemd/system ]] || { echo "A running Linux systemd host is required." >&2; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
TUNNEL_USER=${TUNNEL_USER:-tunnel}
requested_port=${RELAY_PORT:-}
if [[ -f /etc/relay-status/status.env ]]; then
  # This is a root-owned, trusted shell configuration file.
  # shellcheck disable=SC1091
  . /etc/relay-status/status.env
fi
RELAY_PORT=${requested_port:-${RELAY_PORT:-2222}}
PUBKEY=${1:-}
if [[ $# -gt 1 || ! "$TUNNEL_USER" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
  echo "Usage: sudo TUNNEL_USER=tunnel RELAY_PORT=2222 $0 [laptop.pub]" >&2
  exit 1
fi
if [[ ! "$RELAY_PORT" =~ ^[0-9]+$ ]] || (( 10#$RELAY_PORT < 1 || 10#$RELAY_PORT > 65535 )); then
  echo "RELAY_PORT must be between 1 and 65535." >&2
  exit 1
fi
if id "$TUNNEL_USER" >/dev/null 2>&1; then
  groups=" $(id -nG "$TUNNEL_USER") "
  if (( $(id -u "$TUNNEL_USER") < 1000 )) || [[ "$TUNNEL_USER" == "${SUDO_USER:-}" || "$groups" =~ \ (sudo|admin|wheel|root)\  ]]; then
    echo "TUNNEL_USER must be a dedicated account, not your admin/sudo account." >&2
    exit 1
  fi
fi
if [[ -n "$PUBKEY" ]]; then
  if [[ ! -f "$PUBKEY" ]] || ! ssh-keygen -lf "$PUBKEY" >/dev/null; then
    echo "Invalid public key file." >&2
    exit 1
  fi
  [[ $(awk 'NF && $1 !~ /^#/ {n++} END {print n+0}' "$PUBKEY") -eq 1 ]] || { echo "Supply exactly one public key." >&2; exit 1; }
elif ! id "$TUNNEL_USER" >/dev/null 2>&1; then
  echo "A laptop public key is required for the first installation." >&2
  exit 1
fi
if [[ -n "${FONT_SRC:-}" ]]; then
  for font in Athletics-Regular.woff2 Athletics-Bold.woff2; do
    [[ -f "$FONT_SRC/$font" ]] || { echo "FONT_SRC is missing $font" >&2; exit 1; }
  done
fi
if ! id "$TUNNEL_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$TUNNEL_USER"
fi
home=$(getent passwd "$TUNNEL_USER" | cut -d: -f6)
group=$(id -gn "$TUNNEL_USER")
if [[ -z "$PUBKEY" && ! -s "$home/.ssh/authorized_keys" ]]; then
  echo "No existing authorized_keys. Supply the laptop public key." >&2
  exit 1
fi

# OpenSSH uses the first obtained value: this must precede cloud-image drop-ins.
install -d -m 755 /etc/ssh/sshd_config.d
conf=/etc/ssh/sshd_config.d/00-hpc-relay.conf
backup=$(mktemp -d)
committed=0
[[ ! -f "$conf" ]] || cp -p "$conf" "$backup/previous"
cleanup() {
  if [[ "$committed" == 0 ]]; then
    if [[ -f "$backup/previous" ]]; then cp -p "$backup/previous" "$conf"; else rm -f "$conf"; fi
  fi
  rm -rf "$backup"
}
trap cleanup EXIT
sed -e "s/__TUNNEL_USER__/$TUNNEL_USER/g" -e "s/__RELAY_PORT__/$RELAY_PORT/g" "$HERE/sshd/00-hpc-relay.conf" > "$conf"
chmod 644 "$conf"
sshd -t
settings=$(sshd -T -C "user=$TUNNEL_USER,host=localhost,addr=127.0.0.1")
for expected in 'passwordauthentication no' 'kbdinteractiveauthentication no' 'permitrootlogin no' 'pubkeyauthentication yes' 'gatewayports no' 'allowtcpforwarding remote' 'maxsessions 0' "permitlisten 127.0.0.1:$RELAY_PORT"; do
  if ! grep -Fxq "$expected" <<< "$settings"; then
    echo "Effective sshd configuration did not contain '$expected'. Restoring previous drop-in." >&2
    exit 1
  fi
done
systemctl reload ssh
committed=1
passwd -l "$TUNNEL_USER" >/dev/null
install -d -m 700 -o "$TUNNEL_USER" -g "$group" "$home/.ssh"
if [[ -n "$PUBKEY" ]]; then
  install -m 600 -o "$TUNNEL_USER" -g "$group" "$PUBKEY" "$home/.ssh/authorized_keys"
fi

if ! id relay-status >/dev/null 2>&1; then
  useradd --system --user-group --home-dir /var/lib/relay-status --shell /usr/sbin/nologin relay-status
elif (( $(id -u relay-status) == 0 || $(id -u relay-status) >= 1000 )); then
  echo "relay-status must be an unprivileged service account." >&2
  exit 1
fi
install -d -m 750 -o relay-status -g relay-status /var/lib/relay-status
for name in history.jsonl summary.json summary.json.tmp; do
  file=/var/lib/relay-status/$name
  [[ ! -L "$file" ]] || { echo "Refusing state symlink: $file" >&2; exit 1; }
  if [[ -f "$file" ]]; then chown relay-status:relay-status "$file"; chmod 640 "$file"; fi
done
install -d -m 755 /etc/relay-status /usr/local/share/relay-fonts /usr/local/share/relay-status
python3 - "$RELAY_PORT" <<'CONFIG'
import sys
from pathlib import Path
path = Path('/etc/relay-status/status.env')
lines = path.read_text().splitlines() if path.exists() else []
lines = [line for line in lines if line.split('=', 1)[0].strip() != 'RELAY_PORT']
lines.append('RELAY_PORT=' + sys.argv[1])
path.write_text('\n'.join(lines) + '\n')
path.chmod(0o644)
CONFIG
install -m 755 "$HERE/bin/tunnel-status-web.py" /usr/local/sbin/tunnel-status-web.py
install -m 644 "$HERE/assets/moon.webp" /usr/local/share/relay-status/moon.webp
install -m 644 "$HERE/systemd/tunnel-status-web.service" /etc/systemd/system/tunnel-status-web.service
if [[ -n "${FONT_SRC:-}" ]]; then
  install -m 644 "$FONT_SRC/Athletics-Regular.woff2" "$FONT_SRC/Athletics-Bold.woff2" /usr/local/share/relay-fonts/
fi
systemctl daemon-reload
systemctl enable tunnel-status-web.service
systemctl restart tunnel-status-web.service
echo "Relay installed. Status page restarted; tunnel account restricted to loopback port $RELAY_PORT."
