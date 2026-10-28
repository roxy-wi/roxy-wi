import pytest

from app.modules.pacemaker import service
from app.modules.pacemaker.remote import RemoteError
from app.modules.roxywi.exception import (
    RoxywiConflictError, RoxywiInputError, RoxywiResourceNotFound, RoxywiValidationError,
)


@pytest.mark.parametrize('error,status,message', [
    (ValueError, 400, 'Invalid value provided; check the request fields'),
    (RemoteError, 502, 'Cluster command failed; inspect application and node logs'),
    (RuntimeError, 502, 'Cluster operation failed; inspect application and node logs'),
])
def test_api_never_exposes_unexpected_exception_text(client, authenticated, monkeypatch, caplog, error, status, message):
    private = 'Traceback: /private/cluster/config.xml password=secret-resource-value'

    def failed_lookup(*_args):
        raise error(private)

    monkeypatch.setattr(service, 'get_cluster', failed_lookup)
    response = client.get('/pacemaker/api/1/status', headers=authenticated[1])
    assert response.status_code == status
    assert response.get_json() == {'error': message}
    assert private not in response.text and private not in caplog.text


@pytest.mark.parametrize('error,status', [
    (RoxywiInputError, 400), (RoxywiValidationError, 400),
    (RoxywiConflictError, 409), (RoxywiResourceNotFound, 404),
])
def test_deliberate_public_errors_retain_actionable_messages(client, authenticated, monkeypatch, error, status):
    message = 'Review the current cluster configuration before retrying'

    def rejected_lookup(*_args):
        raise error(message)

    monkeypatch.setattr(service, 'get_cluster', rejected_lookup)
    response = client.get('/pacemaker/api/1/status', headers=authenticated[1])
    assert response.status_code == status
    assert response.get_json() == {'error': message}
