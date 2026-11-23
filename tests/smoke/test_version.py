import pytest

from app.modules.db import roxy as roxy_sql
from app.version import get_service_version


def test_service_version_is_set():
    assert isinstance(get_service_version(), str)
    assert get_service_version()


def test_version_api_is_public(client):
    response = client.get('/api/version')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['service_version'] == get_service_version()
    assert payload['latest_version'] == '0'
    assert payload['update_available'] is False


@pytest.mark.parametrize(('stored', 'latest', 'available'), [
    ('', '0', False),
    ('invalid version', '0', False),
    (get_service_version(), get_service_version(), False),
    ('99.0.0', '99.0.0', True),
])
def test_version_api_reports_cached_release(client, monkeypatch, stored, latest, available):
    monkeypatch.setattr(roxy_sql, 'get_tool_new_version', lambda _tool: stored)

    response = client.get('/api/version')

    assert response.status_code == 200
    assert response.get_json() == {
        'service_version': get_service_version(),
        'latest_version': latest,
        'update_available': available,
    }
