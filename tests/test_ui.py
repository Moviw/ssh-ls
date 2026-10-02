"""Pilot-level regressions for navigation safety and confirmed actions."""
from __future__ import annotations

import copy
import unittest

from ssh_ls.models import Host, LaunchRequest
from ssh_ls.ui import SSHApp


class FakeService:
    def __init__(self, hosts: list[Host]):
        self.hosts = hosts
        self.warnings: list[str] = []
        self.demo = True
        self.settings = {"accent": "#7aa2f7", "row_height": 1, "ascii": False}
        self.saved: list[Host] = []
        self.deleted: list[str] = []
        self.effective_calls = 0

    def reload(self): pass
    def save(self, host):
        self.saved.append(copy.deepcopy(host))
        for i, current in enumerate(self.hosts):
            if current.id == host.id:
                self.hosts[i] = host
                return host
        self.hosts.append(host)
        return host
    def delete(self, host):
        self.deleted.append(host.id)
        self.hosts = [h for h in self.hosts if h.id != host.id]
    def duplicate(self, host):
        clone = copy.deepcopy(host); clone.id += "-copy"; clone.label += " copy"; clone.custom = True
        self.hosts.append(clone); return clone
    def move(self, host, delta): pass
    def reset_overrides(self, host): return host
    def diagnose(self, host=None): return "local only"
    def effective(self, host):
        self.effective_calls += 1
        return "hostname example.test"
    def argv(self, host, command=None): return ["ssh", host.destination]
    def save_settings(self, settings): self.settings.update(settings)


def hosts() -> list[Host]:
    return [
        Host("one", "alpha", "alpha.example.test", user="alice", sources=["config:test"], production=True),
        Host("two", "beta", "beta.example.test", sources=["history:zsh:test"], last_used=42),
    ]


class SSHAppPilotTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_shortcuts_and_input_safety_and_tabs(self):
        service = FakeService(hosts())
        app = SSHApp(service)
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.press("j")
            self.assertEqual(app.selected, 1)
            await pilot.press("/")
            await pilot.press("q", "j", "k")
            self.assertEqual(app.selected, 0)
            self.assertEqual(app.search_text, "qjk")
            app.query_one("#search").value = ""
            await pilot.press("escape")
            await pilot.press("right")
            self.assertEqual(app.tab, "Recent")
            self.assertEqual(app._filtered[0].id, "two")

    async def test_favorite_crud_and_empty_view(self):
        service = FakeService(hosts())
        app = SSHApp(service)
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.press("f")
            self.assertTrue(service.hosts[0].favorite)
            self.assertTrue(service.saved[-1].favorite)
            await pilot.press("c")
            self.assertEqual(len(service.hosts), 3)
            await pilot.press("right", "right")
            self.assertEqual(app.tab, "Favorites")
            # Only alpha is a favorite, and its source is unaffected by the separate copy.
            self.assertEqual([h.id for h in app._filtered], ["one", "one-copy"])
            await pilot.press("right")
            self.assertEqual(app.tab, "History")
            self.assertEqual([h.id for h in app._filtered], ["two"])
            await pilot.press("/")
            await pilot.press("z", "z", "z")
            self.assertEqual(app._filtered, [])
            self.assertIn("No hosts", str(app.query_one("#host-list").content))


    async def test_add_form_and_settings_save(self):
        service = FakeService(hosts())
        app = SSHApp(service)
        async with app.run_test(size=(110, 34)) as pilot:
            await pilot.press("a")
            app.screen.query_one("#field-label").value = "new-lab"
            app.screen.query_one("#field-hostname").value = "lab.example.test"
            app.screen.query_one("#field-port").value = "2200"
            await pilot.click("#save")
            self.assertEqual(service.hosts[-1].label, "new-lab")
            self.assertEqual(service.hosts[-1].port, 2200)
            await pilot.press("o")
            app.screen.query_one("#setting-accent").value = "#bb9af7"
            app.screen.query_one("#setting-ascii").value = True
            await pilot.click("#save")
            self.assertEqual(service.settings["accent"], "#bb9af7")
            self.assertTrue(service.settings["ascii"])


    async def test_compact_tabs_and_selected_row_scroll(self):
        compact = SSHApp(FakeService(hosts()))
        async with compact.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            tabs = [compact.query_one(f"#tab-{i}") for i in range(4)]
            self.assertTrue(all(tab.region.right <= 60 for tab in tabs))
            self.assertEqual(len({tab.region.y for tab in tabs}), 1)
            self.assertFalse(compact.query_one("#brand").display)
            self.assertLessEqual(compact.query_one("#search").region.right, 60)

        many = [Host(str(i), f"host-{i:02d}", f"node-{i}.example.test", order=i) for i in range(30)]
        app = SSHApp(FakeService(many))
        async with app.run_test(size=(90, 18)) as pilot:
            for _ in range(25):
                await pilot.press("j")
            scroll = app.query_one("#host-scroll")
            self.assertEqual(app.selected, 25)
            self.assertGreater(scroll.scroll_y, 0)
            # The selected item remains within the vertical scroll viewport.
            self.assertGreaterEqual(25, scroll.scroll_y)
            self.assertLess(25, scroll.scroll_y + scroll.size.height)

    async def test_production_launch_requires_confirmation_and_narrow_details(self):
        service = FakeService(hosts())
        app = SSHApp(service)
        async with app.run_test(size=(70, 24)) as pilot:
            self.assertTrue(app.query_one("#detail-pane").display is False)
            await pilot.press("enter")
            self.assertIsNone(app.result)
            self.assertTrue(app.screen.query_one("#yes").is_mounted)
            # Confirmation is explicit; accepting returns a request rather than running SSH.
            await pilot.click("#yes")
            self.assertEqual(app.result, LaunchRequest(service.hosts[0], None))
            self.assertEqual(service.effective_calls, 0)

    async def test_narrow_details_open_as_modal(self):
        service = FakeService(hosts())
        app = SSHApp(service)
        async with app.run_test(size=(70, 24)) as pilot:
            self.assertFalse(app.query_one("#detail-pane").display)
            await pilot.press("d")
            self.assertTrue(app.screen.query("#message-box"))
            await pilot.click("#close")
            self.assertEqual(app.tab, "All")
