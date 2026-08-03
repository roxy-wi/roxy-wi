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
