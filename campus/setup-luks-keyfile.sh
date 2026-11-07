#!/bin/bash
# Let the next boot unlock the root disk without typing the passphrase.
#
# The passphrase slot is kept. This does not decrypt the disk.
# An older installed kernel is left alone, so it still asks for the passphrase
# if the new initrd fails.
#
#   sudo ./setup-luks-keyfile.sh           # show the disk it found
#   sudo ./setup-luks-keyfile.sh --apply   # add the key, from a terminal
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the campus laptop." >&2
  exit 1
fi

apply=0
if [[ "${1:-}" == "--apply" ]]; then
  apply=1
elif [[ -n "${1:-}" ]]; then
  echo "Usage: sudo $0 [--apply]" >&2
  exit 1
fi
for command in findmnt lsblk cryptsetup python3; do
  command -v "$command" >/dev/null 2>&1 || { echo "Missing $command" >&2; exit 1; }
done
if [[ "$apply" == 1 ]]; then
  for command in dracut lsinitrd cmp; do
    command -v "$command" >/dev/null 2>&1 || { echo "This optional helper supports dracut only; missing $command. No changes made." >&2; exit 1; }
  done
  if [[ ! -f "/boot/initrd.img-$(uname -r)" ]]; then
    echo "Only the /boot/initrd.img-<kernel> layout is supported. No changes made." >&2
    exit 1
  fi
fi

root_src=$(findmnt -nro SOURCE /)
root_src=${root_src%%\[*}
crypt_name=$(lsblk -nro NAME,TYPE -s "$root_src" | awk '$2=="crypt" {print $1; exit}')
if [[ -z "$crypt_name" ]]; then
  echo "Root ($root_src) is not sitting on a LUKS device. Nothing to do." >&2
  exit 1
fi

count=$(lsblk -nro NAME,TYPE -s "$root_src" | awk '$2=="crypt"' | wc -l)
if [[ "$count" -ne 1 ]]; then
  echo "Expected one LUKS device under root, found $count. Stop." >&2
  exit 1
fi

disk=$(cryptsetup status "$crypt_name" | awk -F: '/^[[:space:]]*device:/ {gsub(/[[:space:]]/, "", $2); print $2; exit}')
uuid=$(cryptsetup luksUUID "$disk")
mapper=$(cryptsetup status "$crypt_name" | awk 'NR==1 {print $1; exit}')
name=$(basename "$mapper")
key="/etc/cryptsetup-keys.d/${name}.key"

echo "Root:     $root_src"
echo "LUKS:     $name"
echo "Disk:     $disk"
echo "UUID:     $uuid"
echo "Keyfile:  $key"
echo "Initrd:   /boot/initrd.img-$(uname -r)"

if [[ "$apply" -ne 1 ]]; then
  echo
  echo "No change made. Re-run with --apply from a terminal to add the keyfile."
  echo "The current passphrase stays enrolled. The disk stays encrypted."
  exit 0
fi

install -d -m 0700 /etc/cryptsetup-keys.d
if [[ -f "$key" ]]; then
  if ! cryptsetup open --test-passphrase --key-file "$key" --keyfile-size 512 "$disk"; then
    echo "$key exists but does not unlock $disk. It was left untouched." >&2
    exit 1
  fi
  echo "Keyfile already unlocks the disk."
else
  if [[ ! -t 0 ]]; then
    echo "Run --apply from a terminal. cryptsetup has to ask for the current passphrase." >&2
    exit 1
  fi
  dd if=/dev/urandom of="$key" bs=512 count=1 status=none
  chmod 0400 "$key"
  echo "Enter the existing LUKS passphrase. It remains a backup slot."
  if ! cryptsetup luksAddKey --new-keyfile-size 512 "$disk" "$key"; then
    rm -f "$key"
    echo "Key enrollment failed; the new, unenrolled keyfile was removed." >&2
    exit 1
  fi
  cryptsetup open --test-passphrase --key-file "$key" --keyfile-size 512 "$disk"
fi

crypttab=/etc/crypttab
if [[ -f "$crypttab" && ! -f /etc/crypttab.bak-passprompt ]]; then
  cp -a "$crypttab" /etc/crypttab.bak-passprompt
fi

python3 - "$uuid" "$key" "$name" <<'PY'
import sys
from pathlib import Path

uuid, keyfile, name = sys.argv[1:]
path = Path("/etc/crypttab")
text = path.read_text() if path.exists() else ""
out = []
found = False
for line in text.splitlines():
    raw = line.strip()
    if not raw or raw.startswith("#"):
        out.append(line)
        continue
    parts = raw.split()
    token = parts[1] if len(parts) > 1 else ""
    if token in (f"UUID={uuid}", uuid) or parts[0] == name:
        opts = parts[3].split(",") if len(parts) > 3 else ["luks"]
        for need in ("keyfile-size=512", "x-initrd.attach"):
            if need not in opts:
                opts.append(need)
        out.append(f"{parts[0]} UUID={uuid} {keyfile} {','.join(opts)}")
        found = True
    else:
        out.append(line)
if not found:
    out.append(f"{name} UUID={uuid} {keyfile} luks,keyfile-size=512,x-initrd.attach")
tmp = path.with_name("crypttab.hpc-relay.tmp")
tmp.write_text("\n".join(out) + "\n")
tmp.chmod(0o644)
tmp.replace(path)
PY

install -d -m 755 /etc/dracut.conf.d
printf 'install_items+=" %s "\n' "$key" > /etc/dracut.conf.d/luks-key.conf

kver=$(uname -r)
initrd="/boot/initrd.img-${kver}"
if [[ -f "$initrd" && ! -f "${initrd}.bak-passprompt" ]]; then
  cp -a "$initrd" "${initrd}.bak-passprompt"
fi
dracut -f "$initrd" "$kver"
chmod 600 "$initrd"

if ! lsinitrd -f "${key#/}" "$initrd" | cmp -s "$key" -; then
  echo "The new initrd does not contain the expected key bytes. Do not reboot yet." >&2
  exit 1
fi

echo
echo "Root will unlock from the keyfile on the next boot of kernel $kver."
echo "The passphrase still works. Other kernels, if installed, were not rebuilt:"
for other in /boot/initrd.img-*; do
  if [[ -f "$other" && "$other" != *"$kver"* ]]; then
    printf '%s\n' "$other"
  fi
done
echo "Do not decrypt the disk in place. A power loss during that has no console, and the neighboring partitions leave no spare room."
