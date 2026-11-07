# Setup

This guide follows the Ubuntu Wi-Fi setup used at NIT Jalandhar (NITJ). That
network uses a captive portal, and Pogo includes an optional script for its
Sophos login flow. At another college, configure your own network profile and
adapt the portal helper if needed. The reverse SSH tunnel does not depend on
the Sophos helper.

Run the relay installer on the relay and the campus installer on the laptop.
Neither installer provisions cloud infrastructure. They change system services;
use dedicated machines and keep a working admin session or console available.
No installer reboots a machine.

## 1. Dependencies

On both Ubuntu 24.04 machines:

```bash
sudo apt-get update
sudo apt-get install openssh-server openssh-client python3 curl tzdata
```

On the campus laptop:

```bash
sudo apt-get install network-manager iw rfkill util-linux
```

NetworkManager must actually manage the Wi-Fi interface. Join the campus network
once and save a working profile. Use `nmcli device status` for the interface name
and `nmcli connection show` for the **profile** name; the profile and SSID may differ.
The watchdog reads the SSID from the profile, or from optional `WIFI_SSID`.

## 2. Client keys

On your Mac or Linux client:

```bash
mac/make-keys.sh
```

This creates `~/.ssh` if needed, never replaces existing keys, and prompts for a
passphrase on new client keys. Use an SSH agent or enter the passphrase when
connecting. `--no-passphrase` is an explicit opt-in for unattended client use.
Only the separate laptop tunnel key needs to work unattended at boot.

| Public key | Install on |
|---|---|
| `~/.ssh/hpc_relay.pub` | Relay admin account, normally `ubuntu` |
| `~/.ssh/hpc_campus.pub` | Campus user's `~/.ssh/authorized_keys` |
| `~/.ssh/hpc_cluster.pub` | Private destination account's `~/.ssh/authorized_keys` |

Install public keys through existing authorized access. Never copy these private
keys to another machine. Use mode 700 for `.ssh` and mode 600 for `authorized_keys`.

## 3. Prepare the campus configuration and tunnel key

The campus account must already exist. As root on the laptop:

```bash
sudo install -d -m 755 /etc/hpc-relay
sudo install -m 644 config/campus.env.example /etc/hpc-relay/campus.env
sudoedit /etc/hpc-relay/campus.env
```

Replace the example user, interface, Wi-Fi profile, relay address, and key path.
These are trusted shell configuration files: use literal assignments, quote
values containing spaces, and do not use variable expansion or commands. The
Python portal reader also accepts those literal quotes. Keep the file root-owned
and not writable by other users. Do not put passwords in it.

As the configured campus user:

```bash
campus/make-tunnel-key.sh
```

That creates a separate unencrypted key for the outbound tunnel. Copy **only its
public key** to the relay. The private key remains on the laptop.

## 4. Prepare and install the relay

Use a stable public address. On AWS, associate an Elastic IP; another provider's
stable address works too. Allow inbound TCP 22 from the campus and client network
addresses (or the internet if those addresses cannot be predicted). Allow TCP 80
for the default status page. Do not open the reverse tunnel port publicly.

Before installation, verify that the non-root relay admin account accepts your
client public key and can use sudo. Keep that SSH session open. The installer
turns off password, keyboard-interactive, and root SSH login.

Copy this repository, or the entire `relay/` directory, onto the relay:

```bash
sudo ./relay/install.sh /path/to/ec2_tunnel.pub
```

The installer validates the public key, installs an early OpenSSH drop-in, checks
syntax **and effective settings**, and reloads SSH. Its drop-in is restored if
validation or reload fails. The dedicated `tunnel` account may create only the
loopback reverse listener; shell/SFTP sessions and local forwarding are denied.

The web service runs as `relay-status`, with a writable state directory and a
read-only system filesystem. Its source, image, and unit are installed together,
and an existing page service is restarted. Other existing tunnel connections
are not restarted by the web service.

Optional installer variables:

```bash
sudo TUNNEL_USER=tunnel RELAY_PORT=2222 ./relay/install.sh /path/to/ec2_tunnel.pub
```

Use the same reverse port in the campus env file and the client's `Port` entry.
The installer records it for the relay probe. Omit the public-key argument on
later installs to keep `authorized_keys`; supplying it replaces that file.

Web settings live in `/etc/relay-status/status.env` (example:
`config/status.env.example`). Set `RELAY_TIMEZONE=Asia/Kolkata` if desired; UTC is
the default. Restart `tunnel-status-web.service` after editing web settings.
Changing the tunnel port also requires re-running the relay installer to update
its SSH permissions, then updating the laptop and client.

`FONT_SRC` is optional and must contain Athletics-Regular.woff2 and
Athletics-Bold.woff2. Otherwise the system-font fallback is used.
For a local preview, optional `RELAY_FONT_DIR` can point to your licensed font
directory without copying those files into the repository.

## 5. Pin the relay host key

Obtain the relay's Ed25519 fingerprint from its trusted console or an already
verified admin connection:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

On the laptop, scan the public host key and compare the fingerprint:

```bash
ssh-keyscan -t ed25519 RELAY_IP | ssh-keygen -lf -
```

A scan alone does not establish trust. After matching, pin the complete key line
(without a comment) on the laptop:

```bash
sudo ./campus/pin-relay-key.sh 'RELAY_IP ssh-ed25519 AAAA...'
```

The service uses `/etc/ssh/ssh_known_hosts`, rejects a changed key, and never
accepts a new one interactively.

## 6. Optional Sophos portal

The bundled [`nitj-portal-login`](../campus/rootfs/usr/local/sbin/nitj-portal-login)
script was written for the captive portal in the NITJ setup. It authenticates
to a Sophos user portal at `https://PORTAL_GATEWAY:4443/userportal/Controller`
using mode `451`. This is a specific login flow, not a general captive-portal
client. Another college may use different endpoints, request fields, or session
handling, even if it also uses Sophos.

Leave `PORTAL_ENABLED=0` if there is no portal, the network is authenticated by
another mechanism, or your portal uses a different API. You can run the tunnel
without this script once the bastion has network access. For another portal,
prepare a compatible adapter before enabling portal automation.

For Sophos mode 451, set `PORTAL_ENABLED=1` and the exact `PORTAL_GATEWAY`. The
adapter only sends credentials to that host, while the configured Wi-Fi profile
is active. It does not guess a gateway or follow HTTP redirects.

```bash
sudo install -d -m 755 /etc/nitj-portal
sudo install -m 600 -o root -g root /dev/null /etc/nitj-portal/credentials
sudoedit /etc/nitj-portal/credentials
```

Use `config/portal-credentials.example`: literal values after `=`, without
surrounding quotes. Passwords may contain spaces, hashes, equals signs, or quotes.
The file is not executed as a shell script.

TLS verification is **on**. For a private appliance CA, install its certificate
and set `PORTAL_CA_FILE` to that file. Legacy appliances can explicitly opt out
with `PORTAL_TLS_VERIFY=0`; that makes the login vulnerable to an impersonated
portal, so prefer installing the trusted CA. Existing hand-installed setups
that skipped verification must choose a CA or explicitly configure that opt-out.

Every caller shares a 90-second minimum gap, including the 25-minute timer.
That refresh interval was chosen for a 30-minute Sophos session; adjust the timer
if your administrator specifies a different expiry. Incorrect credentials still
need to be corrected manually and can cause an account lockout.

### Adapting the portal helper

For a similar username/password portal, start with the script's `login()`
function. Adapt the URL, port, request fields, cookies or tokens, and response
handling to your college's documented login flow. `PORTAL_GATEWAY` accepts only
a hostname or IP address; the port and request format are part of the script.
Normalize successful authentication to `200`, which the existing wrapper expects.

Keep the configured-network check, restricted credential file, TLS verification,
and shared lock and rate limit around the login request. Adjust the refresh
interval in `nitj-portal.timer` to the session lifetime on your network. The
bundled 25-minute interval comes from the NITJ setup's 30-minute session.

Keep your adapted source in your fork before running `campus/install.sh`.
Installation copies the helper onto the bastion, and reinstallation copies it
again. If you replace the helper entirely, update the installer validation,
portal service, and Wi-Fi watchdog to use its configuration and entry point.
The bundled helper does not implement SSO, MFA, or interactive browser login.
For those networks, use the authentication method supported by your institution.

## 7. Install the campus side

With the tunnel key, saved Wi-Fi profile, relay pin, and any portal credentials
already in place:

```bash
sudo ./campus/install.sh /etc/hpc-relay/campus.env
sudo ./campus/check.sh
```

Missing prerequisites fail before services are replaced. The installer uses the
campus user's primary group; it does not assume that group has the same name.
It sets campus Wi-Fi autoconnect priority, permanent MAC, power-save settings,
persistent bounded journaling, and sleep/lid settings for an always-on laptop.
It does not restart logind or delete other saved networks. Lid settings apply on
the next boot. The portal timer is disabled when the adapter is disabled.

On the relay, `sudo ./relay/check.sh` should now say `campus: up`.
Checks exit nonzero when unhealthy. Check the laptop journal if the tunnel does
not start; do not attempt a remote reboot to fix an unknown configuration error.

The tunnel account intentionally rejects `ssh tunnel@RELAY_IP true`.
Validate it through the running reverse tunnel and health checks instead.

## 8. Configure the client and private destination

Append `mac/ssh_config.snippet` once to your client's `~/.ssh/config`. Replace
`RELAY_IP`, `CAMPUS_USER`, `HPC_USER`, and `HPC_PRIVATE_IP`; adjust the relay
admin username and reverse port if necessary.

Verify the laptop's host-key fingerprint from a trusted local session before
accepting the first `ssh campus` prompt. `HostKeyAlias campus-bastion` separates
that identity from other localhost services. Verify the destination's host key
before accepting its first prompt as well.

```bash
ssh campus
ssh hpc
```

On the destination, verify `hostname` and `whoami`. The last hop is authenticated
by the client, not by copying its private key to the laptop or relay.

## 9. Optional email

On the relay, create root-owned mode-600 `/etc/relay-status/resend.env` from
`config/resend.env.example`. Use a sender domain configured in Resend. Quote a
sender containing spaces, for example `RESEND_FROM='Relay <relay@example.com>'`.
Systemd reads the private env file and passes the values to the unprivileged
service; the web process does not need permission to read that file directly.

```bash
sudo systemctl restart tunnel-status-web.service
sudo python3 /usr/local/sbin/tunnel-status-web.py --test-email
```

The test checks delivery, not the live tunnel. A failed or unconfigured delivery
returns nonzero. Real alerts are attempted on a fresh up-to-down transition;
mail failures are logged and do not block probes. There is no recovery mail or
durable mail retry queue.

## 10. Optional unattended boot

The tunnel starts without a desktop login once userspace and networking are up.
GDM autologin is optional convenience, not a tunnel requirement. The helper
supports `/etc/gdm3/custom.conf` and leaves the account password intact.

Encrypted root still requires an unlock mechanism before systemd can run.
`campus/setup-luks-keyfile.sh` is an **advanced opt-in**, limited to dracut with
`/boot/initrd.img-<kernel>` and one LUKS mapping under root. It refuses the
initramfs-tools fallback: that fallback previously could claim success without
including the key. It keeps the passphrase slot and verifies the actual key bytes
in the rebuilt initrd for the running kernel only.

Embedding the key in an unencrypted boot partition means someone with physical
disk access may recover it. This is not protection against physical theft.
Consider a distribution-supported TPM/unlock solution instead. Keep a recovery
passphrase and console access; do not try this remotely on an unattended machine.

```bash
sudo ./campus/setup-luks-keyfile.sh           # Inspect only
sudo ./campus/setup-luks-keyfile.sh --apply   # Explicitly enroll/rebuild
```

Other kernels, if installed, are not rebuilt. A backup image is not a guarantee
of a working firmware recovery entry. Test one reboot while present. Whether a
laptop powers on after AC returns is a firmware/hardware property.

## HTTPS

The origin can run as plain HTTP behind a TLS reverse proxy. In
`/etc/relay-status/status.env`, set `RELAY_BIND=127.0.0.1` and
`RELAY_HTTP_PORT=8080`, then restart the page. A Caddyfile can contain:

```caddyfile
relay.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Point the hostname at the relay and allow ports 80 and 443 to Caddy. The reverse
SSH listener stays private. Follow the [Caddy reverse-proxy documentation](https://caddyserver.com/docs/quick-starts/reverse-proxy)
for installation and certificate requirements. A CDN or reverse proxy is not
inherently incompatible with this application; avoid caching `/api/status`.
