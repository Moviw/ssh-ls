"""Isolated services for tests: a temporary SSH config and state, no history."""
import tempfile
from pathlib import Path

from ssh_ls.service import Service
from ssh_ls.store import Store

CONFIG = """Host atlas-dev
  HostName atlas.example.test
  User developer
Host prod-api
  HostName api.example.test
  User deploy
  ProxyJump bastion.example.test
"""


def isolated_service(cls=Service, store=None):
    tmp = tempfile.TemporaryDirectory(prefix="ssh-ls-test-")
    root = Path(tmp.name)
    config = root / "config"
    config.write_text(CONFIG)
    service = cls(configs=[config], no_history=True, store=store or Store(root / "state"))
    service._tmp = tmp  # keep the directory alive as long as the service
    return service
