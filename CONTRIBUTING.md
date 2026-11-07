# Contributing

Keep the relay and laptop installers separate, retain the loopback listener, and
preserve the client-only private destination key. Changes to unit ordering,
restart limits, portal frequency, host-key handling, or disk boot need an explicit
failure scenario and validation.

Use Python 3.11+ and Bash. Install ShellCheck through your package manager and
`python3 -m pip install -r requirements-dev.txt` into a virtual environment.
Run `scripts/check.sh` before proposing a change. The fast tests alone are
`python3 -m unittest discover -s tests -v`.
Node.js enables the browser-script checks; those tests are reported as skipped
when Node is absent. The runtime web server does not require Node.

Tests must use temporary paths, synthetic host keys, and mocked portal/mail calls.
Do not run installers against a developer's `/etc`, cloud account, or campus
network in CI. Changes to installation still need a disposable Ubuntu VM test;
unit tests cannot verify real Wi-Fi association, firmware boot, or a particular
portal appliance.

Configuration belongs in example files with documentation placeholders. Keep real
deployment notes in `.local/` and never commit private keys, credentials, Resend
keys, or third-party font binaries. The included moon's provenance is documented
under `relay/assets/`.
