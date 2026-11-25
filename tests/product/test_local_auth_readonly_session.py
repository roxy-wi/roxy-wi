"""Session inspection must not upgrade a streamed SQLite read into a write."""
import itertools
import sqlite3
import threading

import pytest
from peewee import SqliteDatabase

from app.modules.authentication import security
from app.modules.db.db_model import AuthenticationPolicy, ConfigChange, User, UserSecurity
from app.routes.change import routes


@pytest.mark.parametrize('interleave', [False, True])
def test_change_list_repeated_authentication_after_concurrent_write(product_client, product, monkeypatch, interleave):
    if not isinstance(product.db, SqliteDatabase):
        pytest.skip('SQLite WAL snapshot upgrade regression')
    for title in ('First synthetic change', 'Second synthetic change'):
        ConfigChange.create(server_id=product.server.server_id, group_id=1, user_id=product.admin.user_id,
            service='haproxy', action='reload', status='draft', title=title, requires_approval=0,
            remote_path='/etc/haproxy/haproxy.cfg', draft_path=str(product.root/title),
            rollback_path=str(product.root/(title+'.old')), drift_status='in_sync')
    original_list = routes.change_sql.list_changes
    failures = []
    original_error = routes._error_response
    def capture(error):
        failures.append(type(error).__name__)
        return original_error(error)
    monkeypatch.setattr(routes, '_error_response', capture)
    def listing(*args, **kwargs):
        stream = iter(original_list(*args, **kwargs))
        first = next(stream)  # Keep the real ConfigChange cursor open.
        if interleave:
            errors = []
            def writer():
                try:
                    with sqlite3.connect(product.db.database, timeout=3) as database:
                        database.execute('UPDATE user SET last_login_ip=? WHERE id=?',
                                         ('192.0.2.99', product.admin.user_id))
                except Exception as error:
                    errors.append(type(error).__name__)
            thread = threading.Thread(target=writer)
            thread.start()
            thread.join(timeout=5)
            assert not thread.is_alive() and not errors
        return itertools.chain([first], stream)
    monkeypatch.setattr(routes.change_sql, 'list_changes', listing)
    response = product_client.get('/changes/api')
    assert response.status_code == 200, response.get_json()
    assert {row['title'] for row in response.get_json()['data']} == {
        'First synthetic change', 'Second synthetic change'}
    assert not failures


def inspected_session(product, monkeypatch):
    user, expected = security.capture_account(product.admin.user_id)
    claims = dict(user_id=user.user_id, group='1', **security.login_proof(user, 'password', expected=expected))
    statements = []
    original = product.db.execute_sql
    def execute(sql, *args, **kwargs):
        statements.append(sql.upper())
        return original(sql, *args, **kwargs)
    monkeypatch.setattr(product.db, 'execute_sql', execute)
    return claims, statements


def assert_read_only(statements):
    assert statements
    assert all(not sql.lstrip().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'BEGIN IMMEDIATE'))
               and 'FOR UPDATE' not in sql for sql in statements)


def test_session_validation_reads_policy_memberships_and_factors_without_writes(product, monkeypatch):
    User.update(role_id='3').where(User.user_id == product.admin.user_id).execute()
    AuthenticationPolicy.update(mode='admin', grace_until=security.now()+86400).execute()
    claims, statements = inspected_session(product, monkeypatch)
    assert security.validate_session(claims)
    assert_read_only(statements)


@pytest.mark.parametrize('missing', ['security', 'policy'])
def test_session_validation_never_initializes_missing_state(product, monkeypatch, missing):
    claims, statements = inspected_session(product, monkeypatch)
    model = UserSecurity if missing == 'security' else AuthenticationPolicy
    model.delete().execute()
    statements.clear()
    assert not security.validate_session(claims)
    assert_read_only(statements)
    assert model.select().count() == 0


def test_epoch_inspection_is_read_only(product, monkeypatch):
    _claims, statements = inspected_session(product, monkeypatch)
    assert isinstance(security.user_epoch(product.admin.user_id), int)
    assert_read_only(statements)


@pytest.mark.parametrize('missing', ['security', 'policy'])
def test_epoch_inspection_rejects_missing_state_without_creating_it(product, monkeypatch, missing):
    from app.modules.roxywi.exception import RoxywiPublicError
    _claims, statements = inspected_session(product, monkeypatch)
    model = UserSecurity if missing == 'security' else AuthenticationPolicy
    model.delete().execute()
    statements.clear()
    with pytest.raises(RoxywiPublicError):
        security.user_epoch(product.admin.user_id)
    assert_read_only(statements)
    assert model.select().count() == 0


def test_pat_change_list_keeps_repeated_epoch_checks_read_only(product_client, product, app, monkeypatch):
    import importlib.util
    if importlib.util.find_spec('app.modules.api_tokens') is None:
        pytest.skip('Optional personal-token provider is not installed')
    if not isinstance(product.db, SqliteDatabase):
        pytest.skip('SQLite WAL snapshot upgrade regression')
    from app.api.routes import change_routes as api_routes
    from tests.product.test_personal_tokens import create, api
    remote = api(app, create(product_client, scopes=['changes.read'])['access_token'])
    for title in ('PAT first change', 'PAT second change'):
        ConfigChange.create(server_id=product.server.server_id, group_id=1, user_id=product.admin.user_id,
            service='haproxy', action='reload', status='draft', title=title, requires_approval=0,
            remote_path='/etc/haproxy/haproxy.cfg', draft_path=str(product.root/title),
            rollback_path=str(product.root/(title+'.old')), drift_status='in_sync')
    original_list = api_routes.change_sql.list_changes
    def listing(*args, **kwargs):
        stream = iter(original_list(*args, **kwargs))
        first = next(stream)
        errors = []
        def writer():
            try:
                with sqlite3.connect(product.db.database, timeout=3) as database:
                    database.execute('UPDATE user SET last_login_ip=? WHERE id=?',
                                     ('192.0.2.99', product.admin.user_id))
            except Exception as error:
                errors.append(type(error).__name__)
        thread = threading.Thread(target=writer)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive() and not errors
        return itertools.chain([first], stream)
    monkeypatch.setattr(api_routes.change_sql, 'list_changes', listing)
    response = remote.get('/api/changes')
    assert response.status_code == 200, response.get_json()
    assert len(response.get_json()['data']) == 2
