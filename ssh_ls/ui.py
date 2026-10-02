"""Textual interface for ssh-ls.

The interface intentionally keeps navigation separate from editable fields: global
single-key shortcuts are ignored whenever an Input/TextArea has focus.
"""
from __future__ import annotations

import copy
import shlex
import uuid
from typing import Any

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Checkbox, Input, Label, Select, Static, TextArea

from .models import Host, LaunchRequest


THEME = {
    "bg": "#1a1b26", "surface": "#24283b", "fg": "#c0caf5", "muted": "#9aa5ce",
    "border": "#414868", "accent": "#7aa2f7", "purple": "#bb9af7",
    "warning": "#e0af68", "danger": "#f7768e", "success": "#9ece6a",
}


def _esc(value: Any) -> str:
    """Escape data before putting it in Textual markup."""
    return str(value if value is not None else "").replace("[", "\\[")


def _source_label(host: Host) -> str:
    sources = getattr(host, "sources", []) or []
    labels = []
    for source in sources:
        value = str(source)
        labels.append("history" if value.startswith("history:") else "config" if value.startswith("config:") else "custom" if value == "custom" else "other")
    if getattr(host, "custom", False):
        labels.append("custom")
    return ", ".join(dict.fromkeys(labels)) or "configured"


class FocusableStatic(Static):
    can_focus = True


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]
    CSS = """
    ConfirmScreen { align: center middle; background: #1a1b26 70%; }
    #confirm-box { width: 70; max-width: 90%; height: auto; max-height: 80%; padding: 1 2; border: round #7aa2f7; background: #24283b; }
    #confirm-text { height: auto; margin-bottom: 1; }
    #confirm-buttons { height: 3; align-horizontal: right; }
    #confirm-buttons Button { margin-left: 1; }
    """
    def __init__(self, title: str, message: str, yes: str = "Confirm", dangerous: bool = False):
        super().__init__()
        self.title_text, self.message, self.yes, self.dangerous = title, message, yes, dangerous

    def action_cancel(self) -> None: self.dismiss(False)

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(f"[b]{_esc(self.title_text)}[/b]")
            yield Static(self.message, id="confirm-text", markup=True)
            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button(self.yes, id="yes", variant="error" if self.dangerous else "primary")

    @on(Button.Pressed)
    def pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class MessageScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "cancel", "Close", priority=True)]
    CSS = """
    MessageScreen { align: center middle; background: #1a1b26 70%; }
    #message-box { width: 78; max-width: 92%; height: auto; max-height: 85%; padding: 1 2; border: round #7aa2f7; background: #24283b; }
    #message-body { height: auto; max-height: 60%; overflow-y: auto; margin: 1 0; }
    #message-close { align-horizontal: right; height: 3; }
    """
    def __init__(self, title: str, message: str):
        super().__init__()
        self.title_text, self.message = title, message

    def action_cancel(self) -> None: self.dismiss(None)

    def compose(self) -> ComposeResult:
        with Vertical(id="message-box"):
            yield Label(f"[b]{_esc(self.title_text)}[/b]")
            yield Static(self.message, id="message-body", markup=True)
            with Horizontal(id="message-close"):
                yield Button("Close", id="close", variant="primary")

    @on(Button.Pressed, "#close")
    def close(self) -> None:
        self.dismiss(None)


class HostForm(ModalScreen[dict[str, Any] | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]
    CSS = """
    HostForm { align: center middle; background: #1a1b26 70%; }
    #form-box { width: 90; max-width: 96%; height: 90%; max-height: 95%; padding: 1 2; border: round #7aa2f7; background: #24283b; }
    #form-fields { height: 1fr; overflow-y: auto; }
    .form-row { height: 3; }
    .form-label { width: 20; padding-top: 1; color: #9aa5ce; }
    .form-input { width: 1fr; }
    #identity-area { height: 5; }
    #form-actions { height: 3; align-horizontal: right; }
    #form-actions Button { margin-left: 1; }
    """
    def __init__(self, host: Host | None = None):
        super().__init__()
        self.host = host

    def action_cancel(self) -> None: self.dismiss(None)

    def _value(self, key: str, default: Any = ""):
        return str(getattr(self.host, key, default) if self.host else default)

    def compose(self) -> ComposeResult:
        h = self.host
        with Vertical(id="form-box"):
            yield Label("[b]Edit host[/b]" if h else "[b]Add SSH host[/b]")
            with VerticalScroll(id="form-fields"):
                for key, title, val, placeholder in (
                    ("label", "Label", self._value("label"), "work server"),
                    ("hostname", "Hostname / IP", self._value("hostname"), "server.example.com"),
                    ("user", "User", self._value("user"), "optional"),
                    ("port", "Port", self._value("port", 22), "22"),
                    ("jump", "Jump host", self._value("jump"), "optional"),
                ):
                    with Horizontal(classes="form-row"):
                        yield Label(title, classes="form-label")
                        yield Input(val, placeholder=placeholder, id=f"field-{key}", classes="form-input")
                with Horizontal(classes="form-row"):
                    yield Label("Identity files", classes="form-label")
                    yield TextArea("\n".join(getattr(h, "identities", []) if h else []), id="field-identities")
                with Horizontal(classes="form-row"):
                    yield Label("Extra SSH options", classes="form-label")
                    yield Input(" ".join(shlex.quote(str(x)) for x in (getattr(h, "extra_args", []) if h else [])), placeholder="e.g. -o ServerAliveInterval=30", id="field-extra", classes="form-input")
                with Horizontal(classes="form-row"):
                    yield Label("Production", classes="form-label")
                    yield Checkbox("Treat as production (confirmation required)", value=bool(getattr(h, "production", False)), id="field-production")
            with Horizontal(id="form-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Save host", id="save", variant="primary")

    def action_cancel(self) -> None: self.dismiss(None)

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save")
    def save(self) -> None:
        try:
            hostname = self.query_one("#field-hostname", Input).value.strip()
            label = self.query_one("#field-label", Input).value.strip()
            port_text = self.query_one("#field-port", Input).value.strip()
            if not hostname:
                raise ValueError("Hostname is required.")
            if not label:
                label = hostname
            port = int(port_text or "22")
            if not 1 <= port <= 65535:
                raise ValueError("Port must be between 1 and 65535.")
            extra = shlex.split(self.query_one("#field-extra", Input).value)
            data = {
                "label": label, "hostname": hostname,
                "user": self.query_one("#field-user", Input).value.strip(),
                "port": port,
                "jump": self.query_one("#field-jump", Input).value.strip(),
                "identities": [line.strip() for line in self.query_one("#field-identities", TextArea).text.splitlines() if line.strip()],
                "extra_args": extra,
                "production": self.query_one("#field-production", Checkbox).value,
            }
            if self.host:
                data["id"] = self.host.id
            self.dismiss(data)
        except (ValueError, TypeError) as exc:
            self.app.push_screen(MessageScreen("Invalid host", _esc(exc)))


class CommandScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]
    CSS = """
    CommandScreen { align: center middle; background: #1a1b26 70%; }
    #command-box { width: 78; max-width: 92%; height: auto; padding: 1 2; border: round #7aa2f7; background: #24283b; }
    #command-input { margin: 1 0; }
    #command-actions { height: 3; align-horizontal: right; }
    #command-actions Button { margin-left: 1; }
    """
    def __init__(self, host: Host):
        super().__init__(); self.host = host

    def compose(self) -> ComposeResult:
        with Vertical(id="command-box"):
            yield Label(f"[b]Remote command for {_esc(self.host.label)}[/b]")
            yield Static("This command will run remotely after connection. Production hosts require a second confirmation. Nothing runs from this dialog alone.")
            yield Input(placeholder="command to run on remote host", id="command-input")
            with Horizontal(id="command-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Prepare launch", id="submit", variant="primary")

    def action_cancel(self) -> None: self.dismiss(None)

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None: self.dismiss(None)

    @on(Button.Pressed, "#submit")
    def submit(self) -> None:
        command = self.query_one("#command-input", Input).value.strip()
        if command:
            self.dismiss(command)
        else:
            self.app.push_screen(MessageScreen("Command required", "Enter an explicit remote command, or cancel."))


class SettingsScreen(ModalScreen[dict[str, Any] | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]
    CSS = """
    SettingsScreen { align: center middle; background: #1a1b26 70%; }
    #settings-box { width: 62; max-width: 92%; height: auto; padding: 1 2; border: round #7aa2f7; background: #24283b; }
    .settings-row { height: 3; }
    .settings-label { width: 23; padding-top: 1; color: #9aa5ce; }
    #settings-actions { height: 3; align-horizontal: right; }
    #settings-actions Button { margin-left: 1; }
    """
    def __init__(self, settings: dict[str, Any]):
        super().__init__(); self.settings = settings

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-box"):
            yield Label("[b]Settings[/b]")
            with Horizontal(classes="settings-row"):
                yield Label("Accent color", classes="settings-label")
                yield Select([(x.title(), color) for x, color in (("Blue", "#7aa2f7"), ("Purple", "#bb9af7"), ("Green", "#9ece6a"), ("Cyan", "#7dcfff"), ("Orange", "#e0af68"), ("Pink", "#f7768e"))], value=self.settings.get("accent", "#7aa2f7"), id="setting-accent", allow_blank=False)
            with Horizontal(classes="settings-row"):
                yield Label("Row height", classes="settings-label")
                yield Select([("Compact (1)", 1), ("Comfortable (3)", 3)], value=int(self.settings.get("row_height", 1)), id="setting-row-height", allow_blank=False)
            with Horizontal(classes="settings-row"):
                yield Label("ASCII borders", classes="settings-label")
                yield Checkbox("Use plain ASCII borders", value=bool(self.settings.get("ascii", False)), id="setting-ascii")
            with Horizontal(id="settings-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Save settings", id="save", variant="primary")

    def action_cancel(self) -> None: self.dismiss(None)

    @on(Button.Pressed)
    def pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel": self.dismiss(None)
        elif event.button.id == "save":
            self.dismiss({"accent": self.query_one("#setting-accent", Select).value,
                          "row_height": self.query_one("#setting-row-height", Select).value,
                          "ascii": self.query_one("#setting-ascii", Checkbox).value})


class SortScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]
    CSS = """
    SortScreen { align: center middle; background: #1a1b26 70%; }
    #sort-box { width: 54; max-width: 90%; height: auto; padding: 1 2; border: round #7aa2f7; background: #24283b; }
    #sort-select { margin: 1 0; }
    #sort-actions { height: 3; align-horizontal: right; }
    #sort-actions Button { margin-left: 1; }
    """
    OPTIONS = [("Smart", "smart"), ("Name", "name"), ("User", "user"), ("Host", "host"), ("Port", "port"), ("Manual", "manual"), ("Recent", "recent")]
    def __init__(self, current: str):
        super().__init__(); self.current = current
    def compose(self) -> ComposeResult:
        with Vertical(id="sort-box"):
            yield Label("[b]Sort hosts[/b]")
            yield Select(self.OPTIONS, value=self.current, id="sort-select", allow_blank=False)
            with Horizontal(id="sort-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Apply", id="apply", variant="primary")
    def action_cancel(self) -> None: self.dismiss(None)

    @on(Button.Pressed)
    def pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "apply": self.dismiss(self.query_one("#sort-select", Select).value)
        elif event.button.id == "cancel": self.dismiss(None)


class SSHApp(App[LaunchRequest | None]):
    """Keyboard-first host picker. No SSH launch is performed by this class."""
    TITLE = "ssh-ls"
    CSS = """
    Screen { background: #1a1b26; color: #c0caf5; }
    #topline { height: 3; padding: 1; background: #24283b; }
    #brand { width: 17; color: #7aa2f7; text-style: bold; padding-top: 0; }
    #tabs { width: 1fr; height: 1; }
    #tabs Button { width: 1fr; min-width: 10; height: 1; border: none; padding: 0; background: #24283b; color: #9aa5ce; }
    #tabs Button:focus { border: none; background: #24283b; padding: 0; }
    #tabs Button.active { color: #7aa2f7; text-style: bold; border-bottom: none; }
    #tabs Button.active:focus { border: none; border-bottom: none; }
    #search { width: 28; height: 1; padding: 0 1; border: none; background: #1a1b26; }
    #main { height: 1fr; }
    #list-pane { width: 60%; min-width: 32; height: 1fr; border: round #414868; margin: 1 0 1 1; padding: 0 1; }
    #detail-pane { width: 40%; min-width: 30; height: 1fr; border: round #414868; margin: 1 1 1 0; padding: 1; }
    #list-caption { height: 2; color: #9aa5ce; padding-top: 1; }
    #host-scroll { height: 1fr; overflow-y: auto; }
    #host-list { height: auto; padding: 0 1; text-wrap: nowrap; text-overflow: ellipsis; }
    #details { height: 1fr; overflow-y: auto; }
    #status { height: 1; padding: 0 2; color: #e0af68; }
    #context { height: 1; padding: 0 2; background: #24283b; color: #9aa5ce; }
    .selected-row { background: #24283b; color: #c0caf5; text-style: bold; }
    .normal-row { color: #9aa5ce; }
    .host-line { height: 1; }
    .warning { color: #e0af68; }
    .danger { color: #f7768e; }
    .success { color: #9ece6a; }
    .muted { color: #9aa5ce; }
    Screen.narrow #list-pane { width: 1fr; min-width: 30; margin-right: 1; }
    Screen.narrow #detail-pane { display: none; }
    Screen.narrow #brand { width: 12; }
    Screen.narrow #search { width: 16; }
    Screen.narrow #tabs Button { min-width: 8; }
    Screen.tiny #brand { display: none; }
    Screen.tiny #search { width: 16; }
    Screen.tiny #tabs Button { min-width: 7; }
    Screen.ascii-borders #topline, Screen.ascii-borders #list-pane, Screen.ascii-borders #detail-pane,
    Screen.ascii-borders #confirm-box, Screen.ascii-borders #message-box, Screen.ascii-borders #form-box,
    Screen.ascii-borders #command-box, Screen.ascii-borders #settings-box, Screen.ascii-borders #sort-box { border: ascii #414868; }
    """
    BINDINGS = [Binding("ctrl+c", "quit", "Quit", priority=True)]
    TABS = ("All", "Recent", "Favorites", "History")
    ACCENTS = {"blue": "#7aa2f7", "purple": "#bb9af7", "green": "#9ece6a", "cyan": "#7dcfff", "orange": "#e0af68", "pink": "#f7768e"}

    def __init__(self, service: Any):
        super().__init__()
        self.service = service
        self.tab = "All"
        self.selected = 0
        self.search_text = ""
        self.result: LaunchRequest | None = None
        self._nav_focus = True
        self._last_narrow = False
        self._filtered: list[Host] = []
        self.status = "Ready"
        self._help_open = False
        self._move_mode = False
        self._ascii = False
        self.sort_mode = "manual"

    def compose(self) -> ComposeResult:
        with Horizontal(id="topline"):
            yield Static("ssh-ls", id="brand")
            with Horizontal(id="tabs"):
                for index, tab in enumerate(self.TABS):
                    yield Button(tab, id=f"tab-{index}", classes="active" if index == 0 else "")
            yield Input(placeholder="/ search hosts", id="search")
        with Horizontal(id="main"):
            with Vertical(id="list-pane"):
                yield Static("", id="list-caption")
                with VerticalScroll(id="host-scroll"):
                    yield FocusableStatic("", id="host-list")
            with Vertical(id="detail-pane"):
                yield Static("Select a host to see details.", id="details")
        yield Static("Ready", id="status")
        yield Static("←→ tabs j/k hosts Enter connect / search ? help q quit", id="context")

    def on_mount(self) -> None:
        self._refresh()
        self.query_one("#host-list", Static).focus()
        self._nav_focus = True
        self._apply_settings_style()
        self._set_responsive(self.size.width)

    def push_screen(self, screen: Screen | str, callback=None, wait_for_dismiss: bool = False, *, mode: str | None = None):
        if isinstance(screen, Screen) and bool(getattr(self.service, "settings", {}).get("ascii", False)):
            screen.add_class("ascii-borders")
        return super().push_screen(screen, callback, wait_for_dismiss, mode=mode)

    def _all_hosts(self) -> list[Host]:
        return [h for h in getattr(self.service, "hosts", []) if not getattr(h, "hidden", False)]

    def _refresh(self) -> None:
        if not self.is_mounted:
            return
        previous_id = self._filtered[self.selected].id if self._filtered and self.selected < len(self._filtered) else None
        hosts = self._all_hosts()
        if self.tab == "Recent":
            hosts = [h for h in hosts if getattr(h, "last_used", 0)]
            hosts.sort(key=lambda h: getattr(h, "last_used", 0), reverse=True)
        elif self.tab == "Favorites":
            hosts = [h for h in hosts if getattr(h, "favorite", False)]
        elif self.tab == "History":
            hosts = [h for h in hosts if getattr(h, "history", False)]
        if self.tab != "Recent":
            if self.sort_mode == "name": hosts.sort(key=lambda h: h.label.casefold())
            elif self.sort_mode == "user": hosts.sort(key=lambda h: h.user.casefold())
            elif self.sort_mode == "host": hosts.sort(key=lambda h: h.hostname.casefold())
            elif self.sort_mode == "port": hosts.sort(key=lambda h: (h.port, h.label.casefold()))
            elif self.sort_mode == "recent": hosts.sort(key=lambda h: getattr(h, "last_used", 0), reverse=True)
            elif self.sort_mode == "smart": hosts.sort(key=lambda h: (not h.favorite, -getattr(h, "last_used", 0), h.order, h.label.casefold()))
            else: hosts.sort(key=lambda h: (h.order, h.label.casefold()))
        if self.search_text:
            q = self.search_text.casefold()
            hosts = [h for h in hosts if q in " ".join(str(getattr(h, x, "") or "") for x in ("label", "hostname", "user", "alias", "jump")).casefold()]
        self._filtered = hosts
        if previous_id is not None and any(host.id == previous_id for host in hosts):
            self.selected = next(i for i, host in enumerate(hosts) if host.id == previous_id)
        else:
            self.selected = min(max(0, self.selected), max(0, len(hosts)-1))
        warnings = getattr(self.service, "warnings", []) or []
        warning_badge = f"  [#e0af68]{'?' if self._ascii else '⚠'} {len(warnings)} warnings[/#e0af68]" if warnings else ""
        self.query_one("#list-caption", Static).update(f"[b]{self.tab}[/b]  [#9aa5ce]{len(hosts)} host{'s' if len(hosts) != 1 else ''}[/#9aa5ce]{warning_badge}")
        rh = int(getattr(self.service, "settings", {}).get("row_height", 1) or 1)
        lines: list[str] = []
        for idx, host in enumerate(hosts):
            star = ("*" if self._ascii else "★") if getattr(host, "favorite", False) else " "
            prod = " [#f7768e]PROD[/#f7768e]" if getattr(host, "production", False) else ""
            source = _esc(_source_label(host))
            identity = f"[b]{_esc(host.label)}[/b]  [#9aa5ce]{_esc(host.destination)}:{host.port}[/#9aa5ce]  [#9aa5ce]({source})[/#9aa5ce]{prod}"
            if idx == self.selected:
                line = f"[#7aa2f7]{'>' if self._ascii else '›'}[/#7aa2f7] [bold #c0caf5]{star} {identity}[/]"
            else:
                line = f"[#9aa5ce] {star} {identity} [/#9aa5ce]"
            lines.extend([line] + ([""] * (rh - 1)))
        if not hosts:
            lines = ["[#9aa5ce]No hosts in this view.[/#9aa5ce]", "", "[#9aa5ce]Press a to add a host, i to reload.[/#9aa5ce]"]
        self.query_one("#host-list", Static).update("\n".join(lines))
        if hosts:
            try: self.query_one("#host-scroll", VerticalScroll).scroll_to(y=self.selected, animate=False)
            except Exception: pass
        self._update_details()
        self.query_one("#status", Static).update(_esc(self.status))
        accent_value = str(getattr(self.service, "settings", {}).get("accent", "#7aa2f7"))
        accent = self.ACCENTS.get(accent_value, accent_value)
        for i, tab in enumerate(self.TABS):
            button = self.query_one(f"#tab-{i}", Button)
            button.set_classes("active" if tab == self.tab else "")
            button.styles.color = accent if tab == self.tab else "#9aa5ce"
            button.styles.border_bottom = ("none", "transparent")

    def _update_details(self) -> None:
        details = self.query_one("#details", Static)
        if not self._filtered:
            details.update("[b]No host selected[/b]\n\nAdd a host or change the current view.")
            return
        h = self._filtered[self.selected]
        # These are declared model values, not claims about ssh_config resolution.
        port_value = f"{h.port}" if getattr(h, "port_explicit", True) else f"{h.port} (SSH default / estimated)"
        declared = [f"Label: {_esc(h.label)}", f"Destination: {_esc(h.destination)}", f"Hostname: {_esc(h.hostname)}", f"Port: {port_value}", f"User: {_esc(h.user or '(default)')}"]
        declared.append("Identity files: " + (_esc(", ".join(h.identities)) if h.identities else "(SSH default)"))
        declared.append("Jump host: " + (_esc(h.jump) if h.jump else "(none declared)"))
        declared.append("Config: " + (_esc(h.config_path) if h.config_path else "(not declared)"))
        declared.append("Extra SSH options: " + (_esc(" ".join(shlex.quote(str(x)) for x in h.extra_args)) if h.extra_args else "(none)"))
        declared.append(f"Production: {'yes — confirmation required' if h.production else 'no'}")
        declared.append(f"Sources: {_esc(', '.join(h.sources) or '(unknown)')}")
        declared.append(f"Favorite: {'yes' if h.favorite else 'no'}  Uses: {h.uses}")
        try:
            argv = self.service.argv(h, command=None)
            preview = " ".join(shlex.quote(str(x)) for x in argv)
        except Exception as exc:
            preview = f"Unavailable: {exc}"
        details.update("[b]Declared / estimated[/b] [#9aa5ce](not resolved config)[/#9aa5ce]\n" + "\n".join(declared) + "\n\n[b]SSH argv preview[/b]\n[#9aa5ce]" + _esc(preview) + "[/#9aa5ce]\n\n[#9aa5ce]Effective SSH config is never queried until you confirm with v.[/#9aa5ce]")

    def _apply_settings_style(self) -> None:
        settings = getattr(self.service, "settings", {}) or {}
        self._ascii = bool(settings.get("ascii", False))
        accent_value = str(settings.get("accent", "#7aa2f7"))
        accent = self.ACCENTS.get(accent_value, accent_value)
        # Keep the semantic Tokyo Night palette; only the accent is configurable.
        self.query_one("#brand", Static).styles.color = accent
        self.screen.add_class("ascii-borders" if settings.get("ascii", False) else "unicode-borders")
        if settings.get("ascii", False): self.screen.remove_class("unicode-borders")
        else: self.screen.remove_class("ascii-borders")
        for i, tab in enumerate(self.TABS):
            b = self.query_one(f"#tab-{i}", Button)
            b.styles.color = accent if tab == self.tab else "#9aa5ce"
            b.styles.border_bottom = ("none", "transparent")

    def _selected_host(self) -> Host | None:
        return self._filtered[self.selected] if self._filtered else None

    def _set_status(self, value: str) -> None:
        self.status = value
        if self.is_mounted:
            self.query_one("#status", Static).update(_esc(value))

    def _prompt(self, title: str, message: str, callback) -> None:
        self.push_screen(ConfirmScreen(title, message), callback)

    def action_quit(self) -> None:
        self.exit(self.result)

    def on_key(self, event) -> None:
        # Modal screens own their key events (including Escape); never let app-level
        # navigation leak into an editable form or confirmation dialog.
        if len(self.screen_stack) > 1:
            return
        focused = self.focused
        key = event.character or ""
        if isinstance(focused, Input) and focused.id == "search" and event.key == "enter":
            self._launch(); event.stop(); event.prevent_default(); return
        if isinstance(focused, (Input, TextArea, Checkbox, Select, Button)):
            if event.key == "escape":
                self.query_one("#host-list", Static).focus()
                self._nav_focus = True
                event.stop(); event.prevent_default()
            return
        handled = True
        if event.key == "escape":
            if self._move_mode:
                self._move_mode = False
                self._set_status("Manual move finished")
            self.query_one("#host-list", Static).focus(); self._nav_focus = True
        elif key in {"q", "Q"}: self.action_quit()
        elif key == "/":
            search = self.query_one("#search", Input); search.focus(); search.value = ""; self.search_text = ""; self._nav_focus = False
        elif event.key in {"tab", "shift+tab"}:
            self._cycle_tab(-1 if event.key == "shift+tab" else 1)
        elif event.key in {"left", "right"}:
            self._cycle_tab(-1 if event.key == "left" else 1)
        elif key in {"j", "J"} or event.key == "down": self._move_selection(1)
        elif key in {"k", "K"} or event.key == "up": self._move_selection(-1)
        elif key in {"a", "A"}: self._add_host()
        elif key in {"e", "E"}: self._edit_host()
        elif key in {"f", "F", " "}: self._toggle_favorite()
        elif key in {"x", "X"} or event.key in {"delete", "backspace"}: self._delete_host()
        elif key in {"c", "C"}: self._duplicate_host()
        elif key in {"m", "M"}:
            self._move_mode = True
            self.sort_mode = "manual"
            self._refresh()
            self._set_status("Manual move mode: j/k or ↑/↓ move selected host; Esc finishes")
        elif key in {"s", "S"}: self._sort_menu()
        elif key in {"o", "O"}: self._settings()
        elif key in {"i", "I"}: self._reload()
        elif key in {"r", "R"}: self._remote_command()
        elif key in {"v", "V"}: self._effective_config()
        elif key in {"g", "G"}: self._diagnose()
        elif key == "?": self._help()
        elif key in {"d", "D"}: self._show_details()
        elif key in {"u", "U"}: self._reset_overrides()
        elif key in {"h", "H"}: self._restore_hidden()
        elif event.key == "enter": self._launch()
        else: handled = False
        if handled:
            event.stop(); event.prevent_default()

    def _move_selection(self, delta: int) -> None:
        if self._filtered:
            if self._move_mode:
                self._move_host(delta)
            else:
                self.selected = (self.selected + delta) % len(self._filtered)
            self._refresh()

    def _cycle_tab(self, delta: int) -> None:
        self.tab = self.TABS[(self.TABS.index(self.tab) + delta) % len(self.TABS)]
        self.selected = 0
        self._refresh()

    @on(Button.Pressed, "#tab-0, #tab-1, #tab-2, #tab-3")
    def tab_pressed(self, event: Button.Pressed) -> None:
        self.tab = self.TABS[int(event.button.id.split("-")[-1])]
        self.selected = 0; self._refresh()
        self.query_one("#host-list", Static).focus()

    @on(Input.Changed, "#search")
    def search_changed(self, event: Input.Changed) -> None:
        self.search_text = event.value
        self.selected = 0
        self._refresh()

    def _add_host(self) -> None:
        self.push_screen(HostForm(), self._form_done)

    def _edit_host(self) -> None:
        h = self._selected_host()
        if h: self.push_screen(HostForm(h), self._form_done)

    def _form_done(self, data: dict[str, Any] | None) -> None:
        if data is None: return
        try:
            if "id" in data:
                host = next(h for h in self.service.hosts if h.id == data["id"])
                candidate = copy.deepcopy(host)
                for field in ("label", "hostname", "user", "port", "jump", "identities", "extra_args", "production"):
                    setattr(candidate, field, data[field])
            else:
                candidate = Host(id="custom:" + uuid.uuid4().hex, label=data["label"], hostname=data["hostname"],
                                 user=data["user"], port=data["port"], jump=data["jump"], identities=data["identities"],
                                 extra_args=data["extra_args"], production=data["production"], custom=True,
                                 sources=["custom"], order=max((h.order for h in self.service.hosts), default=-1) + 1)
            self.service.save(candidate)
            self._set_status("Host saved")
            self._refresh()
        except Exception as exc: self.push_screen(MessageScreen("Could not save host", _esc(exc)))

    def _toggle_favorite(self) -> None:
        h = self._selected_host()
        if not h: return
        try:
            candidate = copy.deepcopy(h)
            candidate.favorite = not h.favorite
            changed = self.service.save(candidate)
            self._set_status("Added to favorites" if changed.favorite else "Removed from favorites")
            self._refresh()
        except Exception as exc: self.push_screen(MessageScreen("Favorite update failed", _esc(exc)))

    def _delete_host(self) -> None:
        h = self._selected_host()
        if not h: return
        self._prompt("Delete host", f"Delete/hide [b]{_esc(h.label)}[/b]? This only removes the saved custom entry or hides its source; it does not alter SSH config.", lambda ok: self._delete_confirmed(h, ok))

    def _delete_confirmed(self, host: Host, ok: bool) -> None:
        if ok:
            try: self.service.delete(host); self._set_status(f"Deleted {host.label}"); self._refresh()
            except Exception as exc: self.push_screen(MessageScreen("Delete failed", _esc(exc)))

    def _duplicate_host(self) -> None:
        h = self._selected_host()
        if h:
            try:
                self.service.duplicate(h); self._set_status(f"Duplicated {h.label}"); self._refresh()
            except Exception as exc: self.push_screen(MessageScreen("Duplicate failed", _esc(exc)))

    def _move_host(self, delta: int) -> None:
        h = self._selected_host()
        if not h: return
        try:
            self.service.move(h, delta); self._refresh(); self._set_status("Manual order updated")
        except Exception as exc: self.push_screen(MessageScreen("Reorder failed", _esc(exc)))

    def _sort_menu(self) -> None:
        self.push_screen(SortScreen(self.sort_mode), self._sort_done)

    def _sort_done(self, mode: str | None) -> None:
        if mode:
            self.sort_mode = str(mode)
            self.selected = 0
            self._refresh()
            self._set_status(f"Sort: {self.sort_mode}")

    def _settings(self) -> None:
        settings = dict(getattr(self.service, "settings", {}) or {})
        self.push_screen(SettingsScreen(settings), self._settings_done)

    def _settings_done(self, settings: dict[str, Any] | None) -> None:
        if settings is None: return
        try:
            self.service.save_settings(settings); self._apply_settings_style(); self._refresh(); self._set_status("Settings saved")
        except Exception as exc: self.push_screen(MessageScreen("Settings failed", _esc(exc)))

    def _reload(self) -> None:
        try:
            self.service.reload(); self._refresh(); self._set_status("Host sources reloaded")
        except Exception as exc: self.push_screen(MessageScreen("Reload failed", _esc(exc)))

    def _remote_command(self) -> None:
        h = self._selected_host()
        if h: self.push_screen(CommandScreen(h), lambda command: self._command_done(h, command))

    def _command_done(self, host: Host, command: str | None) -> None:
        if command:
            self._prepare_launch(host, command)

    def _launch(self) -> None:
        h = self._selected_host()
        if h: self._prepare_launch(h, None)

    def _prepare_launch(self, host: Host, command: str | None) -> None:
        def finish(approved: bool) -> None:
            if approved:
                self.result = LaunchRequest(host, command)
                self.exit(self.result)
        if host.production:
            suffix = f"\n\nRemote command: {_esc(command)}" if command else ""
            self.push_screen(ConfirmScreen("Production connection", f"[#f7768e]Production host:[/#f7768e] {_esc(host.label)} ({_esc(host.destination)}). An SSH command will be handed to the launcher; this UI does not run it directly.{suffix}", "Connect", dangerous=True), finish)
        else:
            finish(True)

    def _effective_config(self) -> None:
        h = self._selected_host()
        if not h: return
        message = (f"Inspect effective SSH configuration for [b]{_esc(h.destination)}[/b]?\n\n"
                   "This runs the local command `ssh -G` using this host's declared connection parameters. SSH config may contain Match exec directives; those can execute local commands. Continue only if you trust the applicable SSH configuration.")
        self.push_screen(ConfirmScreen("Inspect effective SSH config", message, "Run ssh -G", dangerous=True), lambda ok: self._effective_confirmed(h, ok))

    def _effective_confirmed(self, host: Host, ok: bool) -> None:
        if not ok: return
        try: output = self.service.effective(host)
        except Exception as exc: output = f"Error: {exc}"
        self.push_screen(MessageScreen(f"Effective SSH config: {host.label}", _esc(output)))

    def _diagnose(self) -> None:
        h = self._selected_host()
        try: result = self.service.diagnose(h)
        except Exception as exc: result = f"Error: {exc}"
        self.push_screen(MessageScreen("Local diagnostics", _esc(result)))

    def _reset_overrides(self) -> None:
        host = self._selected_host()
        if not host: return
        self.push_screen(ConfirmScreen("Reset host overrides", f"Restore discovered SSH fields for {_esc(host.label)}?", "Reset"), lambda ok: self._reset_confirmed(host, ok))

    def _reset_confirmed(self, host: Host, ok: bool) -> None:
        if ok:
            try:
                self.service.reset_overrides(copy.deepcopy(host)); self._refresh(); self._set_status("Overrides reset")
            except Exception as exc: self.push_screen(MessageScreen("Reset failed", _esc(exc)))

    def _restore_hidden(self) -> None:
        restore = getattr(self.service, "restore_hidden", None)
        if restore is None:
            self._set_status("No hidden-source restore action")
            return
        self.push_screen(ConfirmScreen("Restore hidden sources", "Unhide all previously hidden discovered hosts?", "Restore"), lambda ok: self._restore_confirmed(restore, ok))

    def _restore_confirmed(self, restore, ok: bool) -> None:
        if ok:
            try: restore(); self._refresh(); self._set_status("Hidden sources restored")
            except Exception as exc: self.push_screen(MessageScreen("Restore failed", _esc(exc)))

    def _show_details(self) -> None:
        h = self._selected_host()
        if h:
            port_value = str(h.port) if getattr(h, "port_explicit", True) else f"{h.port} (SSH default / estimated)"
            body = (f"Declared hostname: {_esc(h.hostname)}\nUser: {_esc(h.user or '(default)')}\nPort: {port_value}\n"
                    f"Identity files: {_esc(', '.join(h.identities) or '(SSH default)')}\nJump host: {_esc(h.jump or '(none)')}\n"
                    f"Production: {'yes — confirmation required' if h.production else 'no'}\nSources: {_esc(', '.join(h.sources))}")
            self.push_screen(MessageScreen(f"Host details: {h.label}", body))

    def _help(self) -> None:
        text = "[b]Navigation[/b]\nTab / Shift+Tab / ← / →  switch All, Recent, Favorites, History\nj / k  select host   •   /  search   •   Esc  return to navigation\nEnter  prepare SSH connection   •   r  enter explicit remote command\n\n[b]Host management[/b]\na add   e edit   c duplicate   x delete/hide (confirmation)\nSpace favorite   m reorder mode (j/k or ↑/↓, Esc finish)   i reload sources\ns sort   o settings   g local diagnostics\nv inspect effective SSH config (confirmation; Match exec can run local commands)\nd details on narrow screens   U reset overrides   H restore hidden   ? help   q quit\n\nShortcuts are inactive while editing text. Production launches always require confirmation."
        self.push_screen(MessageScreen("ssh-ls help", text))

    def _set_responsive(self, width: int) -> None:
        self._last_narrow = width < 100
        if self._last_narrow:
            self.screen.add_class("narrow")
            self.screen.remove_class("wide")
        else:
            self.screen.add_class("wide")
            self.screen.remove_class("narrow")
        if width < 70:
            self.screen.add_class("tiny")
        else:
            self.screen.remove_class("tiny")
        if self.is_mounted:
            self.query_one("#tab-2", Button).label = "Favs" if width < 70 else "Favorites"
            if width < 70:
                footer = "←→ tabs j/k hosts Enter connect / search ? help q quit"
            elif width < 100:
                footer = "←/→ tabs j/k hosts Enter connect / search Space favorite ? help q quit"
            else:
                footer = "Tab/←→ views j/k select / search Enter connect a add e edit Space favorite r command ? help q quit"
            self.query_one("#context", Static).update(footer)

    def on_resize(self, event) -> None:
        # At narrow widths details are deliberately not squeezed; d opens a readable modal.
        self._set_responsive(event.size.width)
