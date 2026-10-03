"""Built-in palettes for the terminal UI (kept independent of Textual)."""
import re


DEFAULT_THEME = "tokyo-night"

# Each palette uses the same semantic slots so the UI can apply a theme without
# knowing which family it came from.
THEMES = {
    "tokyo-night": {
        "label": "Tokyo Night", "bg": "#1a1b26", "surface": "#24283b",
        "fg": "#c0caf5", "muted": "#9aa5ce", "border": "#414868",
        "accent": "#7aa2f7", "purple": "#bb9af7", "warning": "#e0af68",
        "danger": "#f7768e", "success": "#9ece6a", "selection": "#2f334d",
    },
    "dracula": {
        "label": "Dracula", "bg": "#282a36", "surface": "#343746",
        "fg": "#f8f8f2", "muted": "#929ac4", "border": "#44475a",
        "accent": "#bd93f9", "purple": "#ff79c6", "warning": "#f1fa8c",
        "danger": "#ff5555", "success": "#50fa7b", "selection": "#343746",
    },
    "catppuccin": {
        "label": "Catppuccin Mocha", "bg": "#1e1e2e", "surface": "#313244",
        "fg": "#cdd6f4", "muted": "#a6adc8", "border": "#45475a",
        "accent": "#cba6f7", "purple": "#89b4fa", "warning": "#f9e2af",
        "danger": "#f38ba8", "success": "#a6e3a1", "selection": "#3b3c52",
    },
    "nord": {
        "label": "Nord", "bg": "#2e3440", "surface": "#3b4252",
        "fg": "#eceff4", "muted": "#aab4c6", "border": "#4c566a",
        "accent": "#88c0d0", "purple": "#b48ead", "warning": "#ebcb8b",
        "danger": "#bf616a", "success": "#a3be8c", "selection": "#3b4252",
    },
    "gruvbox": {
        "label": "Gruvbox Dark", "bg": "#282828", "surface": "#3c3836",
        "fg": "#ebdbb2", "muted": "#a89984", "border": "#504945",
        "accent": "#fe8019", "purple": "#d3869b", "warning": "#fabd2f",
        "danger": "#fb4934", "success": "#b8bb26", "selection": "#302c2a",
    },
    "rose-pine": {
        "label": "Rosé Pine", "bg": "#191724", "surface": "#1f1d2e",
        "fg": "#e0def4", "muted": "#908caa", "border": "#403d52",
        "accent": "#ebbcba", "purple": "#c4a7e7", "warning": "#f6c177",
        "danger": "#eb6f92", "success": "#9ccfd8", "selection": "#26233a",
    },
    "minimal": {
        "label": "Minimal", "bg": "#090909", "surface": "#171717",
        "fg": "#eeeeee", "muted": "#999999", "border": "#444444",
        "accent": "#ffffff", "purple": "#aaaaaa", "warning": "#e6c789",
        "danger": "#e38d91", "success": "#9bc5a1", "selection": "#333333",
    },
    "cyberpunk": {
        "label": "Cyberpunk", "bg": "#100b1d", "surface": "#201331",
        "fg": "#f5eaff", "muted": "#9a73a8", "border": "#48245c",
        "accent": "#00f0ff", "purple": "#ff3df2", "warning": "#ffe66d",
        "danger": "#ff3864", "success": "#32f5a5", "selection": "#3b1e50",
    },
    "ocean": {
        "label": "Ocean", "bg": "#071923", "surface": "#102a3a",
        "fg": "#d7edf5", "muted": "#6f9eae", "border": "#214355",
        "accent": "#4cc9f0", "purple": "#9b8cff", "warning": "#f4c95d",
        "danger": "#ff6b6b", "success": "#61d095", "selection": "#194257",
    },
    "retro": {
        "label": "Retro", "bg": "#17130d", "surface": "#292116",
        "fg": "#f0dfb0", "muted": "#a28b62", "border": "#4a3a22",
        "accent": "#ffd700", "purple": "#c58b70", "warning": "#f2cf69",
        "danger": "#d87558", "success": "#a8b86c", "selection": "#49391f",
    },
}

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")


def get_palette(settings):
    """Return an independent palette mapping for the selected settings."""
    theme = THEMES[settings.get("theme", DEFAULT_THEME)]
    palette = theme.copy()
    accent = settings.get("accent", "auto")
    if isinstance(accent, str) and _HEX_COLOR.fullmatch(accent):
        palette["accent"] = accent
    return palette
