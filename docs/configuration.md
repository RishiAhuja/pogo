# Configuration checklist

The public repository contains example addresses and empty credential fields.
Replace them in your deployment copies, rather than putting your real values
back into the public examples. No application source edits are needed for the
documented setup.

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
| Sophos captive portal | Set `PORTAL_ENABLED=1` and replace `PORTAL_GATEWAY=192.0.2.1` in the bastion configuration. Fill `username` and `password` from `config/portal-credentials.example` in root-owned mode-600 `/etc/nitj-portal/credentials`. Leave the adapter disabled if it does not apply. |
| Private portal CA | Set `PORTAL_CA_FILE` to your trusted CA certificate when needed. Keep `PORTAL_TLS_VERIFY=1`. |
| Wi-Fi SSID override | Set `WIFI_SSID` only if NetworkManager cannot provide the SSID from the saved profile. `WIFI_CONNECTION` is the profile name. |
| Email alerts | Create `/etc/relay-status/resend.env` from `config/resend.env.example`. Supply `RESEND_API_KEY`, a sender configured in Resend, and `RESEND_TO`. Leave the file absent to disable email. |
| Status page | `config/status.env.example` has usable defaults for port, bind address, and UTC. Change `RELAY_TIMEZONE` if wanted. For a TLS proxy, bind the origin to `127.0.0.1` on an appropriate port. |
| HTTPS hostname | Replace `relay.example.com` in the setup guide's Caddy example with your DNS name. Point it at the relay. |
| Athletics fonts | Supply your licensed font directory with `FONT_SRC` during relay installation. `RELAY_FONT_DIR` is available for local previews. System fonts work without either setting. |

The documentation also uses `/path/to/athletics` for rebuilding the README
illustration. It is a local development path, not a runtime requirement.

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
