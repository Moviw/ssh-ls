import json
import tempfile
import unittest
from pathlib import Path

from ssh_ls.service import Service
from ssh_ls.store import StateError, Store
from ssh_ls.themes import DEFAULT_THEME, THEMES, get_palette


class ThemeCoreTests(unittest.TestCase):
    def test_default_and_all_presets_have_complete_hex_palettes(self):
        self.assertEqual(DEFAULT_THEME, "tokyo-night")
        self.assertEqual(Store.empty()["settings"]["theme"], DEFAULT_THEME)
        self.assertEqual(set(THEMES), {
            "tokyo-night", "dracula", "catppuccin", "nord", "gruvbox",
            "rose-pine", "minimal", "cyberpunk", "ocean", "retro",
        })
        keys = {"label", "bg", "surface", "fg", "muted", "border", "accent",
                "purple", "warning", "danger", "success", "selection"}
        for name, palette in THEMES.items():
            with self.subTest(theme=name):
                self.assertEqual(set(palette), keys)
                for key in keys - {"label"}:
                    self.assertRegex(palette[key], r"^#[0-9a-fA-F]{6}$")

    def test_get_palette_copies_theme_and_applies_only_valid_custom_accent(self):
        settings = {"theme": "dracula", "accent": "auto"}
        palette = get_palette(settings)
        self.assertEqual(palette["accent"], THEMES["dracula"]["accent"])
        palette["bg"] = "#000000"
        self.assertNotEqual(THEMES["dracula"]["bg"], "#000000")
        self.assertEqual(get_palette({"theme": "dracula", "accent": "#123AbC"})["accent"], "#123AbC")
        self.assertEqual(get_palette({"theme": "dracula", "accent": "not-a-color"})["accent"], THEMES["dracula"]["accent"])

    def test_theme_settings_persist_through_store_and_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "state")
            service = Service(configs=[], histories=[], store=store)
            service.save_settings({"theme": "nord", "accent": "auto"})
            self.assertEqual(service.settings["theme"], "nord")
            self.assertEqual(store.read()["settings"]["theme"], "nord")
            self.assertEqual(store.read()["settings"]["accent"], "auto")
            reloaded = Service(configs=[], histories=[], store=store)
            self.assertEqual(reloaded.settings["theme"], "nord")

    def test_legacy_default_accent_migrates_read_only_and_custom_accent_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "state")
            legacy = Store.empty()
            legacy["settings"].pop("theme")
            legacy["settings"]["accent"] = "#7aa2f7"
            store.directory.mkdir(parents=True)
            original = json.dumps(legacy)
            store.path.write_text(original)
            loaded = store.read()
            self.assertEqual(loaded["settings"]["theme"], DEFAULT_THEME)
            self.assertEqual(loaded["settings"]["accent"], "auto")
            self.assertEqual(store.path.read_text(), original)

            legacy["settings"]["accent"] = "#bb9af7"
            original_custom = json.dumps(legacy)
            store.path.write_text(original_custom)
            loaded = store.read()
            self.assertEqual(loaded["settings"]["theme"], DEFAULT_THEME)
            self.assertEqual(loaded["settings"]["accent"], "#bb9af7")
            self.assertEqual(store.path.read_text(), original_custom)

    def test_invalid_theme_and_accent_preserve_saved_state_in_store_and_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "state")
            store.save_settings({"theme": "nord"})
            before = store.path.read_bytes()
            for change in ({"theme": "unknown"}, {"theme": []}, {"accent": "blue"}, {"accent": None}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    store.save_settings(change)
                self.assertEqual(store.path.read_bytes(), before)

            service = Service(demo=True, store=store)
            for change in ({"theme": "unknown"}, {"theme": None}, {"accent": "#12345g"}, {"accent": ""}):
                with self.subTest(service_change=change), self.assertRaises(ValueError):
                    service.save_settings(change)
                self.assertEqual(service.settings["theme"], "tokyo-night")
            self.assertEqual(store.path.read_bytes(), before)

            corrupt = json.loads(before)
            corrupt["settings"]["theme"] = "unknown"
            store.path.write_text(json.dumps(corrupt))
            bad_state = store.path.read_bytes()
            with self.assertRaises(StateError):
                store.read()
            self.assertEqual(store.path.read_bytes(), bad_state)


if __name__ == "__main__":
    unittest.main()
