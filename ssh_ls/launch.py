"""OpenSSH owns authentication, configuration and the terminal session."""
import os
import math
import shlex
import shutil
import subprocess
from .models import Host


def _safe_text(value: str, name: str, *, empty=False):
    if not isinstance(value, str) or (not value and not empty) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"Invalid {name}")
    return value


def validate(host: Host):
    _safe_text(host.id, "host identity")
    for name in ("favorite", "hidden", "production", "custom", "port_explicit"):
        if not isinstance(getattr(host, name), bool):
            raise ValueError(f"Invalid {name}")
    if not isinstance(host.identities, list) or not isinstance(host.sources, list) or any(not isinstance(s, str) for s in host.sources):
        raise ValueError("Invalid identities or sources")
    if not isinstance(host.overrides, dict):
        raise ValueError("Invalid overrides")
    if isinstance(host.last_used, bool) or not isinstance(host.last_used, (int, float)) or not math.isfinite(host.last_used) or host.last_used < 0:
        raise ValueError("Invalid last-use time")
    for name in ("uses", "order"):
        value = getattr(host, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Invalid {name}")
    _safe_text(host.label, "name")
    _safe_text(host.hostname, "hostname")
    if host.hostname.startswith("-") or any(c.isspace() for c in host.hostname) or "@" in host.hostname:
        raise ValueError("Hostname must not contain whitespace, @, or start with '-'")
    if host.alias is not None:
        _safe_text(host.alias, "alias")
        if host.alias.startswith("-"):
            raise ValueError("Alias must not start with '-'")
    _safe_text(host.user, "username", empty=True)
    if any(c.isspace() for c in host.user) or "@" in host.user:
        raise ValueError("Username must not contain whitespace or @")
    if isinstance(host.port, bool) or not isinstance(host.port, int) or not 1 <= host.port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    for path in host.identities:
        _safe_text(path, "identity file")
    _safe_text(host.jump, "jump host", empty=True)
    _safe_text(host.config_path, "configuration path", empty=True)
    validate_options(host.extra_args)


def validate_options(args):
    if not isinstance(args, list) or any(not isinstance(x, str) for x in args):
        raise ValueError("SSH options must be an argument list")
    # Options only, never allow an accidental second destination/remote command.
    # OpenSSH accepts clustered flags and attached values; parse these without a shell.
    values = set("BbcDEeFIiJLlmOopQRSWw")
    flags = set("46AaCfGgKkMNnqsTtVvXxYy")
    i = 0
    while i < len(args):
        item = _safe_text(args[i], "SSH option")
        if not item.startswith("-") or item in ("-", "--"):
            raise ValueError("Only SSH options are allowed; enter remote commands using 'r'")
        body = item[1:]
        j = 0
        while j < len(body):
            flag = body[j]
            if flag in "GQVOf":
                raise ValueError(f"-{flag} changes SSH operation; use normal connections or the explicit preview action")
            if flag in values:
                if j == len(body) - 1:
                    i += 1
                    if i >= len(args):
                        raise ValueError(f"Missing value for -{flag}")
                    _safe_text(args[i], "SSH option value")
                break
            if flag not in flags:
                raise ValueError(f"Unsupported SSH option -{flag}")
            if flag in "GQVOf":
                raise ValueError(f"-{flag} changes SSH operation; use normal connections or the explicit preview action")
            j += 1
        i += 1


def build_argv(host: Host, command: str | None = None):
    validate(host)
    args = ["ssh"]
    if host.config_path:
        args += ["-F", os.path.expanduser(host.config_path)]
    changed = host.overrides
    if host.alias is None:
        if host.port_explicit:
            args += ["-p", str(host.port)]
        if host.user:
            args += ["-l", host.user]
        for identity in host.identities:
            args += ["-i", os.path.expanduser(identity)]
        if host.jump:
            args += ["-J", host.jump]
    else:
        if "hostname" in changed:
            args += ["-o", "HostName=" + host.hostname]
        if "user" in changed:
            args += ["-o", "User=" + (host.user or os.environ.get("USER", ""))]
        if "port" in changed:
            args += ["-p", str(host.port)]
        if "identities" in changed:
            for identity in host.identities:
                args += ["-i", os.path.expanduser(identity)]
        if "jump" in changed:
            args += ["-J", host.jump or "none"]
    args += host.extra_args
    args += ["--", host.alias or host.hostname]
    if command is not None:
        _safe_text(command, "remote command")
        args += [command]  # one argument; remote shell syntax is intentional, never run locally
    return args


def launch(host, command=None):
    if not shutil.which("ssh"):
        print("OpenSSH not found. Install an OpenSSH client and retry.", file=__import__("sys").stderr)
        return 127
    try:
        return subprocess.run(build_argv(host, command), shell=False).returncode
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as exc:
        print(f"Cannot start SSH: {exc}", file=__import__("sys").stderr)
        return 1


def effective(host):
    args = build_argv(host)
    args.insert(1, "-G")
    result = subprocess.run(args, capture_output=True, text=True, timeout=10, shell=False)
    return f"$ {shlex.join(args)}\nExit: {result.returncode}\n\n{result.stdout}{result.stderr}"
