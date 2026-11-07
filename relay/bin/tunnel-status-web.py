#!/usr/bin/env python3
"""Campus tunnel probe, append-only history, and the public status page.

Installed to /usr/local/sbin/tunnel-status-web.py. Mail is sent only when
/etc/relay-status/resend.env names RESEND_API_KEY, RESEND_FROM, and RESEND_TO.
"""

import argparse
import json
import os
import shlex
import socket
import threading
import time
import traceback
import urllib.request
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo(os.environ.get("RELAY_TIMEZONE", "UTC"))
RELAY_PORT = int(os.environ.get("RELAY_PORT", "2222"))
if not 1 <= RELAY_PORT <= 65535:
    raise ValueError("RELAY_PORT must be between 1 and 65535")
INTERVAL = 30
PROBE_TIMEOUT = 5
DAY = 86400
WEEK = 7 * DAY
KEEP = 8 * DAY
STALE_AFTER = 3 * INTERVAL
ENV_FILE = Path("/etc/relay-status/resend.env")
HISTORY = Path("/var/lib/relay-status/history.jsonl")
SUMMARY = Path("/var/lib/relay-status/summary.json")
FONTS = Path(os.environ.get("RELAY_FONT_DIR", "/usr/local/share/relay-fonts"))
ASSETS = Path("/usr/local/share/relay-status")
if not ASSETS.is_dir():
    ASSETS = Path(__file__).resolve().parent.parent / "assets"

lock = threading.Lock()
samples = deque()
since = None
last_up = None
outages = []
view = {}
env = {}

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relay</title>
<style>
  @font-face {
    font-family: Athletics;
    src: url("/fonts/Athletics-Regular.woff2") format("woff2");
    font-weight: 300;
    font-style: normal;
    font-display: swap;
  }
  @font-face {
    font-family: Athletics;
    src: url("/fonts/Athletics-Bold.woff2") format("woff2");
    font-weight: 700;
    font-style: normal;
    font-display: swap;
  }
  :root {
    --bg: #111111;
    --text: #f4f4f4;
    --muted: #8d8d8d;
    --rule: #2c2c2c;
    --accent: #174ea6;
    --down: #c4473d;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--bg); color: var(--text); }
  body {
    font-family: Athletics, sans-serif;
    font-weight: 300;
    font-size: 18px;
    line-height: 1.5;
    min-height: 100svh;
    isolation: isolate;
  }
  .atmosphere {
    position: fixed;
    inset: 0;
    z-index: -1;
    overflow: hidden;
    pointer-events: none;
  }
  main {
    position: relative;
    display: grid;
    grid-template-rows: auto 1fr auto;
    min-height: 100svh;
    padding: clamp(24px, 4vw, 80px);
  }
  .moon {
    position: absolute;
    right: -22vw;
    bottom: -40%;
    width: min(105vw, 1600px);
    aspect-ratio: 1;
    background: url("/assets/moon.webp") center / contain no-repeat;
    opacity: 0.07;
    mask-image: linear-gradient(140deg, transparent 15%, #000 75%);
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 1rem;
  }
  .mark { font-size: 20px; font-weight: 700; }
  time { font-size: 14px; color: var(--muted); text-align: right; }
  .overview {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(240px, 28%);
    align-items: center;
    gap: 8vw;
    padding: clamp(48px, 8vh, 120px) 0;
  }
  h1 {
    margin: 0;
    font-size: clamp(112px, 17vw, 280px);
    font-weight: 700;
    line-height: 0.86;
    letter-spacing: -0.045em;
  }
  h1.down { color: var(--down); }
  .lede { margin: 2rem 0 0; max-width: 34rem; color: var(--muted); }
  .since { margin: 0.8rem 0 0; font-size: 22px; font-weight: 700; }
  .stats { display: grid; align-self: center; }
  .stats > div { padding: 1.5rem 0; border-bottom: 1px solid var(--rule); }
  .stats > div:first-child { padding-top: 0; }
  .stats > div:last-child { padding-bottom: 0; border-bottom: 0; }
  .stats b {
    display: block;
    font-size: clamp(36px, 3.5vw, 56px);
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1.1;
  }
  .stats span { display: block; margin-top: 0.4rem; color: var(--muted); font-size: 14px; }
  .losses { list-style: none; margin: 2rem 0 0; padding: 0; color: var(--muted); font-size: 14px; }
  .losses:empty { display: none; }
  .losses li { margin-top: 0.4rem; }
  .path-heading {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.5rem;
    color: var(--muted);
    font-size: 12px;
  }
  .path {
    list-style: none;
    display: flex;
    align-items: flex-start;
    margin: 0;
    padding: 0;
  }
  .path li {
    flex: 1;
    min-width: 0;
    padding-top: 1.1rem;
    border-top: 1px solid var(--rule);
    position: relative;
  }
  .path li:last-child { border-top-color: transparent; }
  .path li.on { border-top-color: var(--accent); }
  .path li::before {
    content: "";
    position: absolute;
    top: -4px;
    left: 0;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--rule);
  }
  .path li.relay::before, .path li.reachable::before { background: var(--accent); }
  .path li.reachable::before { animation: pulse 1.8s ease-in-out infinite; }
  .path b { display: block; font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }
  .path span { display: block; margin-top: 0.2rem; color: var(--muted); font-size: 14px; }
  @keyframes pulse { 50% { opacity: 0.35; } }
  @media (prefers-reduced-motion: reduce) { .path li.reachable::before { animation: none; } }
  @media (max-width: 720px) {
    main { padding: 24px; }
    time { max-width: 14rem; font-size: 12px; }
    .moon { width: 180vw; right: -70vw; bottom: -30%; opacity: 0.055; }
    .overview { grid-template-columns: 1fr; gap: 2.5rem; padding: 3.5rem 0; }
    h1 { font-size: clamp(104px, 28vw, 180px); }
    .lede { margin-top: 1.5rem; font-size: 16px; }
    .since { font-size: 18px; }
    .losses { margin-top: 1.5rem; font-size: 12px; }
    .stats { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; }
    .stats > div, .stats > div:first-child, .stats > div:last-child { padding: 0; border: 0; }
    .stats b { font-size: 30px; }
    .stats span { font-size: 12px; }
    .path-heading { font-size: 11px; }
    .path b { font-size: 16px; }
    .path span { font-size: 11px; }
  }
  @media (max-width: 360px) {
    main { padding: 20px; }
    .mark { font-size: 18px; }
    time { max-width: 10rem; }
    .stats { gap: 0.75rem; }
    .stats b { font-size: 26px; }
  }
</style>
</head>
<body>
<div class="atmosphere" aria-hidden="true"><div class="moon"></div></div>
<main>
  <header>
    <div class="mark">Relay</div>
    <time id="when">—</time>
  </header>
  <section class="overview" aria-label="Campus tunnel status">
    <div class="status">
      <h1 id="word">…</h1>
      <p class="lede" id="lede">Checking the campus laptop.</p>
      <p class="since" id="since"></p>
      <ul class="losses" id="losses"></ul>
    </div>
    <div class="stats" aria-label="Tunnel history">
      <div><b id="p24">—</b><span id="p24l">24 hours</span></div>
      <div><b id="p7">—</b><span id="p7l">7 days</span></div>
      <div><b id="drops">—</b><span>drops this week</span></div>
    </div>
  </section>
  <footer>
    <div class="path-heading"><span>Connection path</span></div>
    <ol class="path" aria-label="Connection path">
      <li id="n-you"><b>Mac</b><span>Home</span></li>
      <li id="n-relay" class="relay"><b>Relay</b><span>This machine</span></li>
      <li id="n-campus"><b>Campus</b><span>Tunnel probe</span></li>
      <li id="n-hpc"><b>HPC</b><span>Via campus</span></li>
    </ol>
  </footer>
</main>
<script>
function paint(d) {
  if (d.stale || typeof d.tunnel_up !== "boolean") {
    unavailable("The relay has no recent tunnel check.");
    return;
  }
  const up = !!d.tunnel_up;
  const word = document.getElementById("word");
  word.textContent = up ? "up" : "down";
  word.className = up ? "" : "down";
  document.getElementById("lede").textContent = up
    ? "The campus laptop answered the relay."
    : "The relay could not reach the campus laptop.";
  document.getElementById("since").textContent = d.since_label || "";
  document.getElementById("when").textContent = d.checked || "—";
  document.getElementById("p24").textContent = d.pct_24h == null ? "—" : d.pct_24h;
  document.getElementById("p7").textContent = d.pct_7d == null ? "—" : d.pct_7d;
  document.getElementById("drops").textContent = d.drops_7d == null ? "—" : d.drops_7d;
  document.getElementById("p24l").textContent = d.label_24h || "24 hours";
  document.getElementById("p7l").textContent = d.label_7d || "7 days";
  document.getElementById("losses").replaceChildren(...(d.losses || []).map(s => {
    const item = document.createElement("li");
    item.textContent = s;
    return item;
  }));
  document.getElementById("n-relay").classList.toggle("on", up);
  document.getElementById("n-campus").classList.toggle("reachable", up);
}
function unavailable(message) {
  const word = document.getElementById("word");
  word.textContent = "—";
  word.className = "";
  document.getElementById("lede").textContent = message;
  document.getElementById("since").textContent = "";
  document.getElementById("n-relay").classList.remove("on");
  document.getElementById("n-campus").classList.remove("reachable");
}
async function refresh() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch("/api/status", { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Error("Status request failed");
    paint(await response.json());
  }
  catch (e) {
    unavailable("This page could not read the relay.");
  }
  finally { clearTimeout(timeout); setTimeout(refresh, 5000); }
}
refresh();
</script>
</body>
</html>
"""


def now_ts():
    return int(time.time())


def campus_up():
    sock = socket.socket()
    deadline = time.monotonic() + PROBE_TIMEOUT
    sock.settimeout(PROBE_TIMEOUT)
    try:
        sock.connect(("127.0.0.1", RELAY_PORT))
        data = b""
        while b"\n" not in data and len(data) < 128:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            sock.settimeout(remaining)
            chunk = sock.recv(64)
            if not chunk:
                break
            data += chunk
        return data.startswith(b"SSH-") and b"\n" in data
    except OSError:
        return False
    finally:
        sock.close()


def load_env():
    found = {}
    try:
        lines = ENV_FILE.read_text().splitlines()
    except (FileNotFoundError, PermissionError):
        lines = []
    for line in lines:
        if not line.strip() or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        words = shlex.split(value, comments=True)
        if len(words) > 1:
            raise ValueError("Quote mail configuration values containing spaces")
        found[key.strip()] = words[0] if words else ""
    for key in ("RESEND_API_KEY", "RESEND_FROM", "RESEND_TO"):
        if key in os.environ:
            found[key] = os.environ[key]
    return found


def local_time(ts):
    return datetime.fromtimestamp(ts, DISPLAY_TZ)


def fmt_clock(ts):
    return local_time(ts).strftime("%-d %b · %-I:%M %p")


def fmt_checked(ts):
    return local_time(ts).strftime("%-d %b %Y · %-I:%M %p %Z")


def fmt_dur(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, _ = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"


def window_stats(now, span):
    up = n = drops = 0
    prev = None
    previous_ts = None
    for ts, flag in samples:
        if previous_ts is not None and ts - previous_ts > STALE_AFTER:
            prev = None
        previous_ts = ts
        if now - ts > span:
            prev = flag
            continue
        n += 1
        up += flag
        if prev == 1 and flag == 0:
            drops += 1
        prev = flag
    return up, n, drops


def rebuild_outages():
    found = []
    started = None
    previous_ts = None
    for ts, flag in samples:
        if previous_ts is not None and ts - previous_ts > STALE_AFTER:
            started = None
        previous_ts = ts
        if flag == 0 and started is None:
            started = ts
        elif flag == 1 and started is not None:
            found.append((started, ts))
            started = None
    if started is not None:
        found.append((since if last_up == 0 and since is not None else started, None))
    return found[-8:]


def loss_lines(now):
    lines = []
    for start, end in reversed(outages):
        if end is None:
            lines.append(f"{fmt_clock(start)} · still down · {fmt_dur(now - start)}")
        else:
            end_label = (
                local_time(end).strftime("%-I:%M %p")
                if local_time(start).date() == local_time(end).date()
                else fmt_clock(end)
            )
            lines.append(f"{fmt_clock(start)} – {end_label} · {fmt_dur(end - start)}")
    return lines


def pct_label(up, n, span_name, now):
    if n == 0:
        return None, span_name
    pct = f"{100 * up / n:.1f}%"
    if pct.endswith(".0%"):
        pct = pct[:-3] + "%"
    span = DAY if span_name == "24 hours" else WEEK
    covered = n >= span // INTERVAL
    unit = "check" if n == 1 else "checks"
    label = span_name if covered else f"{span_name} · {n} {unit}"
    return pct, label


def publish(now):
    global view
    up24, n24, _ = window_stats(now, DAY)
    up7, n7, drops7 = window_stats(now, WEEK)
    p24, l24 = pct_label(up24, n24, "24 hours", now)
    p7, l7 = pct_label(up7, n7, "7 days", now)
    current = bool(last_up)
    view = {
        "tunnel_up": current,
        "checked": fmt_checked(now),
        "checked_at": samples[-1][0] if samples else None,
        "since_label": f"{'Up' if current else 'Down'} for {fmt_dur(now - since)}" if since else "",
        "pct_24h": p24,
        "label_24h": l24,
        "pct_7d": p7,
        "label_7d": l7,
        "drops_7d": drops7,
        "losses": loss_lines(now),
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(view, separators=(",", ":")).encode()
    tmp = SUMMARY.with_suffix(".json.tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, SUMMARY)


def send_down_email(now, test=False):
    sender = env.get("RESEND_FROM", "").strip()
    recipient = env.get("RESEND_TO", "").strip()
    if not env.get("RESEND_API_KEY") or not sender or not recipient:
        print("email skipped: resend env incomplete", flush=True)
        return False
    when = fmt_checked(now)
    note = (
        "This is a delivery test. No live tunnel check was performed."
        if test
        else "The relay lost the campus laptop."
    )
    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;background:#111111;">
  <div style="max-width:520px;padding:72px 40px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
    <div style="font-size:13px;letter-spacing:0.18em;text-transform:uppercase;color:#8d8d8d;">Relay</div>
    <div style="margin-top:36px;font-size:84px;line-height:0.85;font-weight:700;letter-spacing:-0.045em;color:#c4473d;">Down</div>
    <p style="margin:28px 0 0;font-size:18px;line-height:1.45;color:#f4f4f4;">{note}</p>
    <p style="margin:18px 0 0;font-size:15px;color:#8d8d8d;">{when}</p>
  </div>
</body>
</html>"""
    payload = json.dumps(
        {
            "from": sender,
            "to": [recipient],
            "subject": "Campus laptop unreachable" + (" — test" if test else ""),
            "html": html,
            "text": f"Down\n{note}\n{when}\n",
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {env['RESEND_API_KEY']}",
            "Content-Type": "application/json",
            "User-Agent": "relay-status/1.0",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        print("down email sent", flush=True)
        return True
    except Exception as exc:
        print(f"down email failed: {type(exc).__name__}", flush=True)
        return False


def append_history(now, flag):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("ab+") as handle:
        if handle.tell():
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b"\n":
                handle.write(b"\n")
        handle.write((json.dumps({"t": now, "u": flag}, separators=(",", ":")) + "\n").encode())
        handle.flush()
        os.fsync(handle.fileno())


def sample():
    global since, last_up, outages
    up = campus_up()
    flag = 1 if up else 0
    now = now_ts()
    recent = bool(samples) and 0 <= now - samples[-1][0] <= STALE_AFTER
    lost = recent and last_up == 1 and flag == 0
    with lock:
        append_history(now, flag)
        samples.append((now, flag))
        cutoff = now - KEEP
        while samples and samples[0][0] < cutoff:
            samples.popleft()
        if last_up != flag or since is None or not recent:
            since = now
        last_up = flag
        outages = rebuild_outages()
        publish(now)
    if lost:
        threading.Thread(target=send_down_email, args=(now,), daemon=True).start()


def load_history():
    global since, last_up, outages
    if not HISTORY.exists():
        return
    now = now_ts()
    cutoff = now - KEEP
    previous = None
    run_start = None
    previous_ts = None
    with HISTORY.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                ts, flag = item["t"], item["u"]
                if type(ts) is not int or type(flag) is not int or flag not in (0, 1):
                    continue
                if ts < 0 or ts > now or (previous_ts is not None and ts <= previous_ts):
                    continue
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if previous != flag or previous_ts is None or ts - previous_ts > STALE_AFTER:
                run_start = ts
                previous = flag
            previous_ts = ts
            if ts >= cutoff:
                samples.append((ts, flag))
    if previous is None:
        return
    last_up = previous
    since = run_start
    outages = rebuild_outages()
    publish(previous_ts)


def loop():
    deadline = time.monotonic()
    while True:
        deadline = max(deadline + INTERVAL, time.monotonic())
        time.sleep(max(0, deadline - time.monotonic()))
        try:
            sample()
        except Exception:
            traceback.print_exc()


class StatusHTTPServer(ThreadingHTTPServer):
    """Bound idle connections and concurrent handlers on the small relay."""

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(5)
        return request, address

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            with lock:
                current = dict(view or {"tunnel_up": None, "checked": "—"})
            checked_at = current.get("checked_at")
            current["stale"] = not checked_at or not 0 <= now_ts() - checked_at <= STALE_AFTER
            if current["stale"]:
                current["tunnel_up"] = None
            body = json.dumps(current).encode()
            ctype = "application/json"
        elif path in ("/", "/index.html"):
            body = PAGE.encode()
            ctype = "text/html; charset=utf-8"
        elif path == "/assets/moon.webp":
            moon = ASSETS / "moon.webp"
            if not moon.is_file():
                self.send_error(404)
                return
            body = moon.read_bytes()
            ctype = "image/webp"
        elif path in ("/fonts/Athletics-Regular.woff2", "/fonts/Athletics-Bold.woff2"):
            font = (FONTS / Path(path).name).resolve()
            if font.parent != FONTS.resolve() or not font.is_file():
                self.send_error(404)
                return
            body = font.read_bytes()
            ctype = "font/woff2"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        static = path.startswith("/fonts/") or path == "/assets/moon.webp"
        self.send_header("Cache-Control", "public, max-age=86400" if static else "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, fmt, *args):
        return


def main():
    global env, view
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-email", action="store_true", help="Send a delivery test and exit")
    parser.add_argument(
        "--preview",
        choices=("up", "down"),
        help="Serve sample data without probing or writing history",
    )
    parser.add_argument("--bind", help="HTTP listen address (preview defaults to loopback)")
    parser.add_argument("--port", type=int, help="HTTP port (80, or 8080 for preview)")
    args = parser.parse_args()
    if args.test_email and args.preview:
        parser.error("--test-email and --preview cannot be combined")
    port = (
        args.port
        if args.port is not None
        else int(os.environ.get("RELAY_HTTP_PORT", "8080" if args.preview else "80"))
    )
    if not 1 <= port <= 65535:
        parser.error("HTTP port must be between 1 and 65535")
    bind = args.bind or os.environ.get("RELAY_BIND", "127.0.0.1" if args.preview else "0.0.0.0")
    if args.preview:
        up = args.preview == "up"
        view = {
            "tunnel_up": up,
            "checked": "Design preview · sample data",
            "since_label": "Up for 23m" if up else "Down for 8h 33m",
            "pct_24h": "100%" if up else "5.6%",
            "pct_7d": "100%" if up else "5.6%",
            "label_24h": "24 hours · 50 checks",
            "label_7d": "7 days · 50 checks",
            "drops_7d": 0 if up else 1,
            "losses": [],
        }

        class PreviewHandler(Handler):
            def do_GET(self):
                view["checked_at"] = now_ts()
                super().do_GET()

        print(f"Sample data only: http://{bind}:{port}/", flush=True)
        StatusHTTPServer((bind, port), PreviewHandler).serve_forever()
        return 0
    env = load_env()
    if args.test_email:
        return 0 if send_down_email(now_ts(), test=True) else 1
    load_history()
    try:
        sample()
    except Exception:
        traceback.print_exc()
    threading.Thread(target=loop, daemon=True).start()
    StatusHTTPServer((bind, port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
