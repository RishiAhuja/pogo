#!/bin/bash
# Pin the relay host key. Run as root on the campus laptop.
#
#   ssh-keyscan -t ed25519 RELAY_HOST | ssh-keygen -lf -
#   sudo ./pin-relay-key.sh 'RELAY_HOST ssh-ed25519 AAAA...'
#
# Compare that fingerprint with a machine that already trusts the relay
# before pinning. This script does not scan the network itself.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the campus laptop." >&2
  exit 1
fi

line=${1:-}
if [[ ! "$line" =~ ^[0-9A-Za-z.:_-]+\ ssh-ed25519\ AAAA[0-9A-Za-z+/=]+$ ]]; then
  echo "Usage: sudo $0 '<host> ssh-ed25519 AAAA...'" >&2
  exit 1
fi

host=${line%% *}
ssh-keygen -lf /dev/stdin <<< "$line" >/dev/null
file=/etc/ssh/ssh_known_hosts
touch "$file"
tmp=$(mktemp "${file}.XXXXXX")
trap 'rm -f "$tmp"' EXIT
awk -v host="$host" '!($1 == host && $2 == "ssh-ed25519")' "$file" > "$tmp"
printf '%s\n' "$line" >> "$tmp"
chmod 644 "$tmp"
chown root:root "$tmp"
mv "$tmp" "$file"
echo "Pinned ${host} in ${file}"
