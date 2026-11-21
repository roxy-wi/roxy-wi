"""Verified login may use the bounded optional audit reserve; denials stay charged."""
from types import SimpleNamespace

import pytest

from app.modules.authentication import security
from app.modules.db.db_model import AuthenticationChallenge, AuthenticationEvent, UserSecurity


@pytest.fixture
def optional_audit(monkeypatch):
    class AuditStorageUnavailable(Exception):
        pass
    state = SimpleNamespace(calls=[], unavailable=False)
    def record(*args, **kwargs):
        state.calls.append((args, kwargs))
        if state.unavailable:
            raise AuditStorageUnavailable('Synthetic exhausted audit reserve')
    adapter = SimpleNamespace(record=record, AuditStorageUnavailable=AuditStorageUnavailable)
    original_spec = security.importlib.util.find_spec
    original_import = security.importlib.import_module
    monkeypatch.setattr(security.importlib.util, 'find_spec',
        lambda name: object() if name == 'app.modules.audit' else original_spec(name))
    monkeypatch.setattr(security.importlib, 'import_module',
        lambda name: adapter if name == 'app.modules.audit.events' else original_import(name))
    state.error = AuditStorageUnavailable
    return state


@pytest.mark.parametrize('event', ['authentication.verified', 'authentication.passkey.login',
                                   'authentication.recovery.used'])
def test_completed_login_proof_uses_bounded_audit_reserve(product, optional_audit, event):
    security.record(product.admin.user_id, event)
    args, details = optional_audit.calls[-1]
    assert args == (event, 'succeeded')
    assert details['force'] is True
    assert details['user_id'] == product.admin.user_id


@pytest.mark.parametrize('event,outcome,verified', [
    ('authentication.verified', 'denied', True),
    ('authentication.passkey.login', 'denied', False),
    ('authentication.verified', 'success', False),
    ('authentication.recovery.used', 'failed', False),
    ('authentication.totp.enrolled', 'success', True),
    ('authentication.passkey.enrolled', 'success', True),
    ('authentication.policy.changed', 'success', True),
])
def test_unverified_denied_and_configuration_writes_cannot_use_reserve(product, optional_audit, event, outcome, verified):
    security.record(product.admin.user_id, event, outcome, actor_verified=verified)
    _args, details = optional_audit.calls[-1]
    assert details.get('force', False) is False
    assert details['user_id'] == (product.admin.user_id if verified else None)


def test_exhausted_reserve_propagates_positive_failure_and_rolls_back_epoch(product, optional_audit):
    optional_audit.unavailable = True
    before = security.user_epoch(product.admin.user_id)
    with pytest.raises(optional_audit.error):
        with security.atomic():
            UserSecurity.update(epoch=UserSecurity.epoch + 1).where(UserSecurity.user_id == product.admin.user_id).execute()
            security.record(product.admin.user_id, 'authentication.recovery.used')
    assert security.user_epoch(product.admin.user_id) == before
    assert not AuthenticationEvent.select().exists()
    assert optional_audit.calls[-1][1]['force'] is True


def test_exhausted_audit_preserves_denial_gate_and_local_record(product, optional_audit):
    optional_audit.unavailable = True
    token = security.issue_challenge(product.admin, 'audit.reserve.contract')
    def deny(user, payload):
        security.record(user.user_id, 'authentication.passkey.login', 'denied',
                        actor_verified=False, reason_code='invalid_assertion')
        return False
    for _ in range(7):
        assert security.consume_challenge(token, 'audit.reserve.contract', verify=deny) is None
    assert AuthenticationChallenge.get_by_id(security.digest(token)).attempts == 5
    assert UserSecurity.get_by_id(product.admin.user_id).blocked_until > security.now()
    assert AuthenticationEvent.select().where(AuthenticationEvent.outcome == 'denied').count() == 5
    assert len(optional_audit.calls) == 5
    assert all(not details.get('force', False) and details['user_id'] is None
               for _args, details in optional_audit.calls)
