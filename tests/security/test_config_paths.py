from pathlib import Path

import pytest

from app.modules.config.common import get_config_dir, resolve_config_version_path


@pytest.mark.security
def test_config_version_path_stays_inside_service_directory():
    resolved = Path(resolve_config_version_path('haproxy', 'server-1.cfg'))
    assert resolved.parent == Path(get_config_dir('haproxy')).resolve()


@pytest.mark.security
@pytest.mark.parametrize('version', ['../secret', '../../etc/passwd'])
def test_config_version_path_rejects_traversal(version):
    with pytest.raises(ValueError, match='outside the allowed directory'):
        resolve_config_version_path('haproxy', version)
