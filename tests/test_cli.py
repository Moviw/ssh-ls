import hashlib
import io
import json
import os
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ssh_ls.cli import main
from ssh_ls.models import LaunchRequest
from ssh_ls.service import demo_hosts
from ssh_ls.store import Store


class CLITests(unittest.TestCase):
    def test_demo_connection_is_preview_only(self):
        output = io.StringIO()
        with redirect_stdout(output), patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True), patch("ssh_ls.ui.SSHApp") as app, patch("ssh_ls.cli.launch", side_effect=AssertionError("network launch")):
            app.return_value.run.return_value = LaunchRequest(demo_hosts()[0], "uptime")
            self.assertEqual(main(["--demo"]), 0)
        self.assertIn("DEMO (not executed)", output.getvalue())

    def test_real_tui_handoff_restores_tty_and_propagates_exit(self):
        with tempfile.TemporaryDirectory(prefix="ssh-ls-pty-") as tmp:
            directory = Path(tmp)
            config = directory / "config"
            config.write_text("Host fixture\n HostName fixture.example.test\n")
            pristine = hashlib.sha256(config.read_bytes()).hexdigest()
            fake_ssh = directory / "ssh"
            fake_ssh.write_text(f"#!{sys.executable}\nimport json,sys,termios\na=termios.tcgetattr(0)\nprint('SSH_LS_FAKE_TTY',int(bool(a[3]&termios.ICANON)),int(bool(a[3]&termios.ECHO)))\nprint('SSH_LS_FAKE_ARGV',json.dumps(sys.argv[1:]))\nsys.exit(23)\n")
            fake_ssh.chmod(0o700)
            Store(directory / "state" / "ssh-ls").save_settings({"start_tab": "All"})
            master, slave = pty.openpty()
            env = {**os.environ, "PATH": str(directory) + os.pathsep + os.environ.get("PATH", ""), "XDG_CONFIG_HOME": str(directory / "state"), "TERM": "xterm-256color"}
            process = subprocess.Popen([sys.executable, "-m", "ssh_ls", "--config", str(config), "--no-history"], stdin=slave, stdout=slave, stderr=slave, env=env)
            os.close(slave)
            received = b""
            deadline = time.monotonic() + 20
            sent = False
            try:
                while time.monotonic() < deadline:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if ready:
                        try:
                            chunk = os.read(master, 65536)
                        except OSError:
                            break
                        if not chunk:
                            break
                        received += chunk
                    if not sent and b"fixture" in received and b"Connect" in received:
                        time.sleep(0.15)
                        os.write(master, b"\r")
                        sent = True
                    if process.poll() is not None:
                        # Drain output once after exit.
                        try:
                            while select.select([master], [], [], 0.1)[0]:
                                received += os.read(master, 65536)
                        except OSError:
                            pass
                        break
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                text = received.decode(errors="replace")
                self.assertTrue(sent, text[-1500:])
                self.assertEqual(process.returncode, 23, text[-1500:])
                self.assertIn("SSH_LS_FAKE_TTY 1 1", text)
                self.assertIn('"--", "fixture"', text)
                self.assertEqual(hashlib.sha256(config.read_bytes()).hexdigest(), pristine)
                print("PTY HANDOFF canonical=1 echo=1; SSH exit=23; original config unchanged")
            finally:
                os.close(master)
                if process.poll() is None:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    unittest.main()
