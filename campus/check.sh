#!/bin/bash
# Read-only check. Exits nonzero when a required component is unhealthy.
set -u
result=0
if [[ ! -f /etc/hpc-relay/campus.env ]]; then
  echo "campus.env: missing" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
. /etc/hpc-relay/campus.env
set +a
check_active() {
  local state
  state=$(systemctl is-active "$2" 2>/dev/null || true)
  echo "$1: ${state:-unknown}"
  [[ "$state" == active ]]
}
check_active tunnel aws-reverse-tunnel.service || result=1
check_active 'wifi timer' nitj-wifi-ensure.timer || result=1
if [[ "${PORTAL_ENABLED:-1}" == 1 ]]; then
  check_active 'portal timer' nitj-portal.timer || result=1
  if [[ -f /etc/nitj-portal/credentials && "$(stat -c '%a:%U' /etc/nitj-portal/credentials)" == 600:root ]]; then
    echo 'portal credentials: present, root-owned, mode 600'
  else
    echo 'portal credentials: missing or unsafe permissions'
    result=1
  fi
else
  echo 'portal adapter: disabled'
fi
active=$(nmcli --escape no -g GENERAL.CONNECTION device show "${WIFI_IFACE:-}" 2>/dev/null || true)
echo "wifi: ${active:-unknown}"
[[ "$active" == "${WIFI_CONNECTION:-}" ]] || result=1
if [[ -n "${RELAY_HOST:-}" ]] && ssh-keygen -F "$RELAY_HOST" -f /etc/ssh/ssh_known_hosts >/dev/null 2>&1; then
  echo 'relay pin: present'
else
  echo 'relay pin: missing'
  result=1
fi
exit "$result"
