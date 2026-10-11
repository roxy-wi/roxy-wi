from pathlib import Path
import shutil
import subprocess

import pytest


def test_async_change_center_polling_and_notifications():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required to execute browser state tests')
    subprocess.run([node, str(Path(__file__).with_name('change_center_ui.cjs'))], check=True, timeout=15)
