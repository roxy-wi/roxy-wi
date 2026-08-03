from types import SimpleNamespace

import pytest

from app import login
from app.modules.roxywi import auth as roxywi_auth


@pytest.fixture(autouse=True)
def clear_activity_throttle():
    roxywi_auth._last_activity_updates.clear()


@pytest.mark.security
def test_activity_tracking_failure_does_not_reject_request(app, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        roxywi_auth.user_sql,
        'update_last_act_user',
        lambda user_id, ip: (_ for _ in ()).throw(Exception('database is locked')),
    )
    monkeypatch.setattr(
        roxywi_auth.logger,
        'warning',
        lambda message, **kwargs: warnings.append((message, kwargs)),
    )

    with app.test_request_context('/'):
        roxywi_auth.update_user_activity(12345)

    assert warnings[0][0] == 'Cannot update user activity'
    assert warnings[0][1]['user_id'] == 12345


@pytest.mark.security
def test_parallel_activity_tracking_is_throttled(app, monkeypatch):
    updates = []
    monkeypatch.setattr(
        roxywi_auth.user_sql,
        'update_last_act_user',
        lambda user_id, ip: updates.append((user_id, ip)),
    )

    with app.test_request_context('/', environ_base={'REMOTE_ADDR': '192.0.2.10'}):
        for _ in range(10):
            roxywi_auth.update_user_activity(12345)

    assert updates == [(12345, '192.0.2.10')]


@pytest.mark.security
def test_global_login_check_does_not_load_full_page_user_context(app, monkeypatch):
    activity_updates = []
    monkeypatch.setattr(
        login.roxywi_common,
        'get_jwt_token_claims',
        lambda: {'user_id': 12345, 'group': 7},
    )
    monkeypatch.setattr(
        login.roxywi_common,
        'get_users_params',
        lambda: (_ for _ in ()).throw(AssertionError('full page context must not be loaded')),
    )
    monkeypatch.setattr(
        login.user_sql,
        'get_user_id',
        lambda user_id: SimpleNamespace(user_id=user_id, enabled=1, group_id=7),
    )
    monkeypatch.setattr(
        login.roxywi_auth,
        'update_user_activity',
        lambda user_id: activity_updates.append(user_id),
    )

    with app.test_request_context('/service/haproxy/127.0.0.1/last-edit'):
        login.check_login()

    assert activity_updates == [12345]
