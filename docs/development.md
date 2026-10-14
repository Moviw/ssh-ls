# Development

```sh
git clone https://github.com/Moviw/ssh-ls.git
cd ssh-ls
uv sync
uv run ssh-ls
```

## Tests

```sh
uv run python -m unittest discover -s tests -v
uv build
```

The suite covers discovery, native argument construction, state persistence, Textual keyboard interaction, and terminal handoff. Tests use fictional or temporary data, not your real SSH credentials.

An optional integration test creates a temporary localhost SSH server and keys:

```sh
# Requires an installed OpenSSH server (sshd).
SSH_LS_INTEGRATION=1 uv run python -m unittest discover -s tests -p test_native_ssh.py -v
```

CI runs Python 3.11 and 3.14 on macOS and Ubuntu. Ubuntu jobs also run the native SSH integration test.

## Changes

Keep changes focused and add a regression test when fixing behavior. Use fictional hostnames and temporary paths in tests, examples, screenshots, and issue reports. Don't add real host inventories, private keys, or shell history.

The implementation has three boundaries: discovery reads source files, the service manages app-owned state, and the launcher hands control to OpenSSH. UI code should not make SSH connections itself.

## Test releases

GitHub Releases and PyPI publishing are configured. Homebrew distribution is not configured.

Update the version in `pyproject.toml`, `ssh_ls/__init__.py`, and `uv.lock` together. After main passes CI, push a matching `vX.Y.Z` tag. CI verifies the tag matches the package version, reruns the test matrix, then publishes a stable GitHub Release with `ssh-ls.tar.gz`. The installer uses the latest stable asset; built-in updates pin the returned version. Release notes come from GitHub's generated notes.

## PyPI publishing

The workflow is `.github/workflows/workflow.yml`. A matching `vX.Y.Z` tag tests, builds, and publishes that version through PyPI Trusted Publishing. The existing `ci.yml` publishes the GitHub Release from the same tag.

Register a pending publisher on PyPI with these exact fields:

| Field | Value |
| --- | --- |
| PyPI project name | `ssh-ls` |
| Owner | `Moviw` (the GitHub owner, not the PyPI display name) |
| Repository name | `ssh-ls` |
| Workflow name | `workflow.yml` |
| Environment name | `pypi` |

In GitHub **Settings → Environments**, create `pypi`. No PyPI token or password is needed. See [PyPI's Trusted Publishing guide](https://docs.pypi.org/trusted-publishers/using-a-publisher/). A pending publisher does not reserve a package name. Each PyPI version can be uploaded only once, so use a new version and tag for subsequent releases.
