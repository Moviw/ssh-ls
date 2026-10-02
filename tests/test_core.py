import copy
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ssh_ls.launch import build_argv, validate, launch
from ssh_ls.models import Host
from ssh_ls.store import StateError, Store


class CoreTests(unittest.TestCase):
    def host(self, **kwargs):
        return Host("test", "Test", "server.example.test", **kwargs)

    def test_native_alias_retains_config(self):
        host = self.host(alias="work", user="estimate", port=2222, identities=["estimated-key"], jump="estimated-jump")
        self.assertEqual(build_argv(host), ["ssh", "--", "work"])
        host.overrides = {"port": 2222, "hostname": "other.example.test"}
        host.hostname = "other.example.test"
        self.assertEqual(build_argv(host), ["ssh", "-o", "HostName=other.example.test", "-p", "2222", "--", "work"])

    def test_implicit_history_port_defers_to_openssh(self):
        host = self.host(port_explicit=False, sources=["history:fixture"])
        self.assertEqual(build_argv(host), ["ssh", "--", "server.example.test"])
        host.port_explicit = True
        self.assertEqual(build_argv(host), ["ssh", "-p", "22", "--", "server.example.test"])

    def test_remote_command_not_local_shell(self):
        command = "printf hello; $(touch /tmp/never-execute-ssh-ls)"
        host = self.host(user="developer", port=2222, identities=["/tmp/key with spaces"])
        args = build_argv(host, command)
        self.assertEqual(args[-1], command)
        self.assertIn("/tmp/key with spaces", args)
        with patch("ssh_ls.launch.shutil.which", return_value="/usr/bin/ssh"), patch("ssh_ls.launch.subprocess.run") as run:
            run.return_value.returncode = 23
            self.assertEqual(launch(host, command), 23)
            self.assertEqual(run.call_args.kwargs, {"shell": False})
            self.assertEqual(run.call_args.args[0], args)

    def test_validation(self):
        for change in [{"hostname": "-oProxyCommand=bad"}, {"hostname": "a b"}, {"user": "a@b"}, {"port": 0}, {"port": 65536}, {"label": "bad\x1b[2J"}, {"last_used": float("nan")}, {"identities": "not-list"}, {"favorite": "true"}]:
            host = self.host()
            for k, v in change.items():
                setattr(host, k, v)
            with self.assertRaises(ValueError):
                validate(host)
        for args in [["destination"], ["-p"], ["-G"], ["-O", "exit"], ["-Q", "cipher"], ["-f"], ["--", "evil"], ["-o", "ok", "evil-command"]]:
            with self.assertRaises(ValueError):
                build_argv(self.host(extra_args=args))
        self.assertEqual(build_argv(self.host(extra_args=["-vv", "-L", "8080:localhost:80"]))[3:6], ["-vv", "-L", "8080:localhost:80"])

    def test_store_backup_permissions_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "app")
            host = self.host()
            store.save_host(host)
            pristine = store.path.read_bytes()
            host.favorite = True
            store.save_host(host)
            self.assertEqual(store.path.with_suffix(".json.bak").read_bytes(), pristine)
            self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(store.directory.stat().st_mode), 0o700)
            store.path.write_text("broken")
            with self.assertRaises(StateError):
                store.save_host(host)
            self.assertEqual(store.path.read_text(), "broken")

    def test_two_store_instances_merge_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Store(Path(tmp)), Store(Path(tmp))
            a.save_host(self.host())
            other = self.host()
            other.id = "other"
            b.save_host(other)
            self.assertEqual(set(a.read()["hosts"]), {"test", "other"})


if __name__ == "__main__":
    unittest.main()
