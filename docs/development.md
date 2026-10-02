# Development

```sh
git clone https://github.com/Moviw/ssh-ls.git
cd ssh-ls
uv sync
uv run ssh-ls --demo
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
