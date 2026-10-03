"""Release lookup and safe lifecycle operations for ssh-ls."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


API_URL = "https://api.github.com/repos/Moviw/ssh-ls/releases/latest"
REPOSITORY = "https://github.com/Moviw/ssh-ls"
ASSET_NAME = "ssh-ls.tar.gz"
MAX_RESPONSE_BYTES = 64 * 1024
VERSION_PATTERN = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\+([0-9A-Za-z.-]+))?$")


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    asset_url: str


@dataclass(frozen=True)
class Installation:
    """A confirmed uv-managed installation; never inferred from PATH alone."""

    prefix: Path
    uv: Path
    bin_dir: Path


def _version_tuple(version: str) -> tuple[int, int, int] | None:
    match = VERSION_PATTERN.fullmatch(version.strip())
    if not match:
        return None
    return tuple(int(match.group(index)) for index in (1, 2, 3))


def compare_versions(left: str, right: str) -> int:
    """Compare stable SemVer versions numerically; invalid values compare equal."""
    left_parts, right_parts = _version_tuple(left), _version_tuple(right)
    if left_parts is None or right_parts is None:
        return 0
    return (left_parts > right_parts) - (left_parts < right_parts)


def _repo_url(value: object, expected_path: str) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.path != expected_path or parsed.query or parsed.fragment:
        return None
    return value


def _latest_release(timeout: float = 2.0) -> Release | None:
    """Fetch and validate the latest stable release, without comparing versions."""
    request = Request(API_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "ssh-ls"})
    with urlopen(request, timeout=timeout) as response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        return None
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict) or data.get("draft") is True or data.get("prerelease") is True:
        return None
    tag = data.get("tag_name")
    version_parts = _version_tuple(tag) if isinstance(tag, str) else None
    if version_parts is None:
        return None
    tag_value = tag[1:] if tag.startswith("v") else tag
    release_url = _repo_url(data.get("html_url"), f"/Moviw/ssh-ls/releases/tag/{tag}")
    if release_url is None:
        return None
    expected_asset_url = f"{REPOSITORY}/releases/download/{tag}/ssh-ls.tar.gz"
    assets = data.get("assets")
    if not isinstance(assets, list):
        return None
    asset_urls = [asset.get("browser_download_url") for asset in assets if isinstance(asset, dict) and asset.get("name") == ASSET_NAME]
    if len(asset_urls) != 1 or asset_urls[0] != expected_asset_url:
        return None
    return Release(version=tag_value, url=release_url, asset_url=expected_asset_url)


def available_update(current_version: str, timeout: float = 2.0) -> Release | None:
    """Return the validated stable GitHub release when newer, or None offline."""
    try:
        release = _latest_release(timeout)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeError, TypeError, json.JSONDecodeError):
        return None
    if release is None or compare_versions(release.version, current_version) <= 0:
        return None
    return release


def _find_uv(path: str | None = None, home: Path | None = None) -> Path | None:
    found = shutil.which("uv", path=path)
    if found:
        return Path(found).expanduser().resolve()
    candidate = (home or Path.home()) / ".local" / "bin" / "uv"
    return candidate.resolve() if candidate.is_file() and os.access(candidate, os.X_OK) else None


def _is_official_source(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.fragment:
        return False
    if parsed.path == "/Moviw/ssh-ls/archive/refs/heads/main.tar.gz":
        return True
    if parsed.path == "/Moviw/ssh-ls/releases/latest/download/ssh-ls.tar.gz":
        return True
    match = re.fullmatch(r"/Moviw/ssh-ls/releases/download/(v?\d+\.\d+\.\d+(?:\+[0-9A-Za-z.-]+)?)/ssh-ls\.tar\.gz", parsed.path)
    return bool(match and _version_tuple(match.group(1)) is not None)


def detect_uv_installation(prefix: Path | str | None = None, *, path: str | None = None, home: Path | None = None) -> Installation | None:
    """Confirm uv ownership from its receipt, official source and installed entrypoint."""
    try:
        resolved = Path(prefix or sys.prefix).expanduser().resolve(strict=True)
        receipt = resolved / "uv-receipt.toml"
        if resolved.name != "ssh-ls" or not receipt.is_file():
            return None
        metadata = tomllib.loads(receipt.read_text(encoding="utf-8"))
        tool = metadata.get("tool", {})
        if not isinstance(tool, dict):
            return None
        requirements = tool.get("requirements", [])
        if not isinstance(requirements, list) or not any(
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and item["name"].lower().replace("_", "-") == "ssh-ls"
            and _is_official_source(item.get("url"))
            for item in requirements
        ):
            return None
        entrypoints = tool.get("entrypoints", [])
        if not isinstance(entrypoints, list):
            return None
        entrypoint_records = [item for item in entrypoints if isinstance(item, dict) and item.get("name") == "ssh-ls"]
        if len(entrypoint_records) != 1 or not isinstance(entrypoint_records[0].get("install-path"), str):
            return None
        installed_entrypoint = Path(entrypoint_records[0]["install-path"]).expanduser()
        if not installed_entrypoint.is_absolute():
            return None
        resolved_entrypoint = installed_entrypoint.resolve(strict=True)
        resolved_entrypoint.relative_to(resolved)
        if not installed_entrypoint.is_symlink():
            return None
        uv = _find_uv(path, home)
        if uv is None:
            return None
        return Installation(prefix=resolved, uv=uv, bin_dir=installed_entrypoint.parent.resolve(strict=True))
    except (OSError, ValueError, RuntimeError, tomllib.TOMLDecodeError):
        return None


def update(current_version: str, *, installation: Installation | None = None) -> int:
    try:
        release = _latest_release()
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeError, TypeError, json.JSONDecodeError) as exc:
        print(f"Could not check GitHub for the latest ssh-ls release: {exc}", file=sys.stderr)
        return 1
    if release is None:
        print("GitHub did not return a valid stable ssh-ls release with the expected asset.", file=sys.stderr)
        return 1
    if compare_versions(release.version, current_version) <= 0:
        print(f"ssh-ls {current_version} is already up to date.")
        return 0
    installation = installation or detect_uv_installation()
    if installation is None:
        print("ssh-ls can only update its uv-managed installation. For pipx or source installs, update it with that installation method.", file=sys.stderr)
        return 1
    print(f"Updating ssh-ls to {release.version}…")
    env = {**os.environ, "UV_TOOL_DIR": str(installation.prefix.parent), "UV_TOOL_BIN_DIR": str(installation.bin_dir)}
    try:
        result = subprocess.run(
            [str(installation.uv), "tool", "install", "--upgrade", "--refresh", "--python", "3.11", release.asset_url],
            check=False,
            env=env,
        )
    except OSError as exc:
        print(f"Could not start uv: {exc}", file=sys.stderr)
        return 1
    return result.returncode


def uninstall(*, installation: Installation | None = None, yes: bool = False, input_fn=input) -> int:
    installation = installation or detect_uv_installation()
    if installation is None:
        print("Refusing to remove this installation: it is not confirmed as uv-managed. For pipx or source installs, remove it with that installation method.", file=sys.stderr)
        return 1
    if not yes:
        try:
            answer = input_fn("Uninstall ssh-ls? App settings, saved state, SSH files, uv and Python will be kept. [y/N] ")
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer.strip().lower() not in {"y", "yes"}:
            print("Uninstall cancelled.")
            return 0
    env = {**os.environ, "UV_TOOL_DIR": str(installation.prefix.parent), "UV_TOOL_BIN_DIR": str(installation.bin_dir)}
    try:
        result = subprocess.run([str(installation.uv), "tool", "uninstall", "ssh-ls"], check=False, env=env)
    except OSError as exc:
        print(f"Could not start uv: {exc}", file=sys.stderr)
        return 1
    return result.returncode
