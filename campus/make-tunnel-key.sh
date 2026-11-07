#!/bin/bash
# Create the laptop's key for the relay. Run as the campus user, not root.
# Never overwrites an existing key.
set -euo pipefail
umask 077

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run this as the campus user, so the key is created in that home directory." >&2
  exit 1
fi

key="$HOME/.ssh/ec2_tunnel"
if [[ -f /etc/hpc-relay/campus.env ]]; then
  set -a
  # shellcheck disable=SC1091
  . /etc/hpc-relay/campus.env
  set +a
  key=${TUNNEL_KEY:-$key}
fi

if [[ -f "$key" ]]; then
  echo "Already exists: $key"
  if [[ ! -f "${key}.pub" ]]; then
    ssh-keygen -y -f "$key" > "${key}.pub"
  fi
else
  if [[ -e "${key}.pub" ]]; then
    echo "Public key exists without its private key: ${key}.pub" >&2
    exit 1
  fi
  install -d -m 700 "$(dirname "$key")"
  ssh-keygen -t ed25519 -N "" -C "${USER}@$(hostname)" -f "$key"
fi

echo
echo "This public key is the only line in the relay tunnel user's authorized_keys:"
cat "${key}.pub"
