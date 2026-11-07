# Operations

## Check the path

From the client, `ssh hpc` is the end-to-end check. The public page only checks
the campus laptop's SSH banner. On the relay, run `sudo ./relay/check.sh`; on the
laptop, run `sudo ./campus/check.sh`. Both return nonzero when unhealthy.

```bash
journalctl -u aws-reverse-tunnel.service -n 50 --no-pager
journalctl -u nitj-wifi-ensure.service -n 50 --no-pager
journalctl -u nitj-portal.service -n 50 --no-pager
```

The boot oneshot being inactive after successful completion is normal. The tunnel
and enabled timers should remain active. A disabled portal adapter does not need
portal credentials or an active portal timer.

## Down or unknown

For **down**, check power, visible campus Wi-Fi, portal credentials/session, relay
host-key pin, and the reverse listener, in that order. On the relay,
`sudo ss -ltnp` shows the loopback listener. The cloud firewall must not publish it.

For **unknown**, inspect `journalctl -u tunnel-status-web.service`: the page may
be unable to get a fresh probe, write history, or read its API. A paused process
or full state filesystem must not be mistaken for a continuously healthy tunnel.
Old percentages are historical samples, not a live reachability test.

`portal_skip recent` means the minimum gap prevented another attempt.
`portal_skip not-on-campus-wifi` means no credentials were sent on that profile.
`portal_skip disabled` means the adapter is intentionally off.
`portal_status 200` indicates a successful Sophos response. Exception **classes**
are logged without passwords or response bodies. Fix wrong credentials instead
of repeatedly forcing login attempts.

## Maintenance and updates

The watchdog restarts a manually stopped tunnel. For maintenance:

```bash
sudo systemctl stop nitj-wifi-ensure.timer
sudo systemctl stop nitj-boot.service nitj-wifi-ensure.service
sudo systemctl stop aws-reverse-tunnel.service
```

Restore with `sudo systemctl start aws-reverse-tunnel.service nitj-wifi-ensure.timer`.
A Wi-Fi dispatcher event can schedule the watchdog while the network changes;
avoid changing network state during a planned stop.

Keep your deployment values outside the public tree. Before migrating an older
hand installation, create the campus env file, explicitly select portal behavior
and TLS trust, and verify the relay fingerprint. The installer now restricts the
tunnel account, so commands such as `ssh tunnel@relay true` are expected to fail.
Do not append the client SSH snippet twice.

Re-running the relay installer replaces its code/assets and restarts the page.
It preserves tunnel authorized keys unless a public-key argument is supplied.
The campus installer updates and restarts its services/timers. Neither installer
updates a running machine merely because files in this repository were edited.

## Mail

```bash
sudo python3 /usr/local/sbin/tunnel-status-web.py --test-email
```

This sends a delivery test without binding HTTP or changing tunnel state. It
does not assert that the laptop is up. Missing mail configuration and delivery
failure return nonzero. Restart the service after changing its env files.
There is one attempt per fresh drop; inspect the journal for failures. No recovery
mail or durable retry queue is provided.

## Replace a relay or rotate its host key

Verify the new fingerprint through a trusted channel, update `RELAY_HOST` if
needed, re-run `campus/pin-relay-key.sh`, and restart the tunnel. Update the
client's `aws-relay` entry and its known-hosts record only after verification.
Moving a stable public IP alone does not preserve the old machine's host key.

## History

`/var/lib/relay-status/history.jsonl` is the source of truth. `summary.json` is an
exported snapshot. Do not parse or rewrite history on each HTTP request. For
manual retention work, stop the page, make a backup, trim complete old lines,
keep ownership `relay-status:relay-status` and mode 640, then restart. Trimming
old records may shorten a reconstructed run; do not claim missing history as up.

## Reboot

The tunnel starts at multi-user boot independently of GDM. Verify disk unlock,
networking, and one full reboot while console access is available. Firmware power
restore and physical disk-key protection are outside the regular installer.
