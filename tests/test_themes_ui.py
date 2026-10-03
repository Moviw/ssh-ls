"""Pilot regressions for theme selection, preview, persistence, and rollback."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ssh_ls.models import Host
from ssh_ls.service import Service
from ssh_ls.store import Store
from ssh_ls.themes import DEFAULT_THEME, THEMES
from ssh_ls.ui import SSHApp, SettingsScreen


class ThemePilotTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_presets_are_selectable_and_apply_full_palette_on_save(self):
        service = Service(demo=True)
        app = SSHApp(service)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.assertEqual(service.settings["theme"], DEFAULT_THEME)
            for name, palette in THEMES.items():
                with self.subTest(theme=name):
                    await pilot.press("o")
                    self.assertIsInstance(app.screen, SettingsScreen)
                    theme_select = app.screen.query_one("#setting-theme")
                    self.assertIn(name, [value for _, value in theme_select._options])
                    theme_select.value = name
                    await pilot.pause()
                    await pilot.click("#save")
                    await pilot.pause()

                    self.assertEqual(service.settings["theme"], name)
                    self.assertEqual(service.settings["accent"], "auto")
                    self.assertEqual(app._palette, palette)
                    theme = app.get_theme(app.theme)
                    self.assertEqual(theme.background.lower(), palette["bg"])
                    self.assertEqual(theme.surface.lower(), palette["surface"])
                    self.assertEqual(theme.panel.lower(), palette["surface"])
                    self.assertEqual(theme.foreground.lower(), palette["fg"])
                    self.assertEqual(theme.variables["ssh-bg"].lower(), palette["bg"])
                    self.assertEqual(theme.variables["ssh-fg"].lower(), palette["fg"])
                    self.assertEqual(theme.variables["ssh-accent"].lower(), palette["accent"])
                    self.assertEqual(app.screen.styles.background.hex.lower(), palette["bg"])
                    self.assertEqual(app.query_one("#topline").styles.background.hex.lower(), palette["surface"])

                    row = app.query_one("#host-list").content
                    self.assertTrue(row.plain)
                    # Rich stores these semantic row styles as literal color strings.
                    self.assertEqual(row.spans[0].style.lower(), palette["accent"])
                    self.assertIn("bold " + palette["fg"], [span.style.lower() for span in row.spans])
                    self.assertIn(palette["muted"], [span.style.lower() for span in row.spans])

    async def test_preview_is_immediate_but_escape_or_back_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "state")
            service = Service(configs=[], histories=[], no_history=True, store=store)
            favorite = Host("custom:fictional", "fixture-box", "box.example.test",
                            custom=True, favorite=True, sources=["custom"])
            service.save(favorite)
            before = store.path.read_bytes()
            app = SSHApp(service)
            async with app.run_test(size=(90, 28)) as pilot:
                original = dict(app._palette)
                await pilot.press("o")
                select = app.screen.query_one("#setting-theme")
                select.value = "dracula"
                await pilot.pause()
                self.assertEqual(app._palette["bg"], THEMES["dracula"]["bg"])
                self.assertEqual(app.get_theme(app.theme).background.lower(), THEMES["dracula"]["bg"])
                self.assertEqual(store.path.read_bytes(), before)
                await pilot.press("escape")
                await pilot.pause()
                self.assertEqual(app._palette, original)
                self.assertEqual(store.path.read_bytes(), before)
                self.assertEqual([h.id for h in service.hosts], ["custom:fictional"])

                await pilot.press("o")
                app.screen.query_one("#setting-theme").value = "nord"
                await pilot.pause()
                await pilot.click("#cancel")
                await pilot.pause()
                self.assertEqual(app._palette, original)
                self.assertEqual(store.path.read_bytes(), before)

    async def test_theme_persists_after_restart_with_custom_favorite_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "state")
            service = Service(configs=[], histories=[], no_history=True, store=store)
            fixture = Host("custom:only", "fictional-favorite", "host.invalid",
                           custom=True, favorite=True, sources=["custom"])
            service.save(fixture)
            app = SSHApp(service)
            async with app.run_test(size=(90, 28)) as pilot:
                await pilot.press("o")
                app.screen.query_one("#setting-theme").value = "ocean"
                await pilot.pause()
                await pilot.click("#save")
                await pilot.pause()

            restarted = Service(configs=[], histories=[], no_history=True,
                                store=Store(Path(tmp) / "state"))
            self.assertEqual(restarted.settings["theme"], "ocean")
            self.assertEqual(restarted.settings["accent"], "auto")
            self.assertEqual([(h.id, h.label, h.favorite) for h in restarted.hosts],
                             [("custom:only", "fictional-favorite", True)])
            self.assertEqual(SSHApp(restarted)._palette, THEMES["ocean"])

    async def test_theme_change_resets_custom_accent_save_error_rolls_preview_back_and_compact_settings(self):
        class RejectingService(Service):
            def save_settings(self, settings):
                raise OSError("fixture write failure")

        service = RejectingService(demo=True)
        service.settings.update({"theme": "tokyo-night", "accent": "#123abc"})
        app = SSHApp(service)
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            await pilot.press("o")
            screen = app.screen
            self.assertIsInstance(screen, SettingsScreen)
            theme = screen.query_one("#setting-theme")
            accent = screen.query_one("#setting-accent")
            self.assertEqual(accent.value, "#123abc")
            theme.value = "retro"
            await pilot.pause()
            self.assertEqual(accent.value, "auto")
            self.assertEqual(app._palette["accent"], THEMES["retro"]["accent"])

            for selector in ("#setting-theme", "#setting-accent", "#setting-start-tab"):
                widget = screen.query_one(selector)
                self.assertLessEqual(widget.region.right, 60)
            self.assertLessEqual(screen.query_one("#save").region.bottom, 20)
            self.assertLessEqual(screen.query_one("#cancel").region.bottom, 20)

            await pilot.click("#save")
            await pilot.pause()
            self.assertEqual(service.settings["theme"], "tokyo-night")
            self.assertEqual(service.settings["accent"], "#123abc")
            self.assertEqual(app._palette["bg"], THEMES["tokyo-night"]["bg"])
            self.assertEqual(app.get_theme(app.theme).background.lower(), THEMES["tokyo-night"]["bg"])
            self.assertEqual(app.screen.title_text, "Settings failed")
            self.assertIn("fixture write failure", str(app.screen.query_one("#message-body").content))


if __name__ == "__main__":
    unittest.main()
