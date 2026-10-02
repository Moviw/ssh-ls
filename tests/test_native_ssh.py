"""Opt-in loopback SSH smoke. Keys/config/server exist only in a temp directory."""
import getpass
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from ssh_ls.discovery import discover_config
from ssh_ls.launch import build_argv


@unittest.skipUnless(os.environ.get("SSH_LS_INTEGRATION") == "1", "set SSH_LS_INTEGRATION=1 for isolated loopback sshd")
class NativeSSHTests(unittest.TestCase):
    def test_direct_and_picker_argv_match_native_openssh(self):
        sshd = shutil.which("sshd") or "/usr/sbin/sshd"
        self.assertTrue(Path(sshd).exists(), "Install openssh-server for integration")
        self.assertTrue(shutil.which("ssh-keygen"))
        with tempfile.TemporaryDirectory(prefix="ssh-ls-smoke-") as tmp:
            directory = Path(tmp)
            os.chmod(directory, 0o700)
            for name in ("client", "server"):
                subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(directory / name)], check=True, capture_output=True)
            authorized = directory / "authorized_keys"
            authorized.write_bytes((directory / "client.pub").read_bytes())
            authorized.chmod(0o600)
            with socket.socket() as socket_:
                socket_.bind(("127.0.0.1", 0))
                port = socket_.getsockname()[1]
            config = directory / "sshd_config"
            config.write_text(f"""Port {port}
ListenAddress 127.0.0.1
HostKey {directory / 'server'}
PidFile {directory / 'sshd.pid'}
AuthorizedKeysFile {authorized}
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM no
StrictModes no
PermitRootLogin prohibit-password
PermitUserRC no
AllowUsers {getpass.getuser()}
LogLevel ERROR
SetEnv HOME={directory} ZDOTDIR={directory}
""")
            server = subprocess.Popen([sshd, "-D", "-e", "-f", str(config)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                ready = False
                for _ in range(50):
                    if server.poll() is not None:
                        self.fail("Isolated sshd failed: " + server.communicate()[1].decode())
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                            ready = True
                            break
                    except OSError:
                        time.sleep(0.1)
                self.assertTrue(ready, "loopback sshd did not start")
                known = directory / "known_hosts"
                public = (directory / "server.pub").read_text().split()
                known.write_text(f"[127.0.0.1]:{port} {public[0]} {public[1]}\n")
                client_config = directory / "config"
                client_config.write_text(f"""Host fixture
  HostName 127.0.0.1
  User {getpass.getuser()}
  Port {port}
  IdentityFile {directory / 'client'}
  IdentitiesOnly yes
  BatchMode yes
  StrictHostKeyChecking yes
  UserKnownHostsFile {known}
  GlobalKnownHostsFile /dev/null
  ConnectTimeout 5
""")
                hosts, warnings = discover_config([client_config])
                self.assertFalse(warnings)
                self.assertEqual(len(hosts), 1)
                command = "printf ssh-ls-native-ok"
                baseline = subprocess.run(["ssh", "-F", str(client_config), "fixture", command], capture_output=True, text=True, timeout=15)
                modified = subprocess.run(build_argv(hosts[0], command), capture_output=True, text=True, timeout=15)
                self.assertEqual((baseline.returncode, baseline.stdout), (0, "ssh-ls-native-ok"), baseline.stderr)
                self.assertEqual((modified.returncode, modified.stdout), (baseline.returncode, baseline.stdout), modified.stderr)
                print("NATIVE BASELINE stdout='ssh-ls-native-ok' exit=0")
                print("NATIVE PICKER stdout='ssh-ls-native-ok' exit=0")
                failure = subprocess.run(build_argv(hosts[0], "exit 23"), capture_output=True, text=True, timeout=15)
                self.assertEqual(failure.returncode, 23, failure.stderr)
                print("NATIVE REMOTE EXIT stdout='' exit=23")
            finally:
                server.terminate()
                try:
                    server.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.communicate()


if __name__ == "__main__":
    unittest.main()
