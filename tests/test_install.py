"""Offline integration tests for the POSIX install.sh entry point."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "install.sh"


class InstallScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.log"
        self.bootstrap_source = self.root / "bootstrap.sh"
        self.uv_template = self.root / "uv"
        self._write(self.uv_template, self._uv_program())
        self._write(
            self.bootstrap_source,
            '#!/bin/sh\n'
            'set -eu\n'
            '[ "${UV_INSTALL_DIR-}" = "$HOME/.local/bin" ] || exit 71\n'
            '[ "${UV_NO_MODIFY_PATH-}" = "1" ] || exit 72\n'
            'mkdir -p "$UV_INSTALL_DIR"\n'
            'cp "$FAKE_UV_TEMPLATE" "$UV_INSTALL_DIR/uv"\n'
            'chmod +x "$UV_INSTALL_DIR/uv"\n',
        )
        self._write(
            self.bin / "curl",
            '#!/bin/sh\n'
            'printf "curl %s\\n" "$*" >> "$FAKE_LOG"\n'
            '[ "${CURL_EXIT:-0}" -eq 0 ] || exit "$CURL_EXIT"\n'
            'out=\n'
            'while [ "$#" -gt 0 ]; do\n'
            '  if [ "$1" = "-o" ]; then shift; out=$1; fi\n'
            '  shift\n'
            'done\n'
            '[ -n "$out" ] || exit 73\n'
            'cp "$FAKE_BOOTSTRAP_SOURCE" "$out"\n',
        )
        self._write(self.bin / "ssh", '#!/bin/sh\nexit 0\n')
        self._write(self.bin / "uname", '#!/bin/sh\nprintf "%s\\n" "${FAKE_OS:-Darwin}"\n')

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, contents: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        path.chmod(0o755)

    @staticmethod
    def _uv_program() -> str:
        return '''#!/bin/sh
printf 'uv %s\\n' "$*" >> "$FAKE_LOG"
if [ "$1" = tool ] && [ "$2" = install ]; then
  [ "${UV_INSTALL_EXIT:-0}" -eq 0 ] || exit "$UV_INSTALL_EXIT"
  mkdir -p "$HOME/.local/bin"
  printf '#!/bin/sh\\nprintf "ssh-ls 9.8.7\\\\n"\\n' > "$HOME/.local/bin/ssh-ls"
  chmod +x "$HOME/.local/bin/ssh-ls"
  exit 0
fi
if [ "$1" = tool ] && [ "$2" = dir ] && [ "$3" = --bin ]; then
  printf '%s\\n' "$HOME/.local/bin"
  exit 0
fi
exit 74
'''

    def _env(self, **extra: str) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(self.home),
                "PATH": f"{self.bin}:/usr/bin:/bin",
                "FAKE_LOG": str(self.log),
                "FAKE_UV_TEMPLATE": str(self.uv_template),
                "FAKE_BOOTSTRAP_SOURCE": str(self.bootstrap_source),
                **extra,
            }
        )
        return env

    def _run(self, **env: str) -> subprocess.CompletedProcess[str]:
        self.assertTrue(INSTALLER.is_file(), f"installer missing: {INSTALLER}")
        return subprocess.run(
            ["sh", str(INSTALLER)],
            cwd=REPO,
            env=self._env(**env),
            text=True,
            capture_output=True,
            timeout=30,
        )

    def _install_log(self) -> str:
        return self.log.read_text() if self.log.exists() else ""

    def test_reuses_uv_on_path_and_verifies_installed_binary(self) -> None:
        self._write(self.bin / "uv", self._uv_program())

        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self._install_log()
        self.assertIn("uv tool install --upgrade --refresh --python 3.11 https://github.com/Moviw/ssh-ls/releases/latest/download/ssh-ls.tar.gz", calls)
        self.assertIn("uv tool dir --bin", calls)
        self.assertIn("ssh-ls 9.8.7", result.stdout + result.stderr)
        self.assertNotIn("curl ", calls)

    def test_bootstraps_uv_from_downloaded_official_installer(self) -> None:
        isolated_tmp = self.root / "tmp"
        isolated_tmp.mkdir()
        result = self._run(TMPDIR=str(isolated_tmp))

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self._install_log()
        self.assertIn("curl ", calls)
        self.assertTrue((self.home / ".local/bin/uv").is_file())
        self.assertIn("tool install --upgrade --refresh --python 3.11", calls)
        self.assertIn("ssh-ls 9.8.7", result.stdout + result.stderr)
        self.assertIn("Add", result.stdout)
        self.assertEqual(list(isolated_tmp.iterdir()), [])

    def test_successful_install_preserves_ssh_and_shell_state(self) -> None:
        self._write(self.bin / "uv", self._uv_program())
        fixtures = {
            ".ssh/config": b"Host fixture\n  HostName example.invalid\n",
            ".zsh_history": b": 1720000000:0;echo keep\n\xff",
            ".zshrc": b"export KEEP_ME='unchanged'\n",
            ".config/ssh-ls/state.json": b'{"fixture":true}\n',
        }
        for relative_path, contents in fixtures.items():
            path = self.home / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)

        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        for relative_path, contents in fixtures.items():
            with self.subTest(path=relative_path):
                self.assertEqual((self.home / relative_path).read_bytes(), contents)

    def test_uses_local_uv_when_not_on_path(self) -> None:
        local_uv = self.home / ".local/bin/uv"
        self._write(local_uv, self._uv_program())

        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self._install_log()
        self.assertIn("uv tool install", calls)
        self.assertNotIn("curl ", calls)

    def test_download_failure_stops_before_uv_install(self) -> None:
        result = self._run(CURL_EXIT="23")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("curl ", self._install_log())
        self.assertNotIn("uv tool install", self._install_log())

    def test_uv_install_failure_stops_before_version_check(self) -> None:
        self._write(self.bin / "uv", self._uv_program())

        result = self._run(UV_INSTALL_EXIT="42")

        self.assertEqual(result.returncode, 42)
        calls = self._install_log()
        self.assertIn("uv tool install", calls)
        self.assertNotIn("uv tool dir --bin", calls)
        self.assertNotIn("ssh-ls 9.8.7", result.stdout + result.stderr)

    def test_rejects_unsupported_operating_system_before_downloading(self) -> None:
        result = self._run(FAKE_OS="FreeBSD")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("supported", (result.stdout + result.stderr).lower())
        self.assertNotIn("curl ", self._install_log())


if __name__ == "__main__":
    unittest.main()
