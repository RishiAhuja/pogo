import importlib.util
import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_status():
    spec = importlib.util.spec_from_file_location(
        "relay_status", ROOT / "relay/bin/tunnel-status-web.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Request:
    def __init__(self, path, method="GET"):
        self.reader = BytesIO(f"{method} {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode())
        self.response = bytearray()

    def makefile(self, *args):
        return self.reader

    def sendall(self, data):
        self.response.extend(data)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.module = load_status()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.module.HISTORY = Path(self.tmp.name) / "history.jsonl"
        self.module.SUMMARY = Path(self.tmp.name) / "summary.json"
        self.module.ENV_FILE = Path(self.tmp.name) / "resend.env"
        self.module.ASSETS = ROOT / "relay/assets"
        self.module.FONTS = Path(self.tmp.name) / "fonts"

    def request(self, path, method="GET"):
        req = Request(path, method)
        self.module.Handler(req, ("127.0.0.1", 1234), object())
        return bytes(req.response).split(b"\r\n\r\n", 1)

    def test_stale_status_is_unknown(self):
        self.module.view = {"tunnel_up": True, "checked_at": 1000}
        with patch.object(self.module, "now_ts", return_value=1100):
            headers, body = self.request("/api/status")
        self.assertIn(b"no-store", headers)
        self.assertTrue(json.loads(body)["stale"])
        self.assertIsNone(json.loads(body)["tunnel_up"])

    def test_recent_status_remains_up(self):
        self.module.view = {"tunnel_up": True, "checked_at": 1000}
        with patch.object(self.module, "now_ts", return_value=1030):
            _, body = self.request("/api/status")
        self.assertTrue(json.loads(body)["tunnel_up"])
        self.assertFalse(json.loads(body)["stale"])

    def test_asset_and_head(self):
        headers, body = self.request("/assets/moon.webp")
        self.assertIn(b"Content-Type: image/webp", headers)
        self.assertIn(b"max-age=86400", headers)
        self.assertEqual(body, (ROOT / "relay/assets/moon.webp").read_bytes())
        head_headers, head_body = self.request("/assets/moon.webp", "HEAD")
        self.assertEqual(headers, head_headers)
        self.assertEqual(head_body, b"")

    def test_unknown_assets_and_traversal_are_rejected(self):
        for path in (
            "/assets/README.md",
            "/assets/../README.md",
            "/fonts/../../etc/passwd",
            "/fonts/secret.woff2",
        ):
            with self.subTest(path=path):
                headers, _ = self.request(path)
                self.assertIn(b"404 Not Found", headers)

    def test_font_symlink_cannot_escape_font_directory(self):
        self.module.FONTS.mkdir()
        secret = Path(self.tmp.name) / "secret"
        secret.write_text("not a font")
        (self.module.FONTS / "Athletics-Regular.woff2").symlink_to(secret)
        headers, _ = self.request("/fonts/Athletics-Regular.woff2")
        self.assertIn(b"404 Not Found", headers)

    def test_truncated_history_is_separated_before_appending(self):
        self.module.HISTORY.write_text('{"t":1,"u":')
        self.module.append_history(1000, 1)
        lines = self.module.HISTORY.read_text().splitlines()
        self.assertEqual(json.loads(lines[-1]), {"t": 1000, "u": 1})
        with patch.object(self.module, "now_ts", return_value=1001):
            self.module.load_history()
        self.assertEqual(list(self.module.samples), [(1000, 1)])

    def test_history_ignores_invalid_future_and_out_of_order_samples(self):
        rows = [
            {"t": 100, "u": 1},
            {"t": 50, "u": 0},
            {"t": 101, "u": 7},
            {"t": 102, "u": True},
            {"t": 120, "u": 0},
            {"t": 9999, "u": 1},
            None,
        ]
        self.module.HISTORY.write_text("\n".join(json.dumps(row) for row in rows))
        with patch.object(self.module, "now_ts", return_value=200):
            self.module.load_history()
        self.assertEqual(list(self.module.samples), [(100, 1), (120, 0)])
        self.assertEqual(self.module.view["checked_at"], 120)

    def test_monitoring_gap_resets_run_and_does_not_send_false_alert(self):
        self.module.samples.append((100, 1))
        self.module.last_up = 1
        self.module.since = 100
        with (
            patch.object(self.module, "now_ts", return_value=1000),
            patch.object(self.module, "campus_up", return_value=False),
            patch.object(self.module, "send_down_email") as mail,
        ):
            self.module.sample()
        self.assertEqual(self.module.since, 1000)
        self.assertEqual(self.module.window_stats(1000, 86400)[2], 0)
        mail.assert_not_called()

    def test_mail_delivery_does_not_block_probe_thread(self):
        self.module.samples.append((1000, 1))
        self.module.last_up = 1
        self.module.since = 1000
        with (
            patch.object(self.module, "now_ts", return_value=1030),
            patch.object(self.module, "campus_up", return_value=False),
            patch.object(self.module.threading, "Thread") as thread,
        ):
            self.module.sample()
        thread.assert_called_once_with(
            target=self.module.send_down_email, args=(1030,), daemon=True
        )
        thread.return_value.start.assert_called_once()

    def test_sparse_samples_do_not_claim_complete_window(self):
        self.module.samples.extend([(1, 1), (86400, 1)])
        _, label = self.module.pct_label(2, 2, "24 hours", 86401)
        self.assertIn("2 checks", label)

    def test_quoted_email_config_and_environment_override(self):
        self.module.ENV_FILE.write_text(
            "RESEND_FROM='Relay <relay@example.com>'\nRESEND_API_KEY=file-key\n"
        )
        with patch.dict(os.environ, {"RESEND_API_KEY": "service-key"}, clear=True):
            env = self.module.load_env()
        self.assertEqual(env["RESEND_FROM"], "Relay <relay@example.com>")
        self.assertEqual(env["RESEND_API_KEY"], "service-key")

    def test_test_email_failure_is_reported(self):
        self.module.env = {}
        self.assertFalse(self.module.send_down_email(1000, test=True))
        self.module.env = {
            "RESEND_FROM": "relay@example.com",
            "RESEND_TO": "you@example.com",
            "RESEND_API_KEY": "fake",
        }
        with patch.object(self.module.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertFalse(self.module.send_down_email(1000, test=True))

    def test_probe_uses_configured_port_and_requires_complete_banner(self):
        with patch.object(self.module.socket, "socket") as socket_factory:
            sock = socket_factory.return_value
            sock.recv.side_effect = [b"SSH-2.0-test\r\n"]
            self.module.RELAY_PORT = 3333
            self.assertTrue(self.module.campus_up())
            sock.connect.assert_called_once_with(("127.0.0.1", 3333))
            sock.recv.side_effect = [b"SSH-2.0-test", b""]
            self.assertFalse(self.module.campus_up())

    def test_probe_has_a_total_deadline(self):
        with (
            patch.object(self.module.socket, "socket") as socket_factory,
            patch.object(self.module.time, "monotonic", side_effect=[0, 6]),
        ):
            self.assertFalse(self.module.campus_up())
        socket_factory.return_value.recv.assert_not_called()

    def test_preview_does_not_probe_load_credentials_or_write_history(self):
        with (
            patch("sys.argv", ["relay-status", "--preview", "down", "--port", "8765"]),
            patch.dict(os.environ, {}, clear=True),
            patch.object(self.module, "StatusHTTPServer") as server,
            patch.object(self.module, "load_env") as credentials,
            patch.object(self.module, "sample") as sample,
            patch.object(self.module, "load_history") as history,
        ):
            self.assertEqual(self.module.main(), 0)
        self.assertEqual(server.call_args.args[0], ("127.0.0.1", 8765))
        credentials.assert_not_called()
        sample.assert_not_called()
        history.assert_not_called()
        self.assertIn("sample data", self.module.view["checked"])

    def test_email_cli_failure_exits_nonzero_without_starting_server(self):
        with (
            patch("sys.argv", ["relay-status", "--test-email"]),
            patch.object(self.module, "StatusHTTPServer") as server,
            patch.object(self.module, "load_env", return_value={}),
        ):
            self.assertEqual(self.module.main(), 1)
        server.assert_not_called()

    def test_restart_preserves_run_but_gaps_reset_it(self):
        for rows, expected in [([(100, 1), (130, 1)], 100), ([(100, 1), (300, 1)], 300)]:
            with self.subTest(rows=rows):
                self.module.samples.clear()
                self.module.HISTORY.write_text(
                    "\n".join(json.dumps({"t": ts, "u": flag}) for ts, flag in rows)
                )
                with patch.object(self.module, "now_ts", return_value=310):
                    self.module.load_history()
                self.assertEqual(self.module.since, expected)


if __name__ == "__main__":
    unittest.main()
