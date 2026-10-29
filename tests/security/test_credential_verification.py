"""Optional auth features must compose without replacing one another's checks."""
from types import SimpleNamespace

import pytest

from app.modules.common import credential_verification as credentials

pytestmark = pytest.mark.security


def test_legacy_sessions_work_without_optional_features_but_pat_cannot(monkeypatch):
    monkeypatch.setattr(credentials, '_optional', lambda _: None)
    assert credentials.verify({'user_id': '1', 'group': '1'})
    assert not credentials.verify({'credential_type': 'pat', 'user_id': '1', 'group': '1'})
    assert not credentials.verify({'credential_type': 'unknown'})


@pytest.mark.parametrize('field', credentials.SECURITY_PROOF_FIELDS)
def test_removing_security_provider_does_not_downgrade_bound_session(monkeypatch, field):
    monkeypatch.setattr(credentials, '_optional', lambda _: None)
    assert not credentials.verify({'user_id': '1', 'group': '1', field: 0})


def test_pat_uses_its_provider_once_and_never_human_session_fallback(monkeypatch):
    calls = []
    def load(name):
        calls.append(name)
        assert name == 'app.modules.api_tokens.service'
        return SimpleNamespace(verify=lambda payload: payload['pat_id'] == 'known')
    monkeypatch.setattr(credentials, '_optional', load)
    assert credentials.verify({'credential_type': 'pat', 'pat_id': 'known'})
    assert not credentials.verify({'credential_type': 'pat', 'pat_id': 'unknown'})
    assert calls == ['app.modules.api_tokens.service']*2


def test_installed_security_validation_is_never_skipped(monkeypatch):
    monkeypatch.setattr(credentials, '_optional', lambda _: SimpleNamespace(
        validate_session=lambda payload: payload.get('auth_epoch') == 2))
    assert not credentials.verify({'user_id': '1', 'group': '1'})
    assert not credentials.verify({'auth_epoch': 1})
    assert credentials.verify({'auth_epoch': 2})


def test_provider_failures_do_not_fall_back_to_legacy_authentication(monkeypatch):
    def failure(_):
        raise RuntimeError('Provider unavailable')
    monkeypatch.setattr(credentials, '_optional', failure)
    with pytest.raises(RuntimeError, match='Provider unavailable'):
        credentials.verify({'user_id': '1', 'group': '1'})
