from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('script', ['pacemaker_ui.cjs'])
def test_pacemaker_status_and_review_widgets(script):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for browser-script regression tests')
    subprocess.run([node, str(Path(__file__).with_name(script))], check=True, timeout=15)
