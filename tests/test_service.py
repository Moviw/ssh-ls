import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ssh_ls.models import Host
from ssh_ls.service import Service
from ssh_ls.store import Store


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.config = self.directory / "config"
        self.config.write_text("Host alpha\n HostName alpha.example.test\n User scientist\n Port 2222\nHost beta\n HostName beta.example.test\n")
        self.history = self.directory / "history"
        self.history.write_text("ssh alpha\nssh -p 2223 lab.example.test\n")
        self.store = Store(self.directory / "state")

    def service(self):
        return Service(configs=[self.config], histories=[self.history], store=self.store)

    def test_overrides_and_native_refresh(self):
        service = self.service()
        host = copy.deepcopy(next(h for h in service.hosts if h.alias == "alpha"))
        host.port = 2022
        host.favorite = True
        service.save(host)
        self.assertIn("2022", service.argv(host))
        self.config.write_text(self.config.read_text().replace("alpha.example.test", "new.example.test"))
        service.reload()
        changed = next(h for h in service.hosts if h.alias == "alpha")
        self.assertEqual(changed.hostname, "new.example.test")
        self.assertEqual(changed.port, 2022)
        self.assertTrue(changed.favorite)
        service.reset_overrides(changed)
        self.assertEqual(changed.port, 2222)
        self.assertNotIn("-p", service.argv(changed))

    def test_hidden_restore_duplicate_and_reorder(self):
        service = self.service()
        original = self.config.read_bytes()
        first, second = service.hosts[:2]
        service.delete(first)
        self.assertTrue(first.hidden)
        service.restore_hidden()
        self.assertFalse(first.hidden)
        clone = service.duplicate(first)
        self.assertTrue(clone.custom)
        self.assertEqual(clone.alias, first.alias)
        edited = copy.deepcopy(clone)
        edited.port = 4444
        service.save(edited)
        self.assertIn("4444", service.argv(edited))
        service.reload()
        edited = next(h for h in service.hosts if h.id == edited.id)
        edited2 = copy.deepcopy(edited)
        edited2.hostname = "override.example.test"
        service.save(edited2)
        self.assertIn("HostName=override.example.test", service.argv(edited2))
        service.delete(edited2)
        self.assertNotIn(edited2.id, [h.id for h in service.hosts])
        service.move(first, 1)
        self.assertEqual(self.config.read_bytes(), original)

    def test_demo_never_reads_user_data_or_executes_ssh(self):
        with patch("ssh_ls.service.discover_config", side_effect=AssertionError("config read")), patch("ssh_ls.service.discover_history", side_effect=AssertionError("history read")), patch("ssh_ls.service.effective", side_effect=AssertionError("process start")), patch.object(Store, "read", side_effect=AssertionError("state read")), patch.object(Store, "save_host", side_effect=AssertionError("state write")):
            service = Service(demo=True)
            service.record_use(service.hosts[0])
            self.assertIn("DEMO", service.effective(service.hosts[0]))
            self.assertIn("DEMO", service.diagnose())

    def test_corrupt_state_does_not_get_overwritten(self):
        service = self.service()
        self.store.directory.mkdir(parents=True, exist_ok=True)
        self.store.path.write_text("corrupt")
        service.reload()
        self.assertTrue(service.state_error)
        with self.assertRaises(ValueError):
            service.save(service.hosts[0])
        self.assertEqual(self.store.path.read_text(), "corrupt")

    def test_history_port_edit_and_reset(self):
        self.history.write_text("ssh unlisted.example.test\n")
        service = self.service()
        host = copy.deepcopy(next(h for h in service.hosts if h.history))
        self.assertNotIn("-p", service.argv(host))
        host.favorite = True
        service.save(host)
        service.reload()
        host = copy.deepcopy(next(h for h in service.hosts if h.history))
        self.assertNotIn("-p", service.argv(host))
        host.port = 2222
        service.save(host)
        self.assertIn("2222", service.argv(host))
        service.reload()
        host = next(h for h in service.hosts if h.history)
        self.assertIn("2222", service.argv(host))
        service.reset_overrides(host)
        self.assertNotIn("-p", service.argv(host))

    def test_settings_validate_and_reload(self):
        service = self.service()
        service.save_settings({"accent": "#bb9af7", "row_height": 3, "ascii": True})
        service.reload()
        self.assertEqual(service.settings["row_height"], 3)
        self.assertTrue(service.settings["ascii"])
        with self.assertRaises(ValueError):
            service.save_settings({"accent": "notacolor"})


if __name__ == "__main__":
    unittest.main()
