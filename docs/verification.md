# Verification checklist

This file defines reproducible checks; it does not assert that they have been run or passed. CI is the execution record for the automated suite and package build.

## Automated checks

From the repository root:

```sh
uv sync
uv run python -m unittest discover -s tests -v
uv build
```

CI runs these checks on Ubuntu and macOS with Python 3.11 and 3.14. On Ubuntu only, CI also installs OpenSSH server and runs the gated localhost native-SSH test with temporary host/client-key fixtures. A green workflow is required before claiming the automated matrix has passed.

## Safe local smoke checks

Use demo mode first; it should render only synthetic `.test` hosts and must not read real SSH config/history, write user state, open a network connection, or invoke `ssh`:

```sh
uv run ssh-ls --demo
```

Exit with `q` and verify the shell prompt returns. Test help/version/doctor separately in a terminal that has no need for remote access:

```sh
uv run ssh-ls --help
uv run ssh-ls --version
uv run ssh-ls --doctor
```

For config/history parsing tests, use temporary fixture files containing only reserved `.test` hostnames and fake paths. History parsing is deliberately conservative: assignment-prefixed commands and relative `-i`/`-F` paths that cannot be resolved are rejected; no history command or remote-command text from history is ever replayed. Never point test runs at a real private key or paste shell history into logs. Any real-host SSH smoke test is optional, manual, and outside the CI integration test; it should only use a host the operator explicitly chooses.

## Native SSH CI integration check

The Ubuntu CI job installs `openssh-server`, creates `/run/sshd`, and runs the gated localhost test only when explicitly enabled:

```sh
sudo apt-get update
sudo apt-get install -y openssh-server
sudo mkdir -p /run/sshd
SSH_LS_INTEGRATION=1 uv run python -m unittest discover -s tests -p test_native_ssh.py -v
```

The test should create temporary client/server keys and bind a high localhost port; it must not read the operator’s SSH files, use public networks, or require real credentials. Do not run this integration test manually unless its fixture test is present and reviewed.

## State rollback and uninstall

Close the application before restoring a state copy. `./ROLLBACK.sh "$STATE_COPY"` restores that copy from its sibling `"$STATE_COPY.bak"`; it is scoped to the supplied copy and does not delete the project or touch SSH config/keys. Test with a disposable copy before choosing any live state path. After `uv tool install`, uninstall with `uv tool uninstall ssh-ls`.

## Evidence to record for release

- CI workflow URL and commit SHA.
- Exact OS/Python matrix results.
- `uv sync`, unit-test, and `uv build` exit statuses and literal summaries.
- Manual demo observation (synthetic records only, no SSH/network/state access).
- Any manual SSH connection test, with host identity redacted and user confirmation recorded separately.
