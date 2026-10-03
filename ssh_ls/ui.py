"""Textual interface for ssh-ls.

The interface intentionally keeps navigation separate from editable fields: global
single-key shortcuts are ignored whenever an Input/TextArea has focus.
"""
from __future__ import annotations

import copy
import shlex
import uuid
from pathlib import Path
from rich.text import Text
from typing import Any

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, Vertical, VerticalScroll
from textual.events import DescendantFocus
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widgets import Button, Checkbox, Input, Label, Select, Static, TextArea

from .models import Host, LaunchRequest
from .store import START_TABS
from .themes import DEFAULT_THEME, THEMES, get_palette


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


def compact_sources(sources: list[str], *, ascii: bool = False) -> str:
    """Group line numbers per source file without losing gaps or provenance."""
    groups: dict[tuple[str, str], set[int]] = {}
    labels: list[str | tuple[str, str]] = []
    for source in sources:
        kind, separator, rest = source.partition(":")
        path, colon, number = rest.rpartition(":")
        if separator and colon and kind in {"config", "history"} and number.isdecimal():
            key = (kind, path)
            if key not in groups:
                groups[key] = set()
                labels.append(key)
            groups[key].add(int(number))
        elif source not in labels:
            labels.append(source)
    results = []
    home = str(Path.home())
    dash = "-" if ascii else "–"
    for label in labels:
        if isinstance(label, str):
            results.append(label)
            continue
        kind, path = label
        if path == home or path.startswith(home + "/"):
            path = "~" + path[len(home):]
        numbers = sorted(groups[label])
        ranges = []
        start = end = numbers[0]
        for number in numbers[1:]:
            if number == end + 1:
                end = number
            else:
                ranges.append(str(start) if start == end else f"{start}{dash}{end}")
                start = end = number
        ranges.append(str(start) if start == end else f"{start}{dash}{end}")
        results.append(f"{kind}:{path}:{', '.join(ranges)}")
    return "\n".join(results) or "(unknown)"


class FocusableStatic(Static):
    can_focus = True


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]
    CSS = """
    ConfirmScreen { align: center middle; background: $ssh-bg 70%; }
    #confirm-box { width: 70; max-width: 90%; height: auto; max-height: 80%; padding: 1 2; border: round $ssh-accent; background: $ssh-surface; }
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
    MessageScreen { align: center middle; background: $ssh-bg 70%; }
    #message-box { width: 78; max-width: 92%; height: auto; max-height: 85%; padding: 1 2; border: round $ssh-accent; background: $ssh-surface; }
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
    HostForm { align: center middle; background: $ssh-bg 70%; }
    #form-box { width: 90; max-width: 96%; height: 90%; max-height: 95%; padding: 1 2; border: round $ssh-accent; background: $ssh-surface; }
    #form-fields { height: 1fr; overflow-y: auto; }
    .form-row { height: 3; }
    .form-label { width: 20; padding-top: 1; color: $ssh-muted; }
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
    CommandScreen { align: center middle; background: $ssh-bg 70%; }
    #command-box { width: 78; max-width: 92%; height: auto; padding: 1 2; border: round $ssh-accent; background: $ssh-surface; }
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


class SettingsScreen(Screen[dict[str, Any] | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]
    CSS = """
    SettingsScreen { align: center middle; background: $ssh-bg; color: $ssh-fg; }
    #settings-box { width: 104; max-width: 98%; height: 100%; max-height: 100%; padding: 1 2; border: round $ssh-border; background: $ssh-bg; }
    #settings-title { height: 1; color: $ssh-accent; text-style: bold; }
    #settings-description { height: 1; color: $ssh-muted; text-wrap: nowrap; text-overflow: ellipsis; }
    #settings-fields { height: 1fr; }
    #theme-preview { height: 2; padding: 0 1; margin-bottom: 0; background: $ssh-surface; }
    .settings-row { height: 3; }
    .settings-label { width: 20; padding-top: 1; color: $ssh-muted; }
    SettingsScreen.compact .settings-label { width: 14; }
    SettingsScreen.tiny .settings-label { width: 12; text-wrap: nowrap; text-overflow: ellipsis; }
    SettingsScreen Select { width: 1fr; min-width: 0; }
    SettingsScreen SelectCurrent { text-wrap: nowrap; text-overflow: ellipsis; }
    #settings-tabs { height: 3; margin: 0 0 1 0; }
    #settings-tabs Button { width: 16; margin-right: 1; }
    #settings-tabs Button.active { color: $ssh-accent; text-style: bold; border-bottom: tall $ssh-accent; }
    #theme-grid { grid-size: 3; grid-columns: 1fr 1fr 1fr; grid-gutter: 1 1; height: auto; padding: 1; }
    #theme-grid Button { height: 6; min-width: 0; padding: 0 1; content-align: left middle; text-align: left; background: $ssh-surface; color: $ssh-fg; border: round $ssh-border; }
    #theme-grid Button:focus { border: tall $ssh-accent; }
    #theme-grid Button.selected-theme { border: round $ssh-accent; text-style: bold; }
    SettingsScreen.compact #theme-grid { grid-size: 2; grid-columns: 1fr 1fr; }
    SettingsScreen.tiny #theme-grid { grid-size: 1; grid-columns: 1fr; }
    #general-pane, #themes-pane { height: auto; }
    #themes-pane { display: none; }
    SettingsScreen.show-themes #general-pane { display: none; }
    SettingsScreen.show-themes #themes-pane { display: block; }
    #settings-actions { height: 3; align-horizontal: right; }
    #settings-actions Button { margin-left: 1; }
    #settings-hint { height: 1; color: $ssh-muted; text-wrap: nowrap; text-overflow: ellipsis; }
    SettingsScreen SelectCurrent { background: $ssh-surface; color: $ssh-fg; border: tall $ssh-border; }
    SettingsScreen SelectCurrent Static#label { height: 1; text-wrap: nowrap; text-overflow: ellipsis; }
    SettingsScreen SelectCurrent:focus { border: tall $ssh-accent; }
    SettingsScreen Checkbox { background: $ssh-surface; color: $ssh-fg; border: tall $ssh-border; }
    SettingsScreen Button { background: $ssh-surface; color: $ssh-fg; border: tall $ssh-border; }
    SettingsScreen Button.-primary { background: $ssh-accent; color: $ssh-bg; border: tall $ssh-accent; }
    """
    def __init__(self, settings: dict[str, Any]):
        super().__init__(); self.settings = settings
        self._selected_theme = settings.get("theme", DEFAULT_THEME)
        self.active_pane = "General"

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-box"):
            yield Static("Settings", id="settings-title")
            yield Static("Choose how ssh-ls opens and looks.", id="settings-description")
            with Horizontal(id="settings-tabs"):
                yield Button("General", id="settings-general", classes="active")
                yield Button("Themes", id="settings-themes")
            with VerticalScroll(id="settings-fields"):
                with Vertical(id="general-pane"):
                    yield Static("Theme colors", classes="settings-label")
                    yield Static("", id="theme-preview")
                    with Horizontal(classes="settings-row"):
                        yield Label("Start page", classes="settings-label")
                        yield Select([(x, x) for x in ("Recent", "Favorites", "All")], value=self.settings.get("start_tab", "Recent"), id="setting-start-tab", allow_blank=False)
                    with Horizontal(classes="settings-row"):
                        yield Label("Accent color", classes="settings-label")
                        options = [("Theme default", "auto"), ("Blue", "#7aa2f7"), ("Purple", "#bb9af7"), ("Green", "#9ece6a"), ("Cyan", "#7dcfff"), ("Orange", "#e0af68"), ("Pink", "#f7768e")]
                        accent = self.settings.get("accent", "auto")
                        if accent not in [value for _, value in options]:
                            options.append(("Custom " + accent, accent))
                        yield Select(options, value=accent, id="setting-accent", allow_blank=False)
                    with Horizontal(classes="settings-row"):
                        yield Label("Row spacing", classes="settings-label")
                        yield Select([("Compact", 1), ("Comfortable", 3)], value=int(self.settings.get("row_height", 1)), id="setting-row-height", allow_blank=False)
                    with Horizontal(classes="settings-row"):
                        yield Label("ASCII display", classes="settings-label")
                        yield Checkbox("Plain borders", value=bool(self.settings.get("ascii", False)), id="setting-ascii")
                with Vertical(id="themes-pane"):
                    yield Static("Select a palette to preview it across ssh-ls. Save to keep it.", id="themes-description")
                    with Grid(id="theme-grid"):
                        ascii_display = bool(self.settings.get("ascii", False))
                        for name, palette in THEMES.items():
                            card = Text()
                            card.append(palette["label"] + "\n", style="bold " + palette["fg"])
                            card.append(("> " if ascii_display else "› ") + ("alice@tokyo" if name == "tokyo-night" else "deploy@" + name) + "\n", style=palette["accent"])
                            card.append(("* Ready  " if ascii_display else "● Ready  "), style=palette["success"])
                            card.append("! Warning", style=palette["warning"])
                            button = Button(card, id=f"theme-{name}", classes="selected-theme" if name == self._selected_theme else "")
                            button.styles.background = palette["surface"]
                            button.styles.color = palette["fg"]
                            button.styles.border = ("round", palette["accent"] if name == self._selected_theme else palette["border"])
                            yield button
            with Horizontal(id="settings-actions"):
                yield Button("Back", id="cancel")
                yield Button("Save", id="save", variant="primary")
            yield Static("Esc discards preview   ·   Save keeps your theme", id="settings-hint")

    def on_mount(self) -> None:
        self._preview_theme()
        self._set_responsive(self.size.width)

    def _set_responsive(self, width: int) -> None:
        self.set_class(width < 78, "compact")
        self.set_class(width < 52, "tiny")

    def on_resize(self, event) -> None:
        self._set_responsive(event.size.width)

    def on_key(self, event) -> None:
        focused = self.app.focused
        if not isinstance(focused, Button) or not focused.id or not focused.id.startswith("theme-"):
            return
        names = list(THEMES)
        index = names.index(focused.id.removeprefix("theme-"))
        columns = 1 if self.size.width < 52 else 2 if self.size.width < 78 else 3
        delta = {"left": -1, "right": 1, "up": -columns, "down": columns}.get(event.key)
        if delta is not None:
            next_index = max(0, min(len(names) - 1, index + delta))
            self.query_one(f"#theme-{names[next_index]}", Button).focus()
            event.stop()
            event.prevent_default()

    def on_descendant_focus(self, event: DescendantFocus) -> None:
        if isinstance(event.widget, Button) and event.widget.id and event.widget.id.startswith("theme-"):
            self.query_one("#settings-fields", VerticalScroll).scroll_to_widget(event.widget, animate=False)

    @on(Button.Pressed, "#settings-general, #settings-themes")
    def pane_pressed(self, event: Button.Pressed) -> None:
        self.active_pane = "Themes" if event.button.id == "settings-themes" else "General"
        self.set_class(self.active_pane == "Themes", "show-themes")
        self.query_one("#settings-general", Button).set_class(self.active_pane == "General", "active")
        self.query_one("#settings-themes", Button).set_class(self.active_pane == "Themes", "active")

    @on(Button.Pressed, "#theme-grid Button")
    def theme_card_pressed(self, event: Button.Pressed) -> None:
        self._select_theme(event.button.id.removeprefix("theme-"))

    def _select_theme(self, name: str) -> None:
        if name not in THEMES:
            return
        changed_theme = name != self._selected_theme
        self._selected_theme = name
        for theme_name in THEMES:
            button = self.query_one(f"#theme-{theme_name}", Button)
            button.set_class(name == theme_name, "selected-theme")
            palette = THEMES[theme_name]
            button.styles.background = palette["surface"]
            button.styles.color = palette["fg"]
            button.styles.border = ("round", palette["accent"] if name == theme_name else palette["border"])
        if changed_theme:
            self.query_one("#setting-accent", Select).value = "auto"
        self._preview_theme()

    @on(Select.Changed, "#setting-accent")
    def preview_changed(self, event: Select.Changed) -> None:
        if not self.is_mounted or event.value is Select.BLANK:
            return
        self._preview_theme()

    def _preview_theme(self) -> None:
        settings = {"theme": self._selected_theme,
                    "accent": self.query_one("#setting-accent", Select).value}
        colors = get_palette(settings)
        self.app._use_theme(settings)
        preview = Text(colors["label"] + "  ", style="bold " + colors["fg"])
        for role in ("accent", "purple", "success", "warning", "danger"):
            preview.append("██ ", style=colors[role])
        ascii_display = self.settings.get("ascii", False)
        preview.append("\n" + ("+ Ready  " if ascii_display else "✓ Ready  "), style=colors["success"])
        preview.append("! Warning  ", style=colors["warning"])
        preview.append("x Failed" if ascii_display else "× Failed", style=colors["danger"])
        self.query_one("#theme-preview", Static).update(preview)

    def action_cancel(self) -> None: self.dismiss(None)

    @on(Button.Pressed)
    def pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel": self.dismiss(None)
        elif event.button.id == "save":
            self.dismiss({"theme": self._selected_theme,
                          "start_tab": self.query_one("#setting-start-tab", Select).value,
                          "accent": self.query_one("#setting-accent", Select).value,
                          "row_height": self.query_one("#setting-row-height", Select).value,
                          "ascii": self.query_one("#setting-ascii", Checkbox).value})


class SortScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]
    CSS = """
    SortScreen { align: center middle; background: $ssh-bg 70%; }
    #sort-box { width: 54; max-width: 90%; height: auto; padding: 1 2; border: round $ssh-accent; background: $ssh-surface; }
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
    Screen { background: $ssh-bg; color: $ssh-fg; }
    #topline { height: 3; padding: 1; background: $ssh-surface; }
    #update-banner { height: 1; display: none; padding: 0 1; color: $ssh-warning; background: $ssh-surface; text-wrap: nowrap; text-overflow: ellipsis; }
    #brand { width: 17; color: $ssh-accent; text-style: bold; padding-top: 0; }
    #tabs { width: 1fr; height: 1; }
    #tabs Button { width: 1fr; min-width: 10; height: 1; border: none; padding: 0; background: $ssh-surface; color: $ssh-muted; }
    #tabs Button:focus { border: none; background: $ssh-surface; padding: 0; }
    #tabs Button.active { color: $ssh-accent; text-style: bold; border-bottom: none; }
    #tabs Button.active:focus { border: none; border-bottom: none; }
    #search { width: 28; height: 1; padding: 0 1; border: none; background: $ssh-bg; }
    #open-settings { width: 12; min-width: 10; height: 1; text-wrap: nowrap; text-overflow: ellipsis; border: none; padding: 0 1; color: $ssh-muted; background: $ssh-surface; }
    #open-settings:focus { border: none; padding: 0 1; color: $ssh-accent; }
    Screen.tiny #open-settings { width: 10; min-width: 10; padding: 0; }
    #main { height: 1fr; }
    #list-pane { width: 60%; min-width: 32; height: 1fr; border: round $ssh-border; margin: 1 0 1 1; padding: 0 1; }
    #detail-pane { width: 40%; min-width: 30; height: 1fr; border: round $ssh-border; margin: 1 1 1 0; padding: 1; }
    #list-caption { height: 3; color: $ssh-muted; padding-top: 1; }
    #host-scroll { height: 1fr; overflow-y: auto; }
    #host-list { height: auto; padding: 0 1; text-wrap: nowrap; text-overflow: ellipsis; }
    #details { height: 1fr; overflow-y: auto; }
    #status { height: 1; padding: 0 2; color: $ssh-warning; }
    #context { height: 3; padding: 1 2; background: $ssh-surface; color: $ssh-muted; }
    #footer-primary { width: 1fr; height: 1; text-wrap: nowrap; text-overflow: ellipsis; }
    #footer-secondary { width: auto; height: 1; margin-left: 1; text-wrap: nowrap; text-overflow: ellipsis; }
    .selected-row { background: $ssh-surface; color: $ssh-fg; text-style: bold; }
    .normal-row { color: $ssh-muted; }
    .host-line { height: 1; }
    .warning { color: $ssh-warning; }
    .danger { color: $ssh-danger; }
    .success { color: $ssh-success; }
    .muted { color: $ssh-muted; }
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
    Screen.ascii-borders #command-box, Screen.ascii-borders #settings-box, Screen.ascii-borders #sort-box { border: ascii $ssh-border; }
    """
    BINDINGS = [Binding("ctrl+c", "quit", "Quit", priority=True)]
    TABS = START_TABS

    def __init__(self, service: Any, *, check_updates: bool = False):
        super().__init__()
        self.service = service
        self.check_updates = check_updates
        self.available_update = None
        self.tab = getattr(service, "settings", {}).get("start_tab", "Recent")
        if self.tab not in self.TABS:
            self.tab = "Recent"
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
        self._use_theme(getattr(service, "settings", {}) or {})

    def compose(self) -> ComposeResult:
        with Horizontal(id="topline"):
            yield Static("ssh-ls", id="brand")
            with Horizontal(id="tabs"):
                for index, tab in enumerate(self.TABS):
                    yield Button(tab, id=f"tab-{index}", classes="active" if index == 0 else "")
            yield Input(placeholder="/ search hosts", id="search")
            yield Button("Settings", id="open-settings", tooltip="Preferences (o)")
        yield Static("", id="update-banner")
        with Horizontal(id="main"):
            with Vertical(id="list-pane"):
                yield Static("", id="list-caption")
                with VerticalScroll(id="host-scroll"):
                    yield FocusableStatic("", id="host-list")
            with Vertical(id="detail-pane"):
                yield Static("Select a host to see details.", id="details")
        yield Static("Ready", id="status")
        with Horizontal(id="context"):
            yield Static("", id="footer-primary")
            yield Static("", id="footer-secondary")

    def on_mount(self) -> None:
        self._refresh()
        self.query_one("#host-list", Static).focus()
        self._nav_focus = True
        self._apply_settings_style()
        self._set_responsive(self.size.width)
        if self.check_updates:
            self.run_worker(self._check_for_updates, thread=True, exclusive=True, name="release-check")

    def _check_for_updates(self) -> None:
        """Check for a release off the UI thread; network errors never affect startup."""
        try:
            from . import __version__
            from .lifecycle import available_update
            release = available_update(current_version=__version__, timeout=2.0)
            if release is not None:
                self.call_from_thread(self._show_update, release.version)
        except Exception:
            # Update discovery is advisory and must never block host browsing.
            return

    def _show_update(self, version: str) -> None:
        self.available_update = version
        if self.is_mounted:
            banner = self.query_one("#update-banner", Static)
            banner.update(f"Update available: v{version} · ssh-ls update")
            banner.display = True

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
            hosts = [h for h in hosts if getattr(h, "last_used", 0) or h.history]
            hosts.sort(key=lambda h: getattr(h, "last_used", 0), reverse=True)
        elif self.tab == "Favorites":
            hosts = [h for h in hosts if getattr(h, "favorite", False)]
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
        colors = self._palette
        warnings = getattr(self.service, "warnings", []) or []
        warning_badge = f"  [{colors['warning']}]{'?' if self._ascii else '⚠'} {len(warnings)} warnings[/]" if warnings else ""
        self.query_one("#list-caption", Static).update(f"[b]{self.tab}[/b]  [{colors['muted']}]{len(hosts)} host{'s' if len(hosts) != 1 else ''}[/]{warning_badge}")
        description = {"All": "Configured, historical and custom hosts", "Recent": "Recently used across sources · newest first", "Favorites": "Your starred hosts"}[self.tab]
        caption = self.query_one("#list-caption", Static)
        caption.update(str(caption.content) + f"\n[{colors['muted']}]{description}[/]")
        rh = int(getattr(self.service, "settings", {}).get("row_height", 1) or 1)
        lines: list[Text] = []
        name_width = min(24, max((Text(host.label).cell_len for host in hosts), default=8))
        self._ascii = bool(getattr(self.service, "settings", {}).get("ascii", False))
        accent = self._palette["accent"]
        for idx, host in enumerate(hosts):
            star = ("*" if self._ascii else "★") if getattr(host, "favorite", False) else " "
            cursor = (">" if self._ascii else "›") if idx == self.selected else " "
            row = Text()
            row.append(cursor + " ", style=accent)
            row.append(star + " ", style=colors["warning"] if host.favorite else colors["muted"])
            name = Text(host.label, style="bold " + colors["fg"] if idx == self.selected else colors["fg"])
            name.truncate(name_width, overflow="ellipsis", pad=True)
            row.append_text(name)
            row.append("  " + host.destination + f":{host.port}", style=colors["muted"])
            row.append("  (" + _source_label(host) + ")", style=colors["muted"])
            if host.production:
                row.append("  PROD", style="bold " + colors["danger"])
            lines.extend([row] + [Text("")] * (rh - 1))
        if not hosts:
            hint = "Press ← for All; a to add a host." if self.tab == "Recent" else "Press a to add a host, i to reload."
            lines = [Text("No hosts in this view.", style=colors["muted"]), Text(""), Text(hint, style=colors["muted"])]
        self.query_one("#host-list", Static).update(Text("\n").join(lines))
        if hosts:
            self.query_one("#host-scroll", VerticalScroll).scroll_to(y=self.selected * rh, animate=False)
        self._update_details()
        self.query_one("#status", Static).update(_esc(self.status))
        self.query_one("#status", Static).display = self.status != "Ready"
        self._update_footer()
        for i, tab in enumerate(self.TABS):
            button = self.query_one(f"#tab-{i}", Button)
            button.set_classes("active" if tab == self.tab else "")
            button.styles.color = accent if tab == self.tab else self._palette["muted"]
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
        declared.append(f"Sources: {_esc(compact_sources(h.sources, ascii=self._ascii))}")
        declared.append(f"Favorite: {'yes' if h.favorite else 'no'}  Uses: {h.uses}")
        try:
            argv = self.service.argv(h, command=None)
            preview = " ".join(shlex.quote(str(x)) for x in argv)
        except Exception as exc:
            preview = f"Unavailable: {exc}"
        details.update(f"[b]Declared / estimated[/b] [{self._palette['muted']}](not resolved config)[/]\n" + "\n".join(declared) + f"\n\n[b]SSH argv preview[/b]\n[{self._palette['muted']}]" + _esc(preview) + f"[/]\n\n[{self._palette['muted']}]Effective SSH config is never queried until you confirm with v.[/]")

    def _use_theme(self, settings: dict[str, Any]) -> None:
        self._palette = get_palette(settings)
        p = self._palette
        theme_id = settings.get("theme", DEFAULT_THEME)
        name = f"ssh-ls-{theme_id}-{p['accent'][1:]}"
        self.register_theme(Theme(
            name=name, primary=p["accent"], secondary=p["purple"], accent=p["accent"],
            background=p["bg"], foreground=p["fg"], surface=p["surface"], panel=p["surface"],
            warning=p["warning"], error=p["danger"], success=p["success"], text_alpha=1,
            variables={**{f"ssh-{key}": color for key, color in p.items() if key != "label"},
                       "border": p["border"], "input-selection-background": p["selection"],
                       "scrollbar": p["border"], "scrollbar-background": p["bg"]},
        ))
        self.theme = name

    def _apply_settings_style(self) -> None:
        settings = getattr(self.service, "settings", {}) or {}
        self._ascii = bool(settings.get("ascii", False))
        self._use_theme(settings)
        accent = self._palette["accent"]
        self.query_one("#brand", Static).styles.color = accent
        self.screen.add_class("ascii-borders" if settings.get("ascii", False) else "unicode-borders")
        if settings.get("ascii", False): self.screen.remove_class("unicode-borders")
        else: self.screen.remove_class("ascii-borders")
        for i, tab in enumerate(self.TABS):
            b = self.query_one(f"#tab-{i}", Button)
            b.styles.color = accent if tab == self.tab else self._palette["muted"]
            b.styles.border_bottom = ("none", "transparent")

    def _selected_host(self) -> Host | None:
        return self._filtered[self.selected] if self._filtered else None

    def _set_status(self, value: str) -> None:
        self.status = value
        if self.is_mounted:
            self.query_one("#status", Static).update(_esc(value))
            self.query_one("#status", Static).display = value != "Ready"
            self._update_footer()

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

    @on(Button.Pressed, "#tab-0, #tab-1, #tab-2")
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

    @on(Button.Pressed, "#open-settings")
    def settings_pressed(self) -> None:
        self._settings()

    def _settings(self) -> None:
        settings = dict(getattr(self.service, "settings", {}) or {})
        self.push_screen(SettingsScreen(settings), self._settings_done)

    def _settings_done(self, settings: dict[str, Any] | None) -> None:
        if settings is None:
            self._apply_settings_style(); self._refresh()
            return
        try:
            self.service.save_settings(settings); self._apply_settings_style(); self._refresh(); self._set_status("Settings saved")
        except Exception as exc:
            self._apply_settings_style(); self._refresh()
            self.push_screen(MessageScreen("Settings failed", _esc(exc)))

    def _reload(self) -> None:
        try:
            self.service.reload(); self._apply_settings_style(); self._refresh(); self._set_status("Host sources reloaded")
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
            self.push_screen(ConfirmScreen("Production connection", f"[{self._palette['danger']}]Production host:[/] {_esc(host.label)} ({_esc(host.destination)}). An SSH command will be handed to the launcher; this UI does not run it directly.{suffix}", "Connect", dangerous=True), finish)
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
                    f"Production: {'yes — confirmation required' if h.production else 'no'}\nSources: {_esc(compact_sources(h.sources, ascii=self._ascii))}")
            self.push_screen(MessageScreen(f"Host details: {h.label}", body))

    def _help(self) -> None:
        text = "[b]Navigation[/b]\nTab / Shift+Tab / ← / →  switch All, Recent, Favorites\nj / k  select host   •   /  search   •   Esc  return to navigation\nEnter  prepare SSH connection   •   r  enter explicit remote command\n\n[b]Host management[/b]\na add   e edit   c duplicate   x delete/hide (confirmation)\nSpace favorite   m reorder mode (j/k or ↑/↓, Esc finish)   i reload sources\ns sort   o settings   g local diagnostics\nv inspect effective SSH config (confirmation; Match exec can run local commands)\nd details on narrow screens   U reset overrides   H restore hidden   ? help   q quit\n\nShortcuts are inactive while editing text. Production launches always require confirmation."
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
            self._update_footer()

    def _update_footer(self) -> None:
        if not self.is_mounted:
            return
        accent = self._palette["accent"]
        def hint(key: str, label: str) -> str:
            return f"[bold {accent} on {self._palette['selection']}] {key} [/]  [{self._palette['fg']}]{label}[/]"
        if self._move_mode:
            primary = [hint("j/k", "Move"), hint("Esc", "Done")]
        else:
            primary = [hint("Enter", "Connect")]
            if self.size.width >= 50:
                primary.append(hint("/", "Search"))
        if self.size.width >= 85:
            primary.append(hint("Space", "Star"))
        secondary = [hint("o", "Settings")]
        if self.size.width >= 75:
            secondary.extend([hint("?", "Help"), hint("q", "Quit")])
        elif self.size.width >= 50:
            secondary.append(hint("?", "Help"))
        elif self.size.width >= 40:
            primary = [hint("↵", "Connect"), hint("o", "Settings")]
            secondary = []
        else:
            primary = [hint("o", "Settings")]
            secondary = []
        self.query_one("#footer-primary", Static).update("   ".join(primary))
        self.query_one("#footer-secondary", Static).update("   ".join(secondary))

    def on_resize(self, event) -> None:
        # At narrow widths details are deliberately not squeezed; d opens a readable modal.
        self._set_responsive(event.size.width)
