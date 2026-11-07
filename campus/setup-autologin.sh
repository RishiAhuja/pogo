#!/bin/bash
# Skip the GDM password prompt for the campus user.
# The account password is left in place. sudo still needs it.
# The tunnel does not need this. It is only so a reboot does not sit at the login screen.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the campus laptop." >&2
  exit 1
fi
if [[ ! -f /etc/hpc-relay/campus.env ]]; then
  echo "Missing /etc/hpc-relay/campus.env" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. /etc/hpc-relay/campus.env
set +a
: "${CAMPUS_USER:?}"
if [[ ! "$CAMPUS_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || ! id "$CAMPUS_USER" >/dev/null 2>&1; then
  echo "CAMPUS_USER must name an existing local account." >&2
  exit 1
fi

python3 - "$CAMPUS_USER" <<'PY'
import sys
from pathlib import Path

user = sys.argv[1]
path = Path("/etc/gdm3/custom.conf")
if not path.exists():
    print("No /etc/gdm3/custom.conf. Desktop autologin was not changed.")
    raise SystemExit(0)

backup = path.with_name("custom.conf.bak-autologin")
if not backup.exists():
    backup.write_text(path.read_text())

lines = path.read_text().splitlines()
out = []
in_daemon = False
seen_daemon = False
saw_enable = False
saw_user = False


def finish_section():
    if not saw_enable:
        out.append("AutomaticLoginEnable=true")
    if not saw_user:
        out.append(f"AutomaticLogin={user}")


for line in lines:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        if in_daemon:
            finish_section()
        in_daemon = stripped.lower() == "[daemon]"
        if in_daemon:
            seen_daemon = True
            saw_enable = False
            saw_user = False
        out.append(line)
        continue
    key = stripped.split("=", 1)[0].strip()
    if in_daemon and key == "AutomaticLoginEnable":
        out.append("AutomaticLoginEnable=true")
        saw_enable = True
        continue
    if in_daemon and key == "AutomaticLogin":
        out.append(f"AutomaticLogin={user}")
        saw_user = True
        continue
    out.append(line)

if in_daemon:
    finish_section()
if not seen_daemon:
    if out and out[-1] != "":
        out.append("")
    out.extend(["[daemon]", "AutomaticLoginEnable=true", f"AutomaticLogin={user}"])

path.write_text("\n".join(out) + "\n")
print(f"GDM will log in {user} automatically. The account password was not removed.")
PY
