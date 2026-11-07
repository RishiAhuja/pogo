import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


def load_portal():
    loader = importlib.machinery.SourceFileLoader(
        "portal", str(ROOT / "campus/rootfs/usr/local/sbin/nitj-portal-login")
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.module = load_portal()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for key in ("ENV_FILE", "CREDS", "LOCK", "STAMP"):
            setattr(self.module, key, root / key)
        self.module.ENV_FILE.write_text(
            "WIFI_IFACE=wlan7\nWIFI_CONNECTION='Campus Wi-Fi'\nPORTAL_GATEWAY=192.0.2.1\nPORTAL_ENABLED=1\n"
        )
        self.module.CREDS.write_text("username=person\npassword=literal#'password=with spaces\n")

    def test_configuration_quotes_and_literal_password_are_distinct(self):
        config = self.module.load_file(self.module.ENV_FILE, shell_values=True)
        creds = self.module.load_file(self.module.CREDS)
        self.assertEqual(config["WIFI_CONNECTION"], "Campus Wi-Fi")
        self.assertEqual(creds["password"], "literal#'password=with spaces")

    def test_disabled_adapter_never_checks_network_or_credentials(self):
        self.module.ENV_FILE.write_text("PORTAL_ENABLED=0\n")
        with (
            patch.object(self.module, "on_network") as network,
            patch.object(self.module, "login") as login,
        ):
            self.assertEqual(self.module.main(), 0)
        network.assert_not_called()
        login.assert_not_called()

    def test_wrong_network_never_receives_credentials(self):
        with (
            patch.object(self.module, "on_network", return_value=False),
            patch.object(self.module, "login") as login,
        ):
            self.assertEqual(self.module.main(), 0)
        login.assert_not_called()

    def test_all_callers_obey_the_rate_limit(self):
        self.module.STAMP.write_text("1000")
        with (
            patch.dict(os.environ, {"NITJ_PORTAL_FORCE": "1"}),
            patch.object(self.module.time, "time", return_value=1030),
            patch.object(self.module, "on_network", return_value=True),
            patch.object(self.module, "login") as login,
        ):
            self.assertEqual(self.module.main(), 0)
        login.assert_not_called()

    def test_only_configured_gateway_is_used_with_tls_on(self):
        with (
            patch.object(self.module, "on_network", return_value=True),
            patch.object(self.module, "login", return_value=200) as login,
        ):
            self.assertEqual(self.module.main(), 0)
        self.assertEqual(login.call_args.args[0], "192.0.2.1")
        self.assertTrue(login.call_args.kwargs["verify"])
        self.assertTrue(self.module.STAMP.exists())

    def test_network_is_rechecked_after_lock(self):
        with (
            patch.object(self.module, "on_network", side_effect=[True, False]),
            patch.object(self.module, "login") as login,
        ):
            self.assertEqual(self.module.main(), 0)
        login.assert_not_called()
        self.assertFalse(self.module.STAMP.exists())

    def test_failed_login_is_still_rate_limited(self):
        with (
            patch.object(self.module, "on_network", return_value=True),
            patch.object(self.module, "login", side_effect=OSError("private detail")) as login,
        ):
            self.assertEqual(self.module.main(), 1)
            self.assertEqual(self.module.main(), 0)
        login.assert_called_once()

    def test_empty_credentials_do_not_send(self):
        self.module.CREDS.write_text("username=\npassword=\n")
        with (
            patch.object(self.module, "on_network", return_value=True),
            patch.object(self.module, "login") as login,
        ):
            self.assertEqual(self.module.main(), 1)
        login.assert_not_called()

    def test_gateway_is_not_a_url_or_injected_path(self):
        with self.module.ENV_FILE.open("a") as handle:
            handle.write("PORTAL_GATEWAY=https://unexpected.example/steal\n")
        with patch.object(self.module, "login") as login:
            self.assertEqual(self.module.main(), 1)
        login.assert_not_called()

    def test_tls_verification_and_redirect_policy(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"status":200}'
        opener = MagicMock()
        opener.open.return_value = response
        with (
            patch.object(self.module.ssl, "create_default_context") as secure,
            patch.object(self.module.ssl, "_create_unverified_context") as insecure,
            patch.object(self.module.urllib.request, "build_opener", return_value=opener),
        ):
            self.assertEqual(
                self.module.login("192.0.2.1", {"username": "person", "password": "fake"}), 200
            )
        secure.assert_called_once()
        insecure.assert_not_called()
        self.assertIsNone(
            self.module.NoRedirect().redirect_request(
                None, None, 302, "redirect", {}, "https://other.example"
            )
        )


if __name__ == "__main__":
    unittest.main()
