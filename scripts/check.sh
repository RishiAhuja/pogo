#!/bin/bash
# Run from any directory. No live services or credentials are used.
set -euo pipefail
cd "$(dirname "$0")/.."
for command in python3 shellcheck ruff; do
  command -v "$command" >/dev/null 2>&1 || { echo "Missing $command; see CONTRIBUTING.md." >&2; exit 1; }
done
ruff check . campus/rootfs/usr/local/sbin/nitj-portal-login
ruff format --check . campus/rootfs/usr/local/sbin/nitj-portal-login
while IFS= read -r -d '' file; do
  bash -n "$file"
  shellcheck "$file"
done < <(python3 - <<'PY'
from pathlib import Path
import sys
for root in ('campus', 'relay', 'mac', 'scripts'):
    for path in sorted(Path(root).rglob('*')):
        if path.is_file() and (path.suffix == '.sh' or path.read_bytes().startswith(b'#!/bin/bash')):
            sys.stdout.buffer.write(str(path).encode() + b'\0')
PY
)
python3 -m unittest discover -s tests -v
