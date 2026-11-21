"""Saved credentials must not be silently reused for a new destination identity."""
import pytest

from app.modules.integrations.connection_options import parse_input, require_credentials_for_identity_change
from app.modules.roxywi.exception import RoxywiValidationError


def connection():
    return parse_input(dict(name='Synthetic connection', group_id=1, transport='https',
                           url='https://audit.example.test/events', auth='bearer'))


@pytest.mark.parametrize(('field', 'value'), [
    ('transport', 'tcp_tls'), ('host', 'other.example.test'), ('port', 8443),
    ('url', 'https://audit.example.test/another-collector'), ('auth', 'api_key'),
    ('username', 'another-account'), ('header_name', 'X-Another-Key'),
])
@pytest.mark.parametrize('credential', ['password', 'token', 'client_cert_pem', 'client_key_pem'])
def test_identity_changes_require_explicit_credential_decision(field, value, credential):
    before = connection()
    changed = before.model_copy(update={field: value})
    with pytest.raises(RoxywiValidationError, match='Re-enter or clear'):
        require_credentials_for_identity_change(changed, before.model_dump(), {credential: 'HiddenCredential'})
    replaced = changed.model_copy(update={'secrets': {credential: 'ExplicitReplacement'}})
    require_credentials_for_identity_change(replaced, before.model_dump(), {credential: 'HiddenCredential'})
    cleared = changed.model_copy(update={'clear_secrets': [credential]})
    require_credentials_for_identity_change(cleared, before.model_dump(), {credential: 'HiddenCredential'})


def test_rename_timeout_and_framing_preserve_credentials_for_same_identity():
    before = connection()
    changed = before.model_copy(update={'name': 'Renamed', 'timeout': 9, 'framing': 'newline'})
    require_credentials_for_identity_change(changed, before.model_dump(), {'token': 'HiddenCredential'})


def test_retargeting_may_preserve_ca_but_requires_decisions_for_every_authentication_credential():
    before = connection()
    changed = before.model_copy(update={'host': 'other.example.test', 'secrets': {'token': 'Replacement'}})
    require_credentials_for_identity_change(changed, before.model_dump(), {'ca_pem': 'PublicCA', 'token': 'Hidden'})
    with pytest.raises(RoxywiValidationError):
        require_credentials_for_identity_change(changed, before.model_dump(), {'token': 'Hidden', 'client_key_pem': 'HiddenKey'})
    changed.clear_secrets = ['client_key_pem']
    require_credentials_for_identity_change(changed, before.model_dump(), {'token': 'Hidden', 'client_key_pem': 'HiddenKey'})


def test_expired_connection_budget_closes_before_credentials_can_be_sent(monkeypatch):
    from types import SimpleNamespace
    from time import monotonic
    from app.modules.integrations import connection_transport
    closed, sent = [], []
    stream = SimpleNamespace(close=lambda: closed.append(True), send=lambda value: sent.append(value))
    monkeypatch.setattr(connection_transport, 'open_socket', lambda *_: stream)
    with pytest.raises(TimeoutError):
        with connection_transport.bounded_stream({}, {}, monotonic()-1) as connected:
            connected.send('MustNotBeSent')
    assert closed == [True] and sent == []
