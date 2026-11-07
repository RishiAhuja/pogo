#!/bin/bash
# Create the three Mac keys if they are missing. Never overwrites a key.
set -euo pipefail
umask 077
install -d -m 700 "$HOME/.ssh"

no_passphrase=0
if [[ "${1:-}" == "--no-passphrase" && $# -eq 1 ]]; then
  no_passphrase=1
elif [[ $# -ne 0 ]]; then
  echo "Usage: $0 [--no-passphrase]" >&2
  exit 1
fi

make_key() {
  local path=$1 comment=$2
  if [[ -f "$path" ]]; then
    if [[ ! -f "${path}.pub" ]]; then
      ssh-keygen -y -f "$path" > "${path}.pub"
    fi
    echo "exists  $path"
    return
  fi
  if [[ -e "${path}.pub" ]]; then
    echo "Public key exists without its private key: ${path}.pub" >&2
    exit 1
  fi
  if [[ "$no_passphrase" == 1 ]]; then
    ssh-keygen -t ed25519 -N "" -C "$comment" -f "$path"
  else
    ssh-keygen -t ed25519 -C "$comment" -f "$path"
  fi
}

make_key "$HOME/.ssh/hpc_relay" "mac-to-relay"
make_key "$HOME/.ssh/hpc_campus" "mac-to-campus"
make_key "$HOME/.ssh/hpc_cluster" "mac-to-hpc"

echo
echo "Install each public key on the matching machine. See docs/setup.md."
echo
for name in hpc_relay hpc_campus hpc_cluster; do
  echo "----- ${name}.pub -----"
  cat "$HOME/.ssh/${name}.pub"
  echo
done
