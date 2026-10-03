import copy
import os
import shlex
import shutil
import time
import uuid
from pathlib import Path

from .discovery import discover_config, discover_history
from .launch import build_argv, effective, validate
from .models import Host
from .store import START_TABS, StateError, Store

EDITABLE = ("hostname", "user", "port", "port_explicit", "identities", "jump", "extra_args")
META = ("label", "favorite", "hidden", "production", "last_used", "uses", "order")


def demo_hosts():
    now = time.time()
    return [
        Host("demo:atlas", "atlas-dev", "atlas.example.test", alias="atlas-dev", user="developer", sources=["config:demo:2"], favorite=True, last_used=now-120, uses=18, order=0),
        Host("demo:nebula", "nebula-gpu", "gpu.example.test", user="researcher", port=2222, sources=["history:zsh:demo"], last_used=now-7200, uses=4, order=1),
        Host("demo:prod", "prod-api", "api.example.test", alias="prod-api", user="deploy", jump="bastion.example.test", sources=["config:demo:8"], production=True, order=2),
        Host("demo:lab", "lab-box", "lab.example.test", user="student", sources=["custom"], custom=True, order=3),
    ]


class Service:
    def __init__(self, *, configs=None, histories=None, no_history=False, demo=False, store=None):
        self.configs, self.histories = configs, histories
        self.no_history, self.demo = no_history, demo
        self.store = store or Store()
        self.hosts = []
        self.warnings = []
        self.settings = Store.empty()["settings"].copy()
        self._base = {}
        self._demo_records = {}
        self.state_error = ""
        self.reload()

    def reload(self):
        self.warnings = []
        if self.demo:
            entries = demo_hosts()
            records = self._demo_records
        else:
            entries, warnings = discover_config(self.configs)
            self.warnings.extend(warnings)
            if not self.no_history:
                history, warnings = discover_history(self.histories)
                self.warnings.extend(warnings)
                for item in history:
                    # ponytail: fold only exact alias references; don't guess DNS/IP equivalence.
                    match = next((h for h in entries if h.alias == item.hostname and h.config_path == item.config_path and (not item.user or h.user == item.user) and (not item.port_explicit or h.port == item.port) and not item.identities and not item.jump and not item.extra_args), None)
                    if match:
                        match.sources = list(dict.fromkeys(match.sources + item.sources))
                        match.last_used = max(match.last_used, item.last_used)
                    else:
                        entries.append(item)
            try:
                state = self.store.read()
                self.settings = {**Store.empty()["settings"], **state.get("settings", {})}
                records = state["hosts"]
                self.state_error = ""
            except StateError as exc:
                self.state_error = str(exc)
                self.warnings.append(self.state_error)
                records = {}
        self._base = {h.id: copy.deepcopy(h) for h in entries}
        by_id = {h.id: h for h in entries}
        for index, host in enumerate(entries):
            host.order = index
        for host_id, data in records.items():
            try:
                saved = Host.from_dict(data)
                validate(saved)
                if saved.id != host_id:
                    raise ValueError("record identity mismatch")
                if host_id in by_id:
                    host = by_id[host_id]
                    for name in META:
                        setattr(host, name, copy.deepcopy(getattr(saved, name)))
                    host.overrides = {k: v for k, v in saved.overrides.items() if k in EDITABLE}
                    for name, value in host.overrides.items():
                        setattr(host, name, copy.deepcopy(value))
                    validate(host)
                elif saved.custom or saved.history and (saved.favorite or saved.overrides):
                    by_id[host_id] = saved
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                self.warnings.append(f"Ignored invalid saved host {host_id}: {exc}")
        self.hosts = sorted(by_id.values(), key=lambda h: h.order)

    def _write(self, host):
        if self.demo:
            self._demo_records[host.id] = host.to_dict()
        else:
            if self.state_error:
                raise StateError(self.state_error)
            self.store.save_host(host)

    def save(self, host):
        validate(host)
        baseline = self._base.get(host.id)
        if baseline and host.port != baseline.port:
            host.port_explicit = True
        if baseline:
            host.overrides = {name: copy.deepcopy(getattr(host, name)) for name in EDITABLE if getattr(host, name) != getattr(baseline, name) or host.custom and name in baseline.overrides}
        elif host.alias is not None:
            previous = next((h for h in self.hosts if h.id == host.id), None)
            if previous:
                for name in EDITABLE:
                    if getattr(host, name) != getattr(previous, name):
                        host.overrides[name] = copy.deepcopy(getattr(host, name))
        self._write(host)
        for index, existing in enumerate(self.hosts):
            if existing.id == host.id:
                self.hosts[index] = host
                break
        else:
            self.hosts.append(host)
        return host

    def delete(self, host):
        if host.custom:
            if self.demo:
                self._demo_records.pop(host.id, None)
            else:
                if self.state_error:
                    raise StateError(self.state_error)
                self.store.remove_host(host.id)
            self.hosts = [h for h in self.hosts if h.id != host.id]
        else:
            host.hidden = True
            self.save(host)

    def duplicate(self, host):
        duplicate = copy.deepcopy(host)
        duplicate.id = "custom:" + uuid.uuid4().hex
        duplicate.label += " copy"
        duplicate.custom, duplicate.hidden = True, False
        duplicate.sources = ["custom"]
        duplicate.last_used, duplicate.uses = 0, 0
        duplicate.order = max((h.order for h in self.hosts), default=-1) + 1
        self._base[duplicate.id] = copy.deepcopy(duplicate)
        return self.save(duplicate)

    def move(self, host, delta):
        visible = sorted((h for h in self.hosts if not h.hidden), key=lambda h: h.order)
        index = next((i for i, h in enumerate(visible) if h.id == host.id), None)
        if index is None or not 0 <= index + delta < len(visible):
            return
        other = visible[index + delta]
        # IDs, not list positions, are persisted; filtered views never target a different host.
        host.order, other.order = other.order, host.order
        if self.demo:
            for h in (host, other):
                self._write(h)
        else:
            if self.state_error:
                raise StateError(self.state_error)
            self.store.update(lambda data: data["hosts"].update({h.id: h.to_dict() for h in (host, other)}))
        self.hosts.sort(key=lambda h: h.order)

    def reset_overrides(self, host):
        if host.id not in self._base:
            return host
        base = self._base[host.id]
        for name in EDITABLE:
            setattr(host, name, copy.deepcopy(getattr(base, name)))
        host.overrides = {}
        return self.save(host)

    def restore_hidden(self):
        for host in list(self.hosts):
            if host.hidden:
                host.hidden = False
                self.save(host)

    def save_settings(self, settings):
        candidate = {**self.settings, **settings}
        if candidate.get("row_height") not in (1, 3) or not isinstance(candidate.get("ascii"), bool):
            raise ValueError("Invalid display settings")
        accent = candidate.get("accent", "")
        import re
        if not isinstance(accent, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
            raise ValueError("Accent must be a six-digit hex color")
        start_tab = candidate.get("start_tab")
        if not isinstance(start_tab, str) or start_tab not in START_TABS:
            raise ValueError("Invalid start tab")
        if not self.demo:
            if self.state_error:
                raise StateError(self.state_error)
            self.store.save_settings(candidate)
        self.settings = candidate

    def record_use(self, host):
        host.last_used = time.time()
        host.uses += 1
        self.save(host)

    def argv(self, host, command=None):
        return build_argv(host, command)

    def effective(self, host):
        if self.demo:
            return "DEMO: no command executed.\nhostname atlas.example.test\nuser developer\nport 22"
        return effective(host)

    def diagnose(self, host=None):
        if self.demo:
            return "DEMO: local diagnostic preview only; no configuration or agent inspected."
        lines = [f"OpenSSH: {shutil.which('ssh') or 'NOT FOUND'}", f"State readable: {'NO' if self.state_error else 'yes'}", f"Agent socket configured: {'yes' if os.environ.get('SSH_AUTH_SOCK') else 'no'}", f"Hosts discovered: {len(self.hosts)}"]
        if host:
            lines += [f"Command: {shlex.join(self.argv(host))}", "Displayed config fields are declared estimates. Use v for an explicit effective-config check."]
            for identity in host.identities:
                path = Path(identity).expanduser()
                lines.append(f"Identity path {identity}: {'exists' if path.exists() else 'not found (may contain SSH tokens)'}")
        if self.warnings:
            lines += ["Warnings:", *self.warnings]
        lines.append("No server contacted, private key read, agent queried or ssh -G executed.")
        return "\n".join(lines)
