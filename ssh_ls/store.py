"""Small locked JSON store; original SSH files are never written."""
import fcntl
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .themes import DEFAULT_THEME, THEMES

START_TABS = ("All", "Recent", "Favorites")


class StateError(ValueError):
    pass


class Store:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "ssh-ls"
        self.path = self.directory / "state.json"

    @staticmethod
    def _validate_settings(settings):
        if (settings["row_height"] not in (1, 3)
                or not isinstance(settings["ascii"], bool)
                or not isinstance(settings["theme"], str)
                or settings["theme"] not in THEMES
                or not isinstance(settings["accent"], str)
                or (settings["accent"] != "auto" and not re.fullmatch(r"#[0-9a-fA-F]{6}", settings["accent"]))
                or not isinstance(settings["start_tab"], str)
                or settings["start_tab"] not in START_TABS):
            raise ValueError("invalid display settings")

    @staticmethod
    def empty():
        return {"version": 1, "hosts": {}, "settings": {"theme": DEFAULT_THEME, "accent": "auto", "row_height": 1, "ascii": False, "start_tab": "Recent"}}

    def read(self):
        if not self.path.exists():
            return self.empty()
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("hosts"), dict) or not isinstance(data.get("settings", {}), dict):
                raise ValueError("unexpected schema")
            if any(not isinstance(v, dict) for v in data["hosts"].values()):
                raise ValueError("invalid host record")
            settings = {**self.empty()["settings"], **data.get("settings", {})}
            # Older releases stored the Tokyo Night accent as a literal. Treat
            # that exact legacy default as preset-driven, without writing here.
            if ("theme" not in data.get("settings", {})
                    and isinstance(settings["accent"], str)
                    and settings["accent"].lower() == "#7aa2f7"):
                settings["accent"] = "auto"
            if settings["start_tab"] == "History":
                settings["start_tab"] = "Recent"
            self._validate_settings(settings)
            data["settings"] = settings
            return data
        except (OSError, ValueError, TypeError) as exc:
            raise StateError(f"Cannot read {self.path}: {exc}. Restore state.json.bak or move this file aside; it will not be overwritten.") from exc

    @contextmanager
    def locked(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        lock_path = self.directory / "state.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, "a+") as lock:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def update(self, mutation):
        with self.locked():
            data = self.read()  # reread after lock: independent host changes do not get lost
            mutation(data)
            payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            fd, name = tempfile.mkstemp(prefix=".state-", dir=self.directory)
            try:
                with os.fdopen(fd, "w") as out:
                    out.write(payload)
                    out.flush()
                    os.fsync(out.fileno())
                if self.path.exists():
                    backup = self.path.with_suffix(".json.bak")
                    backup_fd, backup_name = tempfile.mkstemp(prefix=".backup-", dir=self.directory)
                    os.close(backup_fd)
                    try:
                        shutil.copyfile(self.path, backup_name)
                        os.chmod(backup_name, 0o600)
                        os.replace(backup_name, backup)
                    finally:
                        if os.path.exists(backup_name):
                            os.unlink(backup_name)
                os.replace(name, self.path)
                os.chmod(self.path, 0o600)
                directory_fd = os.open(self.directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            return data

    def save_host(self, host):
        return self.update(lambda data: data["hosts"].__setitem__(host.id, host.to_dict()))

    def remove_host(self, host_id):
        return self.update(lambda data: data["hosts"].pop(host_id, None))

    def save_settings(self, settings):
        def mutation(data):
            candidate = {**self.empty()["settings"], **data["settings"], **settings}
            self._validate_settings(candidate)
            data["settings"] = candidate
        return self.update(mutation)
