import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ssh_ls import cli
from ssh_ls.lifecycle import Installation, Release, available_update, compare_versions, detect_uv_installation, uninstall, update


def release_payload(tag="v0.1.10", *, url=None, asset_url=None, prerelease=False):
    return json.dumps({
        "tag_name": tag,
        "draft": False,
        "prerelease": prerelease,
        "html_url": url or f"https://github.com/Moviw/ssh-ls/releases/tag/{tag}",
        "assets": [{"name": "ssh-ls.tar.gz", "browser_download_url": asset_url or f"https://github.com/Moviw/ssh-ls/releases/download/{tag}/ssh-ls.tar.gz"}],
    }).encode()


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, size=-1):
        return self.body[:size]


class LifecycleTests(unittest.TestCase):
    def test_stable_release_validation_and_numeric_comparison(self):
        self.assertEqual(compare_versions("0.1.10", "0.1.9"), 1)
        self.assertEqual(compare_versions("v1.0.0", "1.0.0"), 0)
        self.assertEqual(compare_versions("1.0.0-rc.1", "1.0.0"), 0)
        with patch("ssh_ls.lifecycle.urlopen", return_value=FakeResponse(release_payload())) as open_url:
            found = available_update("0.1.9")
        open_url.assert_called_once()
        self.assertEqual(found, Release("0.1.10", "https://github.com/Moviw/ssh-ls/releases/tag/v0.1.10", "https://github.com/Moviw/ssh-ls/releases/download/v0.1.10/ssh-ls.tar.gz"))
        with patch("ssh_ls.lifecycle.urlopen", return_value=FakeResponse(release_payload())):
            self.assertIsNone(available_update("0.1.10"))

    def test_lookup_is_silent_for_offline_prerelease_bad_links_and_oversized_data(self):
        for body in (
            b"not json",
            release_payload(prerelease=True),
            release_payload(url="https://github.com/other/project/releases/tag/v0.1.10"),
            release_payload(asset_url="https://evil.test/ssh-ls.tar.gz"),
            b"{" + b" " * 65536,
        ):
            with self.subTest(body=body[:30]), patch("ssh_ls.lifecycle.urlopen", return_value=FakeResponse(body)):
                self.assertIsNone(available_update("0.1.9"))
        with patch("ssh_ls.lifecycle.urlopen", side_effect=OSError("offline")):
            self.assertIsNone(available_update("0.1.9"))

    def test_uv_ownership_requires_receipt_layout_entrypoint_and_uv_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # Non-default tool storage is valid when the receipt and installed
            # launcher both bind back to this exact environment.
            prefix = root / "custom-store" / "ssh-ls"
            prefix.mkdir(parents=True)
            receipt = prefix / "uv-receipt.toml"
            (prefix / "bin").mkdir()
            (prefix / "bin" / "ssh-ls").write_text("launcher")
            bin_dir = root / "custom-bin"
            bin_dir.mkdir()
            (bin_dir / "ssh-ls").symlink_to(prefix / "bin" / "ssh-ls")
            receipt.write_text(f'[tool]\nrequirements = [{{ name = "ssh-ls", url = "https://github.com/Moviw/ssh-ls/archive/refs/heads/main.tar.gz" }}]\nentrypoints = [{{ name = "ssh-ls", install-path = "{bin_dir / "ssh-ls"}", from = "ssh-ls" }}]\n')
            uv = root / "uv"
            uv.write_text("fake")
            uv.chmod(0o700)
            self.assertEqual(detect_uv_installation(prefix, path=str(root)), Installation(prefix.resolve(), uv.resolve(), bin_dir.resolve()))
            receipt.write_text(f'[tool]\nrequirements = [{{ name = "ssh-ls", url = "file:///tmp/ssh-ls" }}]\nentrypoints = [{{ name = "ssh-ls", install-path = "{bin_dir / "ssh-ls"}" }}]\n')
            self.assertIsNone(detect_uv_installation(prefix, path=str(root)))
            receipt.write_text(f'[tool]\nrequirements = [{{ name = "ssh-ls", url = "https://pypi.org/project/ssh-ls" }}]\nentrypoints = [{{ name = "ssh-ls", install-path = "{bin_dir / "ssh-ls"}" }}]\n')
            self.assertIsNone(detect_uv_installation(prefix, path=str(root)))

    def test_uninstall_prompts_defaults_to_no_and_yes_runs_uv(self):
        installation = Installation(Path("/tmp/tools/ssh-ls"), Path("/tmp/uv"), Path("/tmp/bin"))
        with patch("ssh_ls.lifecycle.subprocess.run") as run:
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(uninstall(installation=installation, input_fn=lambda _prompt: "n"), 0)
            run.assert_not_called()
            self.assertIn("cancelled", output.getvalue())
        with patch("ssh_ls.lifecycle.subprocess.run", return_value=type("Result", (), {"returncode": 17})()) as run:
            self.assertEqual(uninstall(installation=installation, input_fn=lambda _prompt: "y"), 17)
            args, kwargs = run.call_args
            self.assertEqual(args[0], ["/tmp/uv", "tool", "uninstall", "ssh-ls"])
            self.assertEqual(kwargs["env"]["UV_TOOL_DIR"], "/tmp/tools")
            self.assertEqual(kwargs["env"]["UV_TOOL_BIN_DIR"], "/tmp/bin")
        with patch("ssh_ls.lifecycle.subprocess.run", return_value=type("Result", (), {"returncode": 0})()) as run:
            self.assertEqual(uninstall(installation=installation, yes=True), 0)
            run.assert_called_once()

    def test_unowned_install_refused_even_when_yes(self):
        with patch("ssh_ls.lifecycle.detect_uv_installation", return_value=None), patch("ssh_ls.lifecycle.subprocess.run") as run:
            error = io.StringIO()
            with redirect_stderr(error):
                self.assertEqual(uninstall(yes=True), 1)
            run.assert_not_called()
            self.assertIn("pipx or source", error.getvalue())

    def test_update_pins_release_and_preserves_uv_exit_code(self):
        installation = Installation(Path("/tmp/tools/ssh-ls"), Path("/tmp/uv"), Path("/tmp/bin"))
        release = Release("0.1.10", "https://github.com/Moviw/ssh-ls/releases/tag/v0.1.10", "https://github.com/Moviw/ssh-ls/releases/download/v0.1.10/ssh-ls.tar.gz")
        with patch("ssh_ls.lifecycle._latest_release", return_value=release), patch("ssh_ls.lifecycle.subprocess.run", return_value=type("Result", (), {"returncode": 23})()) as run:
            self.assertEqual(update("0.1.2", installation=installation), 23)
        self.assertEqual(run.call_args.args[0], ["/tmp/uv", "tool", "install", "--upgrade", "--refresh", "--python", "3.11", release.asset_url])
        self.assertEqual(run.call_args.kwargs["env"]["UV_TOOL_DIR"], "/tmp/tools")
        self.assertEqual(run.call_args.kwargs["env"]["UV_TOOL_BIN_DIR"], "/tmp/bin")
        with patch("ssh_ls.lifecycle._latest_release", return_value=release), patch("ssh_ls.lifecycle.subprocess.run") as run:
            self.assertEqual(update("0.1.10", installation=installation), 0)
            run.assert_not_called()

    def test_missing_uv_is_reported_without_traceback(self):
        installation = Installation(Path("/tmp/tools/ssh-ls"), Path("/tmp/uv"), Path("/tmp/bin"))
        release = Release("0.1.10", "https://github.com/Moviw/ssh-ls/releases/tag/v0.1.10", "https://github.com/Moviw/ssh-ls/releases/download/v0.1.10/ssh-ls.tar.gz")
        error = io.StringIO()
        with patch("ssh_ls.lifecycle._latest_release", return_value=release), patch("ssh_ls.lifecycle.subprocess.run", side_effect=FileNotFoundError("uv removed")), redirect_stderr(error):
            self.assertEqual(update("0.1.2", installation=installation), 1)
            self.assertEqual(uninstall(installation=installation, yes=True), 1)
        self.assertIn("Could not start uv", error.getvalue())

    def test_cli_lifecycle_routes_do_not_construct_ssh_service(self):
        with patch("ssh_ls.cli.update", return_value=31) as update_mock, patch("ssh_ls.cli.Service", side_effect=AssertionError("must not inspect SSH config")):
            self.assertEqual(cli.main(["update"]), 31)
            update_mock.assert_called_once_with(cli.__version__)
        with patch("ssh_ls.cli.uninstall", return_value=0) as uninstall_mock, patch("ssh_ls.cli.Service", side_effect=AssertionError("must not inspect SSH config")):
            self.assertEqual(cli.main(["uninstall", "--yes"]), 0)
            uninstall_mock.assert_called_once_with(yes=True)


if __name__ == "__main__":
    unittest.main()
