# Design

## SSH path and account boundaries

The campus laptop opens outbound SSH to the public relay and requests
`-N -R 127.0.0.1:2222:127.0.0.1:22`. The client reaches that listener through the
relay's admin account, then uses the laptop as a second jump to the private host.
All destination authentication remains on the client; no agent forwarding is needed.

`GatewayPorts no`, `PermitListen`, and `AllowTcpForwarding remote` constrain the
dedicated tunnel user. `MaxSessions 0` permits forwarding but rejects command,
shell, and subsystem sessions. The relay admin still needs forwarding for
ProxyJump; its permissions are not narrowed to those of the tunnel account.
These semantics are documented in [OpenSSH sshd_config](https://man.openbsd.org/sshd_config).

OpenSSH generally uses the first obtained value. The global settings therefore
live in `00-hpc-relay.conf`, ahead of normal cloud-image drop-ins, and installation
checks effective settings as well as syntax. Unusual earlier configuration can
still conflict; installation fails and restores its drop-in rather than assuming
that writing a file was sufficient. A dedicated relay is the supported baseline.

## Recovery

The SSH client and server exchange 15-second keepalives with a count of three.
A dead connection normally clears in about a minute. This is not a guaranteed
deadline under arbitrary host scheduling or network failure.

The tunnel uses `ExitOnForwardFailure`, `BatchMode`, the configured `BindInterface`,
and an explicitly pinned system host-key file. Systemd restarts it after 20 seconds,
without a start-rate limit. A separate 30-second watchdog also starts an inactive
unit, including one stopped manually. Its timer waits 30 seconds after completion
so a slow Wi-Fi operation does not prevent the next check. For maintenance, stop the watchdog
timer and any running watchdog job before stopping the tunnel.

The watchdog reads the SSID from the saved profile, waits until it is visible,
and connects on the configured interface. The profile name does not need to equal
the SSID. Portal work is only attempted on the configured profile and all callers
share the same lock and minimum gap. The NetworkManager dispatcher schedules the
watchdog asynchronously instead of blocking a dispatcher callback on HTTPS.

## Portal adapter

The optional adapter targets one configured Sophos mode-451 gateway. It verifies
TLS by default, can trust a supplied CA, disables environment HTTP proxies, and
rejects redirects. Disabling certificate verification is an explicit legacy
configuration choice, not a safe default. The profile is checked again after
acquiring the lock, because the interface may have changed while waiting.

Credentials use a literal `key=value` file, not shell syntax. Campus configuration
uses quoted literal shell assignments; the Python reader parses those quotes.
Other appliances need a separate adapter. The 25-minute timer is specific to the
observed 30-minute session, not a discovered property of every Sophos deployment.

## Status and persistence

The relay reads a complete SSH banner through the loopback reverse port. A socket
that merely listens is not enough. The connect and read operations share one
five-second deadline, so a slow partial banner cannot prolong a single probe
indefinitely. The cluster itself is not probed.

Samples are compact JSON lines `{ "t": <unix-seconds>, "u": 0|1 }`, appended and
fsynced before the in-memory state advances. Eight days are retained in memory;
the on-disk log is append-only and grows by tens of megabytes per year. A truncated
last record is separated from the next append, and the loader skips invalid,
future, duplicate, and out-of-order rows. Disk errors are logged; stale data does
not continue claiming that the tunnel is up.

The HTTP handler serves a small in-memory summary. It never parses the history
file on a request. `summary.json` is an atomic exported snapshot; startup rebuilds
from history rather than trusting that snapshot. Percentages count observed up
samples. A window is only labeled complete when it has enough checks. Monitoring
gaps reset the current run and do not fabricate continuous uptime or a drop.

A check older than 90 seconds yields `stale: true` and `tunnel_up: null`; the page
shows unknown. A failed HTTP request or timeout also clears the live indicator.
The polling loop waits for each request before scheduling another.

Mail is attempted asynchronously for a contiguous up-to-down transition. It
cannot delay the probe loop. A gap before restart does not create a new outage
alert from an ancient up sample. Delivery failures are logged, with no durable
retry queue; this is a personal status page, not a paging platform.

## Web process

The web service runs as an unprivileged system user. Systemd grants only the
ability to bind a low port and write its state directory. Root reads the mail env
file for the service. HTTP handlers have a concurrency cap and idle socket
timeouts, and static files have explicit routes. These limits do not make the
standard-library server a replacement for an internet-facing reverse proxy.

The page has no build pipeline, remote image request, analytics, or frontend
package dependency. The moon is a local decorative WebP; it is unrelated to the
actual lunar phase or the tunnel state.

## Boot

The regular installer disables sleep and configures the lid for an always-on
laptop. It does not restart logind, enable desktop autologin, or modify disk
unlock. Those last two actions are independent opt-ins. The disk helper has a
narrow dracut scope and does not claim to support arbitrary initramfs builders,
LVM layouts, distributions, or secure-boot policies. Read setup before using it.
