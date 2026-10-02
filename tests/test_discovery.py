from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import shutil
import subprocess

from ssh_ls.discovery import discover_config, discover_history


class ConfigDiscoveryTests(unittest.TestCase):
    def test_alias_options_includes_globs_quotes_equals_and_wildcards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".ssh"
            root.mkdir()
            (root / "config").write_text(
                'Include "parts/*.conf"\n'
                'Host alpha beta *.example !ignored ?x\n'
                '  HostName=one.example # comment\n'
                '  User "deploy user"\n'
                '  Port 2201\n'
                '  IdentityFile "~/.ssh/key one"\n'
                '  ProxyJump bastion\n'
                '  ForwardAgent yes\n', encoding="utf-8")
            (root / "parts").mkdir()
            (root / "parts" / "one.conf").write_text(
                'Host gamma\n HostName gamma.example\n', encoding="utf-8")
            with patch("ssh_ls.discovery.Path.home", return_value=Path(tmp)):
                hosts, warnings = discover_config([root / "config"])
            self.assertEqual(warnings, [])
            by_alias = {host.alias: host for host in hosts}
            self.assertEqual(set(by_alias), {"alpha", "beta", "gamma"})
            self.assertEqual(by_alias["alpha"].hostname, "one.example")
            self.assertEqual(by_alias["alpha"].user, "deploy user")
            self.assertEqual(by_alias["alpha"].port, 2201)
            self.assertEqual(by_alias["alpha"].identities, ["~/.ssh/key one"])
            self.assertEqual(by_alias["alpha"].jump, "bastion")
            self.assertEqual(by_alias["alpha"].extra_args, [])
            self.assertEqual(by_alias["alpha"].config_path, str((root / "config").absolute()))
            self.assertTrue(by_alias["alpha"].sources[0].startswith("config:"))

    def test_cycle_escape_and_malformed_port_are_warnings_not_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".ssh"
            root.mkdir()
            outside = Path(tmp) / "outside.conf"
            outside.write_text("Host secret\n HostName must-not-appear\n", encoding="utf-8")
            (root / "config").write_text(
                'Include config\n'
                'Include missing-fixture.conf\n'
                f'Include "{outside}"\n'
                'Host safe\n Port bad\n HostName safe.example\n', encoding="utf-8")
            with patch("ssh_ls.discovery.Path.home", return_value=Path(tmp)):
                hosts, warnings = discover_config([root / "config"])
            self.assertEqual([h.alias for h in hosts], ["secret", "safe"])
            self.assertTrue(any("cycle" in w for w in warnings))
            self.assertTrue(any("matched no files" in w for w in warnings))
            self.assertTrue(any("Invalid SSH port" in w for w in warnings))

    def test_declaration_only_host_and_first_explicit_port_22_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config"
            cfg.write_text(
                "Host bare\nHost ported\n Port 22\nHost ported\n Port 2222\n",
                encoding="utf-8")
            hosts, warnings = discover_config([cfg])
            self.assertEqual(warnings, [])
            by_alias = {h.alias: h for h in hosts}
            self.assertEqual(set(by_alias), {"bare", "ported"})
            self.assertEqual(by_alias["bare"].hostname, "bare")
            self.assertEqual(by_alias["ported"].port, 22)
            self.assertEqual(by_alias["ported"].extra_args, [])

    def test_default_roots_read_user_before_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            user_config = home / ".ssh/config"
            seen = []

            def fake_read(path, include_root, warnings):
                seen.append(path)
                if path == user_config:
                    return [("same", "__host__", "same", 1, path),
                            ("same", "hostname", "user.example", 2, path),
                            ("same", "port", "22", 3, path)]
                return [("same", "__host__", "same", 1, path),
                        ("same", "hostname", "system.example", 2, path),
                        ("same", "port", "2200", 3, path)]

            with patch("ssh_ls.discovery.Path.home", return_value=home), \
                    patch("ssh_ls.discovery._read_config_root", side_effect=fake_read):
                hosts, warnings = discover_config()
            self.assertEqual(warnings, [])
            self.assertEqual(seen, [user_config, Path("/etc/ssh/ssh_config")])
            self.assertEqual(len(hosts), 1)
            self.assertEqual(hosts[0].hostname, "user.example")
            self.assertEqual(hosts[0].port, 22)

    def test_nested_relative_include_uses_ssh_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".ssh"
            (root / "nested").mkdir(parents=True)
            (root / "config").write_text("Include nested/part.conf\n", encoding="utf-8")
            (root / "nested/part.conf").write_text("Include relative.conf\n", encoding="utf-8")
            (root / "relative.conf").write_text("Host included\n HostName included.example\n", encoding="utf-8")
            with patch("ssh_ls.discovery.Path.home", return_value=Path(tmp)):
                hosts, warnings = discover_config([root / "config"])
            self.assertEqual(warnings, [])
            self.assertEqual([(h.alias, h.hostname) for h in hosts], [("included", "included.example")])

    def test_symlink_include_cycle_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".ssh"
            root.mkdir()
            cfg = root / "config"
            cfg.write_text("Include cycle.conf\nHost safe\n", encoding="utf-8")
            (root / "cycle.conf").symlink_to(cfg)
            with patch("ssh_ls.discovery.Path.home", return_value=Path(tmp)):
                hosts, warnings = discover_config([cfg])
            self.assertEqual([host.alias for host in hosts], ["safe"])
            self.assertTrue(any("cycle" in warning for warning in warnings))

    def test_native_ssh_g_comparison_uses_only_temporary_fixture(self):
        ssh = shutil.which("ssh")
        if not ssh:
            self.skipTest("ssh is unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            ssh_dir = home / ".ssh"
            ssh_dir.mkdir(parents=True)
            cfg = Path(tmp) / "known-fixture.conf"
            cfg.write_text(
                "Include known-fixture-options.conf\n",
                encoding="utf-8")
            (ssh_dir / "known-fixture-options.conf").write_text(
                "Host fixture\n HostName 127.0.0.1\n User fixture-user\n Port 2999\n",
                encoding="utf-8")
            with patch("ssh_ls.discovery.Path.home", return_value=home):
                hosts, warnings = discover_config([cfg])
            self.assertEqual(warnings, [])
            discovered = hosts[0]
            native = subprocess.run(
                [ssh, "-G", "-F", str(cfg), "fixture"],
                capture_output=True, text=True, timeout=5, check=False,
                env={**os.environ, "HOME": str(home)})
            self.assertEqual(native.returncode, 0, native.stderr)
            values = dict(line.split(None, 1) for line in native.stdout.splitlines() if " " in line)
            self.assertEqual(discovered.hostname, values["hostname"])
            self.assertEqual(discovered.user, values["user"])
            self.assertEqual(discovered.port, int(values["port"]))

    def test_missing_explicit_config_warns_but_empty_paths_do_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            hosts, warnings = discover_config([Path(tmp) / "missing.conf"])
            self.assertEqual(hosts, [])
            self.assertTrue(any("Explicit SSH config not found" in w for w in warnings))
        self.assertEqual(discover_config([]), ([], []))

    def test_default_config_has_no_custom_path(self):
        # Explicit empty path list is useful for a deterministic no-input check.
        hosts, warnings = discover_config([])
        self.assertEqual(hosts, [])
        self.assertEqual(warnings, [])


class HistoryDiscoveryTests(unittest.TestCase):
    def test_bash_and_zsh_simple_commands_normalize_and_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            bash = Path(tmp) / "bash_history"
            zsh = Path(tmp) / "zsh_history"
            bash.write_text(
                'ssh -p 2202 -l alice -i "~/.ssh/key one" -J jump host.example uptime\n'
                'env ssh -o User=bob -o Port=2223 bob@host-two\n'
                'ssh -o Compression=yes skipped\n'
                'ssh host; touch marker\n'
                'notssh host\n'
                'ssh default-port-host\n', encoding="utf-8")
            zsh.write_text(
                ': 1700000000:3;command ssh -J jump -p 2202 alice@host.example\n'
                'ssh ssh://carol@host-three\n', encoding="utf-8")
            hosts, warnings = discover_history([bash, zsh])
            self.assertEqual(warnings, [])
            self.assertEqual(len(hosts), 5)
            by_host = {h.hostname: h for h in hosts}
            one = next(h for h in hosts if h.hostname == "host.example" and h.identities)
            self.assertEqual(one.user, "alice")
            self.assertEqual(one.port, 2202)
            self.assertEqual(one.identities, ["~/.ssh/key one"])
            self.assertEqual(one.jump, "jump")
            self.assertTrue(one.history)
            self.assertEqual(by_host["host-two"].user, "bob")
            self.assertEqual(by_host["host-two"].port, 2223)
            self.assertTrue(by_host["host-two"].port_explicit)
            self.assertEqual(by_host["host-three"].user, "carol")
            self.assertFalse(by_host["host-three"].port_explicit)
            self.assertFalse(by_host["default-port-host"].port_explicit)
            zsh_record = next(h for h in hosts if h.hostname == "host.example" and not h.identities)
            self.assertEqual(zsh_record.last_used, 1700000000)

    def test_shell_substitution_and_unknown_options_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            hist = Path(tmp) / "history"
            hist.write_text(
                'ssh $(touch bad)\n'
                'ssh -o ProxyCommand=bad host\n'
                'ssh host `whoami`\n'
                'ssh -oPort=2222 host\n', encoding="utf-8")
            hosts, _ = discover_history([hist])
            self.assertEqual([h.hostname for h in hosts], ["host"])
            self.assertEqual(hosts[0].port, 2222)
            self.assertFalse((Path(tmp) / "bad").exists())

    def test_ssh_url_and_explicit_config_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            hist = Path(tmp) / "history"
            hist.write_text(f'ssh -F {tmp}/custom.conf -i ~/.ssh/key ssh://u@[2001:db8::1]:2200\n', encoding="utf-8")
            hosts, _ = discover_history([hist])
            self.assertEqual(len(hosts), 1)
            self.assertEqual(hosts[0].hostname, "2001:db8::1")
            self.assertEqual(hosts[0].user, "u")
            self.assertEqual(hosts[0].config_path, f"{tmp}/custom.conf")
            self.assertEqual(hosts[0].port, 2200)
            self.assertTrue(hosts[0].port_explicit)

    def test_env_assignments_relative_paths_and_misleading_destinations_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history"
            history.write_text(
                "env FOO=bar ssh env-assigned\n"
                "ssh -i relative.key relative-identity\n"
                "ssh -F ./config relative-config\n"
                "ssh -- -leading-dash\n"
                "ssh 'has space'\n"
                "ssh 'bad user@host'\n"
                "ssh 'bad@user@host'\n"
                "ssh -i ~/.ssh/key -F ~/.ssh/config stable-host\n",
                encoding="utf-8")
            hosts, warnings = discover_history([history])
            self.assertEqual(warnings, [])
            self.assertEqual([host.hostname for host in hosts], ["stable-host"])
            self.assertEqual(hosts[0].identities, ["~/.ssh/key"])
            self.assertEqual(hosts[0].config_path, "~/.ssh/config")

    def test_port_explicitness_is_kept_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history"
            history.write_text("ssh same-host\nssh -p 22 same-host\n", encoding="utf-8")
            hosts, warnings = discover_history([history])
            self.assertEqual(warnings, [])
            self.assertEqual(len(hosts), 2)
            self.assertEqual({host.port_explicit for host in hosts}, {False, True})

    def test_malformed_url_and_control_characters_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history"
            history.write_text(
                "ssh ssh://[\n"
                "ssh bad" + chr(1) + "name\n"
                "ssh -i 'key" + chr(1) + "with-control' safe-host\n"
                "ssh good-host\n", encoding="utf-8")
            hosts, warnings = discover_history([history])
            self.assertEqual(warnings, [])
            self.assertEqual([host.hostname for host in hosts], ["good-host"])


if __name__ == "__main__":
    unittest.main()
