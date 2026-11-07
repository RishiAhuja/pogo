import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def executable(self, path, source):
        path.write_text(source)
        path.chmod(0o755)
        return path

    @unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH tools required")
    def test_client_keys_create_missing_directory_and_never_overwrite(self):
        env = {**os.environ, "HOME": str(self.directory)}
        command = ["bash", str(ROOT / "mac/make-keys.sh"), "--no-passphrase"]
        subprocess.run(command, env=env, check=True, capture_output=True)
        key = self.directory / ".ssh/hpc_relay"
        before = key.read_bytes()
        key.with_suffix(".pub").unlink()
        subprocess.run(command, env=env, check=True, capture_output=True)
        self.assertEqual(key.read_bytes(), before)
        self.assertTrue(key.with_suffix(".pub").is_file())
        self.assertEqual((self.directory / ".ssh").stat().st_mode & 0o777, 0o700)

    @unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH tools required")
    def test_rotation_replaces_the_only_pinned_host_key(self):
        binary = self.directory / "bin"
        binary.mkdir()
        self.executable(binary / "id", "#!/bin/sh\necho 0\n")
        self.executable(binary / "chown", "#!/bin/sh\nexit 0\n")
        keys = []
        for name in ("old", "new"):
            key = self.directory / name
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True
            )
            keys.append("192.0.2.10 " + " ".join(key.with_suffix(".pub").read_text().split()[:2]))
        hosts = self.directory / "known_hosts"
        hosts.write_text(keys[0] + "\n")
        source = (
            (ROOT / "campus/pin-relay-key.sh")
            .read_text()
            .replace("file=/etc/ssh/ssh_known_hosts", f"file={hosts}")
        )
        script = self.executable(self.directory / "pin.sh", source)
        env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"]}
        subprocess.run(["bash", str(script), keys[1]], env=env, check=True, capture_output=True)
        self.assertEqual(hosts.read_text(), keys[1] + "\n")
        subprocess.run(["bash", str(script), keys[1]], env=env, check=True, capture_output=True)
        self.assertEqual(hosts.read_text(), keys[1] + "\n")

    def test_tunnel_uses_configured_interface_and_port(self):
        config = self.directory / "campus.env"
        config.write_text(
            "WIFI_IFACE=wlan7\nRELAY_HOST=192.0.2.10\nRELAY_USER=tunnel\nRELAY_PORT=3333\nTUNNEL_KEY=/example/key\n"
        )
        ssh = self.executable(self.directory / "fake-ssh", '#!/bin/sh\nprintf "%s\\n" "$@"\n')
        source = (ROOT / "campus/rootfs/usr/local/sbin/aws-reverse-tunnel").read_text()
        source = source.replace("/etc/hpc-relay/campus.env", str(config)).replace(
            "/usr/bin/ssh", str(ssh)
        )
        script = self.executable(self.directory / "tunnel.sh", source)
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True, check=True)
        self.assertIn("BindInterface=wlan7\n", result.stdout)
        self.assertIn("127.0.0.1:3333:127.0.0.1:22\n", result.stdout)
        self.assertIn("StrictHostKeyChecking=yes\n", result.stdout)

    def test_wifi_profile_can_differ_from_ssid(self):
        binary = self.directory / "bin"
        binary.mkdir()
        capture = self.directory / "connected"
        nmcli = f"""#!/bin/bash
case "$*" in
  *GENERAL.CONNECTION*) echo Other ;;
  *802-11-wireless.ssid*) echo 'Actual Wi-Fi' ;;
  *'device wifi list'*) echo 'Actual Wi-Fi' ;;
  *'connection up'*) printf '%s\\n' "$@" > '{capture}' ;;
esac
"""
        self.executable(binary / "nmcli", nmcli)
        for name in ("rfkill", "iw", "logger", "systemctl"):
            self.executable(binary / name, "#!/bin/sh\nexit 0\n")
        config = self.directory / "campus.env"
        config.write_text("WIFI_IFACE=wlan7\nWIFI_CONNECTION='Saved profile'\n")
        source = (ROOT / "campus/rootfs/usr/local/sbin/nitj-wifi-ensure").read_text()
        source = source.replace("/etc/hpc-relay/campus.env", str(config)).replace(
            "/run/nitj-wifi-ensure.lock", str(self.directory / "lock")
        )
        script = self.executable(self.directory / "wifi.sh", source)
        if not shutil.which("flock"):
            # This test exercises SSID selection, not Linux locking semantics.
            self.executable(binary / "flock", "#!/bin/sh\nexit 0\n")
        env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"]}
        subprocess.run(["bash", str(script)], env=env, capture_output=True, check=True)
        self.assertIn("Saved profile", capture.read_text())
        self.assertIn("wlan7", capture.read_text())

    @unittest.skipUnless(Path("/usr/sbin/sshd").is_file(), "OpenSSH server required")
    def test_effective_sshd_settings_and_admin_forwarding(self):
        key = self.directory / "host_key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        conf_dir = self.directory / "sshd_config.d"
        conf_dir.mkdir()
        source = (
            (ROOT / "relay/sshd/00-hpc-relay.conf")
            .read_text()
            .replace("__TUNNEL_USER__", "tunnel")
            .replace("__RELAY_PORT__", "3333")
        )
        (conf_dir / "00-relay.conf").write_text(source)
        (conf_dir / "50-cloud.conf").write_text("PasswordAuthentication yes\n")
        config = self.directory / "sshd_config"
        config.write_text(f"HostKey {key}\nInclude {conf_dir}/*.conf\nUsePAM yes\n")
        for user, forwarding, sessions in [("tunnel", "remote", "0"), ("other", "yes", "10")]:
            result = subprocess.run(
                [
                    "/usr/sbin/sshd",
                    "-T",
                    "-f",
                    str(config),
                    "-C",
                    f"user={user},host=localhost,addr=127.0.0.1",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("passwordauthentication no\n", result.stdout)
            self.assertIn(f"allowtcpforwarding {forwarding}\n", result.stdout)
            self.assertIn(f"maxsessions {sessions}\n", result.stdout)
            if user == "tunnel":
                self.assertIn("permitlisten 127.0.0.1:3333\n", result.stdout)


if __name__ == "__main__":
    unittest.main()
