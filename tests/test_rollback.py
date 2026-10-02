import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from ssh_ls.models import Host
from ssh_ls.store import Store


class RollbackTests(unittest.TestCase):
    def test_same_input_baseline_modified_and_rollback(self):
        script = Path(__file__).resolve().parents[1] / "ROLLBACK.sh"
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "fixture")
            host = Host("fixture", "Fictional", "fixture.example.test")
            store.save_host(host)
            baseline = store.path.read_bytes()
            host.favorite = True
            store.save_host(host)
            changed = store.path.read_bytes()
            self.assertNotEqual(baseline, changed)
            restored = Path(tmp) / "copy.json"
            restored.write_bytes(changed)
            restored.with_suffix(".json.bak").write_bytes(baseline)
            result = subprocess.run([str(script), str(restored)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(hashlib.sha256(restored.read_bytes()).digest(), hashlib.sha256(baseline).digest())
            self.assertEqual(json.loads(baseline)["hosts"]["fixture"]["favorite"], False)
            self.assertEqual(json.loads(changed)["hosts"]["fixture"]["favorite"], True)
            self.assertEqual(json.loads(restored.read_bytes())["hosts"]["fixture"]["favorite"], False)
            self.assertEqual(store.path.read_bytes(), changed)
            print("STATE BASELINE favorite=false; MODIFIED favorite=true; ROLLBACK favorite=false; restored hash matches")

    def test_missing_backup_refuses_restore(self):
        script = Path(__file__).resolve().parents[1] / "ROLLBACK.sh"
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "copy.json"
            copy.write_text("unchanged")
            result = subprocess.run([str(script), str(copy)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(copy.read_text(), "unchanged")


if __name__ == "__main__":
    unittest.main()
