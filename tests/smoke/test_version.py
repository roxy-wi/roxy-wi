from app.version import get_service_version


def test_service_version_is_set():
    assert isinstance(get_service_version(), str)
    assert get_service_version()


def test_version_api_is_public(client):
    response = client.get('/api/version')

    assert response.status_code == 200
    assert response.get_json() == {
        'service_version': get_service_version(),
    }


def test_legacy_internal_version_endpoint_uses_same_contract(client):
    response = client.get('/internal/show_version')

    assert response.status_code == 200
    assert response.get_json() == {
        'service_version': get_service_version(),
    }
