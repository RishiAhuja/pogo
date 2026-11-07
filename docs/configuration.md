# Configuration checklist

The public repository contains example addresses and empty credential fields.
Replace them in your deployment copies, rather than putting your real values
back into the public examples. The documented Ubuntu/NITJ setup needs no source
edits. Other portal APIs need an adapted login helper, as explained in the
[portal adapter notes](setup.md#adapting-the-portal-helper).

## Required values

| File | Set these values |
|---|---|
| `config/campus.env.example` → `/etc/hpc-relay/campus.env` on the bastion | `CAMPUS_USER`, `WIFI_IFACE`, `WIFI_CONNECTION`, `RELAY_HOST`, and `TUNNEL_KEY`. The example account, `wlan0`, `Campus Wi-Fi`, `203.0.113.10`, and `/home/campus/...` must match your machines. |
| `mac/ssh_config.snippet` → `~/.ssh/config` on the client | Replace `RELAY_IP`, `CAMPUS_USER`, `HPC_PRIVATE_IP`, and `HPC_USER`. Check `User ubuntu` for the relay admin account. The file also works with Linux OpenSSH. |
| Relay host-key pin | Supply the real relay address and full Ed25519 public-key line to `campus/pin-relay-key.sh`. Verify its fingerprint through a trusted connection first. `AAAA...` in the instructions is an abbreviation, not a key. |
| Relay installation command | Replace `/path/to/ec2_tunnel.pub` with the path to the bastion's tunnel public key. The key helpers generate the keys; do not invent or paste private keys into the repository. |

`RELAY_USER=tunnel` and `RELAY_PORT=2222` are working defaults. If you change the
tunnel account, use the same value for `TUNNEL_USER` during relay installation and
`RELAY_USER` on the bastion. The reverse port must match the relay installer, the
bastion configuration, and the client's `Port` under `Host campus`.

The client aliases `aws-relay`, `campus`, and `hpc` are usable names, not unresolved
placeholders. You can rename them if you update their `ProxyJump` references.
The public relay does not have to run on AWS.

## Optional values

| Feature | Configuration |
|---|---|
| NITJ/Sophos captive portal | For the matching mode-451 login flow, set `PORTAL_ENABLED=1` and replace `PORTAL_GATEWAY=192.0.2.1` in the bastion configuration. Fill `username` and `password` from `config/portal-credentials.example` in root-owned mode-600 `/etc/nitj-portal/credentials`. Other portal flows need an adapter. |
| Private portal CA | Set `PORTAL_CA_FILE` to your trusted CA certificate when needed. Keep `PORTAL_TLS_VERIFY=1`. |
| Wi-Fi SSID override | Set `WIFI_SSID` only if NetworkManager cannot provide the SSID from the saved profile. `WIFI_CONNECTION` is the profile name. |
| Email alerts | Create `/etc/relay-status/resend.env` from `config/resend.env.example`. Supply `RESEND_API_KEY`, a sender configured in Resend, and `RESEND_TO`. Leave the file absent to disable email. |
| Status page | `config/status.env.example` has usable defaults for port, bind address, and UTC. Change `RELAY_TIMEZONE` if wanted. For a TLS proxy, bind the origin to `127.0.0.1` on an appropriate port. |
| HTTPS hostname | Replace `relay.example.com` in the setup guide's Caddy example with your DNS name. Point it at the relay. |
| Athletics fonts | Supply your licensed font directory with `FONT_SRC` during relay installation. `RELAY_FONT_DIR` is available for local previews. System fonts work without either setting. |

The documentation also uses `/path/to/athletics` for rebuilding the README
illustration. It is a local development path, not a runtime requirement.

## Other campus and network settings

The portal adapter is only one part of moving this setup to another network:

| Area | What to configure |
|---|---|
| Wi-Fi authentication | Save a working NetworkManager profile first, including any Wi-Fi password, 802.1X settings, or required certificates. Make sure the profile connects without a desktop prompt. Keep these secrets out of `campus.env`. |
| Portal login flow | Match your institution's endpoint, request format, and session handling. The bundled helper fixes the Sophos port at `4443`; another port or API needs a script change. |
| Portal session lifetime | Adjust `nitj-portal.timer` if your network's session expiry differs from the 30-minute session used in the NITJ setup. Use a refresh interval shorter than the session lifetime, within your institution's limits. |
| MAC address policy | The installer uses the interface's permanent MAC address. If the network registers devices by MAC address, register that address and check that the policy matches your saved profile. |
| Network access | Confirm that the bastion can reach the public relay over SSH and the private destination on its SSH port. The supplied tunnel command uses the configured Wi-Fi interface directly. VPN or proxy-only networks may need changes to that command. |
| Wired connections | The supplied installer and watchdog expect Wi-Fi. Ethernet needs changes to the Wi-Fi preflight, watchdog, and dispatcher. The tunnel also binds to `WIFI_IFACE`, which must match the interface you use. |
| Relay and destination | Set your own relay address, admin account, private destination address, and destination user. Keep the reverse port consistent on the relay, bastion, and client. |

For portal-free networks or authentication handled elsewhere, leave
`PORTAL_ENABLED=0`. Restart the affected services or timers after changing their
installed configuration. Follow the [setup guide](setup.md) for installation
order and the [operations guide](operations.md) for health checks.

## Markers that the installers replace

These are intentional template markers. Do not edit them in the source files:

- `__CAMPUS_USER__` and `__CAMPUS_GROUP__` in the reverse-tunnel service come from
  the configured bastion account and its actual primary group.
- `__TUNNEL_USER__` and `__RELAY_PORT__` in the relay SSH drop-in come from the
  relay installer's values.

Addresses under `192.0.2.0/24` and `203.0.113.0/24`, example email addresses, and
fake keys in tests are documentation or test data. They are not a deployment.
The status page's `--preview` mode also uses sample data deliberately.

Copy the [deployment worksheet](this-deployment.md) to `.local/` for private
records. Keep its empty cells in the public version. Follow the
[setup guide](setup.md) for installation order and file permissions.
