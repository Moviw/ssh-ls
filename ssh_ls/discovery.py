"""Read-only discovery of SSH hosts from config and shell history."""
from __future__ import annotations

import glob
import hashlib
import os
import re
import shlex
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlsplit

from .models import Host

_SAFE_HISTORY_OPTIONS = {"user", "port", "identityfile", "proxyjump"}
_SHELL_META = re.compile(r"[|&;<>()$`\n\r]")
_WILDCARD = re.compile(r"[*?!\[]")


def _stable_id(*parts: str) -> str:
    raw = "\0".join(parts).encode("utf-8", "surrogatepass")
    return hashlib.sha256(raw).hexdigest()[:20]


def _config_tokens(line: str) -> list[str]:
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    if tokens and "=" in tokens[0]:
        key, first = tokens[0].split("=", 1)
        tokens = [key, first, *tokens[1:]] if first else [key, *tokens[1:]]
    if len(tokens) > 1 and tokens[1] == "=":
        del tokens[1]
    return tokens


def _host_pattern_matches(pattern: str, alias: str) -> bool:
    return not _WILDCARD.search(pattern) and pattern.casefold() == alias.casefold()


def _literal_aliases(patterns: Iterable[str]) -> list[str]:
    """Return positive literal Host names only; wildcard patterns are not hosts."""
    positive = [p for p in patterns if not p.startswith("!") and not _WILDCARD.search(p)]
    negative = [p[1:] for p in patterns if p.startswith("!")]
    return [alias for alias in positive if not any(_host_pattern_matches(n, alias) for n in negative)]


def _read_config_root(root_path: Path, include_root: Path, warnings: list[str]) -> list[tuple[str, str, str, int, Path]]:
    """Read config directives, expanding Include without executing anything."""
    records: list[tuple[str, str, str, int, Path]] = []
    active: set[Path] = set()

    def read_file(path: Path, aliases: list[str]) -> None:
        path = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
        try:
            identity = path.resolve()
        except (OSError, RuntimeError):
            identity = path
        if identity in active:
            warnings.append(f"Config include cycle skipped: {path}")
            return
        if not path.is_file():
            return
        active.add(identity)
        current_aliases = aliases
        try:
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                for number, line in enumerate(stream, 1):
                    tokens = _config_tokens(line)
                    if not tokens:
                        continue
                    key = tokens[0].casefold()
                    values = tokens[1:]
                    if key == "host":
                        current_aliases = _literal_aliases(values)
                        # Record the declaration even when it has no options.
                        for alias in current_aliases:
                            records.append((alias, "__host__", alias, number, path))
                    elif key == "match":
                        # Match predicates are not evaluated (especially Match exec).
                        current_aliases = []
                    elif key == "include":
                        for value in values:
                            include = Path(os.path.expanduser(value))
                            # OpenSSH resolves relative Includes from the active
                            # user's ~/.ssh or system /etc/ssh config root.
                            if not include.is_absolute():
                                include = include_root / include
                            pattern = os.path.abspath(os.fspath(include))
                            matches = sorted(glob.glob(pattern))
                            if not matches:
                                warnings.append(f"SSH config Include matched no files: {pattern}")
                            for match in matches:
                                read_file(Path(match), current_aliases)
                    elif current_aliases and values:
                        value = " ".join(values)
                        for alias in current_aliases:
                            records.append((alias, key, value, number, path))
        except OSError:
            warnings.append(f"Unable to read SSH config: {path}")
        finally:
            active.discard(identity)

    read_file(root_path, [])
    return records


def discover_config(paths: list[Path] | None = None) -> tuple[list[Host], list[str]]:
    """Discover literal aliases in default SSH configs or explicit ``-F`` files.

    No ssh subprocess, network operation, or Match exec is used. Explicit config
    paths are treated as custom ``-F`` roots; defaults leave config_path empty so
    the SSH client can apply its native default configuration.
    """
    warnings: list[str] = []
    custom = paths is not None
    if paths is None:
        home = Path.home()
        roots = [(home / ".ssh/config", home / ".ssh"),
                 (Path("/etc/ssh/ssh_config"), Path("/etc/ssh"))]
    else:
        roots = [(Path(p).expanduser(), Path.home() / ".ssh") for p in paths]

    # First-obtained values win as in OpenSSH. IdentityFile is additive.
    found: dict[tuple[str, str], dict[str, object]] = {}
    for root_path, include_root in roots:
        root_abs = root_path.absolute()
        if custom and not root_abs.is_file():
            warnings.append(f"Explicit SSH config not found: {root_abs}")
        config_label = str(root_abs) if custom else ""
        for alias, key, value, line_number, source_path in _read_config_root(root_path, include_root, warnings):
            identity = (config_label or "default", alias)
            row = found.setdefault(identity, {
                "alias": alias, "hostname": alias, "user": "", "port": 22,
                "identities": [], "jump": "", "extra_args": [], "sources": [],
                "config_path": config_label, "seen": set(),
            })
            source = f"config:{source_path}:{line_number}"
            if source not in row["sources"]:
                row["sources"].append(source)
            if key == "__host__":
                continue
            if key == "hostname":
                if "hostname" not in row["seen"]:
                    row["hostname"] = value
                    row["seen"].add("hostname")
            elif key == "user":
                if "user" not in row["seen"]:
                    row["user"] = value
                    row["seen"].add("user")
            elif key == "port":
                if "port" not in row["seen"]:
                    try:
                        port = int(value)
                        if 1 <= port <= 65535:
                            row["port"] = port
                            row["seen"].add("port")
                        else:
                            warnings.append(f"Invalid SSH port skipped in {source}")
                    except ValueError:
                        warnings.append(f"Invalid SSH port skipped in {source}")
            elif key == "identityfile":
                row["identities"].append(value)
            elif key == "proxyjump":
                if "jump" not in row["seen"]:
                    row["jump"] = value
                    row["seen"].add("jump")
            # Other native options stay in the config and are not replayed as
            # -o arguments: the launch layer already uses the config file.

    hosts = [
        Host(
            id=_stable_id(identity[0], identity[1]),
            label=str(row["alias"]), hostname=str(row["hostname"]),
            alias=str(row["alias"]), user=str(row["user"]), port=int(row["port"]),
            identities=list(row["identities"]), jump=str(row["jump"]),
            config_path=str(row["config_path"]), extra_args=[],
            sources=list(row["sources"]),
        )
        for identity, row in found.items()
    ]
    return hosts, warnings


def _history_records(path: Path, warnings: list[str]) -> Iterable[tuple[int, str, float]]:
    if not path.is_file():
        return
    pending_bash_timestamp = 0.0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for number, line in enumerate(stream, 1):
                command = line.rstrip("\r\n")
                timestamp = 0.0
                if command.startswith("#") and command[1:].isdigit():
                    pending_bash_timestamp = float(command[1:])
                    continue
                if command.startswith(": ") and ";" in command:
                    prefix, command = command.split(";", 1)
                    match = re.match(r"^: (\d+):\d+$", prefix)
                    if match:
                        timestamp = float(match.group(1))
                elif pending_bash_timestamp:
                    timestamp = pending_bash_timestamp
                    pending_bash_timestamp = 0.0
                if command.strip():
                    yield number, command.strip(), timestamp
    except OSError:
        warnings.append(f"Unable to read shell history: {path}")


def _destination(value: str) -> tuple[str, str, int | None]:
    if value.startswith("ssh://"):
        try:
            parsed = urlsplit(value)
            if parsed.scheme != "ssh" or not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
                return "", "", None
            return parsed.hostname, unquote(parsed.username or ""), parsed.port
        except ValueError:
            return "", "", None
    if value.startswith("-"):
        return "", "", None
    if "@" in value:
        user, host = value.rsplit("@", 1)
    else:
        user, host = "", value
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return (host, user, None) if host else ("", "", None)


def _parse_ssh_command(command: str) -> dict[str, object] | None:
    # Reject shell operators/substitution rather than trying to partially parse
    # a command that may not represent a direct ssh invocation.
    if _SHELL_META.search(command):
        return None
    try:
        words = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not words:
        return None
    i = 0
    base = os.path.basename(words[i])
    if base == "command":
        i += 1
        if i >= len(words):
            return None
        base = os.path.basename(words[i])
    if base == "env":
        i += 1
        # Environment changes may affect HOME, SSH_AUTH_SOCK, PATH, and option
        # interpretation; without shell state they cannot be modeled safely.
        if i < len(words) and "=" in words[i] and not words[i].startswith("-"):
            return None
        if i >= len(words):
            return None
        base = os.path.basename(words[i])
    if base != "ssh":
        return None
    i += 1
    result: dict[str, object] = {"user": "", "port": 22, "port_explicit": False,
                                "identities": [], "jump": "", "config_path": ""}
    destination = ""
    while i < len(words):
        word = words[i]
        if word == "--":
            i += 1
            if i < len(words):
                destination = words[i]
            break
        if not word.startswith("-") or word == "-":
            destination = word
            break
        if word in ("-p", "-l", "-i", "-J", "-F", "-o"):
            i += 1
            if i >= len(words):
                return None
            option_value = words[i]
            opt = word[1:]
        elif word.startswith("-o") and len(word) > 2:
            option_value, opt = word[2:], "o"
        elif len(word) > 2 and word[:2] in ("-p", "-l", "-i", "-J", "-F"):
            option_value, opt = word[2:], word[1]
        else:
            return None
        if opt == "p":
            try:
                port = int(option_value)
            except ValueError:
                return None
            if not 1 <= port <= 65535:
                return None
            result["port"] = port
            result["port_explicit"] = True
        elif opt == "l":
            result["user"] = option_value
        elif opt == "i":
            if not _stable_history_path(option_value):
                return None
            result["identities"].append(option_value)
        elif opt == "J":
            result["jump"] = option_value
        elif opt == "F":
            if not _stable_history_path(option_value):
                return None
            result["config_path"] = option_value
        elif opt == "o":
            if "=" in option_value:
                key, value = option_value.split("=", 1)
            else:
                pair = option_value.split(None, 1)
                if len(pair) != 2:
                    return None
                key, value = pair
            key = key.casefold()
            if key not in _SAFE_HISTORY_OPTIONS:
                return None
            if key == "user":
                result["user"] = value
            elif key == "port":
                try:
                    port = int(value)
                except ValueError:
                    return None
                if not 1 <= port <= 65535:
                    return None
                result["port"] = port
                result["port_explicit"] = True
            elif key == "identityfile":
                if not _stable_history_path(value):
                    return None
                result["identities"].append(value)
            elif key == "proxyjump":
                result["jump"] = value
        i += 1
    host, url_user, url_port = _destination(destination)
    if not host:
        return None
    if url_user and not result["user"]:
        result["user"] = url_user
    if url_port is not None and not result["port_explicit"]:
        if not 1 <= url_port <= 65535:
            return None
        result["port"] = url_port
        result["port_explicit"] = True
    safe_values = [host, str(result["user"]), str(result["jump"]), str(result["config_path"]),
                   *(str(identity) for identity in result["identities"])]
    if any(any(ord(char) < 32 or ord(char) == 127 for char in value) for value in safe_values):
        return None
    username = str(result["user"])
    if (host.startswith("-") or any(char.isspace() for char in host)
            or "@" in username or any(char.isspace() for char in username)):
        return None
    result["hostname"] = host
    return result


def _stable_history_path(value: str) -> bool:
    """Only retain history paths with a cwd-independent interpretation."""
    return value.startswith("~/") or Path(value).is_absolute()


def discover_history(paths: list[Path] | None = None) -> tuple[list[Host], list[str]]:
    """Extract simple SSH connection commands from zsh/bash histories."""
    warnings: list[str] = []
    history_paths = [Path(p).expanduser() for p in paths] if paths is not None else [
        Path.home() / ".zsh_history", Path.home() / ".bash_history"
    ]
    found: dict[tuple[str, str, int, tuple[str, ...], str, str, bool], Host] = {}
    for path in history_paths:
        for line_number, command, timestamp in _history_records(path, warnings):
            parsed = _parse_ssh_command(command)
            if parsed is None:
                continue
            hostname = str(parsed["hostname"])
            user = str(parsed["user"])
            port = int(parsed["port"])
            identities = tuple(str(x) for x in parsed["identities"])
            jump = str(parsed["jump"])
            config_path = str(parsed["config_path"])
            port_explicit = bool(parsed["port_explicit"])
            key = (hostname.casefold(), user, port, identities, jump, config_path, port_explicit)
            source = f"history:{path.absolute()}:{line_number}"
            if key in found:
                host = found[key]
                host.last_used = max(host.last_used, timestamp)
                if source not in host.sources:
                    host.sources.append(source)
                continue
            dest = f"{user}@{hostname}" if user else hostname
            found[key] = Host(
                id=_stable_id("history", *map(str, key)), label=dest,
                hostname=hostname, user=user, port=port, identities=list(identities),
                jump=jump, config_path=config_path, port_explicit=port_explicit,
                last_used=timestamp,
                sources=[source],
            )
    return list(found.values()), warnings
