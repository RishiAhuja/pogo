#!/bin/bash
# Read-only check. Exits nonzero if the service, API, or tunnel is unhealthy.
set -u
set -a
if [[ -f /etc/relay-status/status.env ]]; then
  # shellcheck disable=SC1091
  . /etc/relay-status/status.env
fi
set +a
result=0
state=$(systemctl is-active tunnel-status-web.service 2>/dev/null || true)
echo "status page: ${state:-unknown}"
[[ "$state" == active ]] || result=1
if command -v curl >/dev/null 2>&1; then
  curl -fsS --max-time 5 "http://127.0.0.1:${RELAY_HTTP_PORT:-80}/api/status" || result=1
  echo
else
  echo "curl is missing" >&2
  result=1
fi
if ! python3 - <<'PROBE'
import os
import socket
import sys
import time
up = False
deadline = time.monotonic() + 5
try:
    with socket.create_connection(('127.0.0.1', int(os.environ.get('RELAY_PORT', '2222'))), timeout=5) as sock:
        data = b''
        while b'\n' not in data and len(data) < 128:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            chunk = sock.recv(64)
            if not chunk:
                break
            data += chunk
        up = data.startswith(b'SSH-') and b'\n' in data
except (OSError, ValueError):
    pass
print('campus:', 'up' if up else 'down')
sys.exit(0 if up else 1)
PROBE
then
  result=1
fi
if [[ "$(id -u)" -eq 0 ]]; then
  if settings=$(sshd -T); then
    awk 'tolower($1) ~ /^(gatewayports|clientaliveinterval|clientalivecountmax|passwordauthentication|permitrootlogin)$/' <<< "$settings"
  else
    result=1
  fi
fi
exit "$result"
