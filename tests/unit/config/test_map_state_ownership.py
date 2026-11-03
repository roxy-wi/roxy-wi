"""Creating a map must not repair ownership of the shared state tree."""
import os
import subprocess

import pytest

from app.modules.config import add


def test_map_creation_leaves_helper_state_untouched(tmp_path, monkeypatch):
    state = tmp_path / 'metrics' / 'metrics-state.db'
    state.parent.mkdir()
    state.write_bytes(b'helper-owned state')
    before = state.stat()
    monkeypatch.setattr(add.get_config, 'get_config_var', lambda *args: str(tmp_path))
    monkeypatch.setattr(add.roxywi_common, 'logging', lambda *args, **kwargs: None)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: pytest.fail('Ownership subprocess'))
    if hasattr(os, 'chown'):
        monkeypatch.setattr(os, 'chown', lambda *args, **kwargs: pytest.fail('Runtime chown'))
    assert add.create_map('192.0.2.1', 'routes.map', '1') == 'success: '
    assert (tmp_path / 'maps' / '1' / 'routes.map').exists()
    assert state.read_bytes() == b'helper-owned state'
    assert (state.stat().st_uid, state.stat().st_gid) == (before.st_uid, before.st_gid)
