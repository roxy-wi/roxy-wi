from datetime import timedelta
import hashlib
import importlib
import json

import pytest

from app.modules.api_tokens import service
from app.modules.api_tokens.scopes import ENDPOINTS
from app.modules.common.time import utc_now
from app.modules.db import db_model as m

URL = '/user/personal-tokens'


def body(**changes):
    return {'name': 'Deployment integration', 'group_id': 1, 'scopes': ['inventory.read'],
            'expires_days': 90, 'password': 'TestBootstrapPassword!', **changes}


def create(client, **changes):
    result = client.post(URL, json=body(**changes))
    assert result.status_code == 201, result.text
    return result.json


def api(app, token):
    client = app.test_client()
    client.environ_base['HTTP_AUTHORIZATION'] = 'Bearer '+token
    client.environ_base['HTTP_ACCEPT'] = 'application/json'
    return client


def test_credential_is_shown_once_hash_only_and_immediately_revocable(product_client, product, app):
    created = create(product_client)
    token, token_id = created['access_token'], created['token']['id']
    row = m.PersonalAccessToken.get_by_id(token_id)
    assert row.token_digest == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(row.__data__)
    listed = product_client.get(URL)
    assert listed.headers['Cache-Control'] == 'no-store'
    assert token not in listed.text and 'token_digest' not in listed.text and 'password_version' not in listed.text
    remote = api(app, token)
    response = remote.get('/api/servers')
    assert response.status_code == 200, response.text
    assert {server['server_id'] for server in response.json} == {product.server.server_id}
    used = m.PersonalAccessToken.get_by_id(token_id).last_used_at
    assert used is not None
    remote.get('/api/servers')
    assert m.PersonalAccessToken.get_by_id(token_id).last_used_at == used
    assert product_client.delete(f'{URL}/{token_id}').status_code == 200
    assert remote.get('/api/servers').status_code in {401, 422}


def test_fixed_group_survives_web_group_switch_without_changing_user(product_client, product, app):
    token = create(product_client)['access_token']
    m.UserGroups.create(user_id=product.admin.user_id, user_group_id=2, user_role_id=1)
    m.User.update(group_id='2').where(m.User.user_id == product.admin.user_id).execute()
    response = api(app, token).get('/api/servers')
    assert response.status_code == 200, response.text
    assert {server['server_id'] for server in response.json} == {product.server.server_id}
    assert m.User.get_by_id(product.admin.user_id).group_id == '2'
    assert api(app, token).get('/api/servers?group_id=2').status_code in {401, 403}
    assert api(app, token).get('/api/servers?group_id=1&group_id=2').status_code in {401, 403}
    assert api(app, token).get(f'/api/server/{product.other.server_id}').status_code in {401, 403}


@pytest.mark.parametrize('path', ['/admin', '/user/personal-tokens', '/user/api-access', '/overview'])
def test_personal_token_cannot_authenticate_web_or_manage_tokens(product_client, product, app, path):
    token = create(product_client)['access_token']
    assert api(app, token).get(path).status_code in {401, 403}


def test_cookie_token_and_ambiguous_header_cookie_identity_are_rejected(product_client, product, app):
    token = create(product_client)['access_token']
    cookie = app.test_client()
    cookie.set_cookie('access_token_cookie', token)
    assert cookie.get('/api/servers').status_code in {401, 422}
    product_client.environ_base['HTTP_AUTHORIZATION'] = 'Bearer '+token
    assert product_client.get(URL).status_code in {401, 403}


@pytest.mark.parametrize('operation', ['role', 'membership', 'disabled', 'password', 'ldap', 'expired'])
def test_authority_is_rechecked_from_database_on_every_request(product_client, product, app, operation):
    created = create(product_client)
    client = api(app, created['access_token'])
    assert client.get('/api/servers').status_code == 200
    if operation == 'role':
        m.UserGroups.update(user_role_id=4).where(m.UserGroups.user_id == product.admin.user_id).execute()
    elif operation == 'membership':
        m.UserGroups.delete().where(m.UserGroups.user_id == product.admin.user_id).execute()
    elif operation == 'disabled':
        m.User.update(enabled=0).where(m.User.user_id == product.admin.user_id).execute()
    elif operation == 'password':
        m.User.update(password='ChangedCredentialVersion').where(m.User.user_id == product.admin.user_id).execute()
    elif operation == 'ldap':
        m.User.update(ldap_user=1).where(m.User.user_id == product.admin.user_id).execute()
    else:
        m.PersonalAccessToken.update(expires_at=utc_now()-timedelta(seconds=1)).execute()
    assert client.get('/api/servers').status_code in {401, 403, 422}


def test_scope_map_denies_unmapped_and_mutating_endpoints_before_execution(product_client, product, app):
    remote = api(app, create(product_client)['access_token'])
    for method, path in [('post', '/api/server'), ('get', '/api/server/creds'),
                         ('post', '/api/service/haproxy/11/restart'), ('post', '/api/changes'),
                         ('post', '/api/changes/1/deploy')]:
        assert getattr(remote, method)(path, json={}).status_code in {401, 403}, path
    assert remote.post('/api/login', json={}).status_code == 400
    assert m.Server.select().count() == 2
    assert m.InstallationTasks.select().count() == 0
    # Every allowed route must exist with the exact method; future routes stay denied.
    for (endpoint, method) in ENDPOINTS:
        assert any(rule.endpoint == endpoint and method in rule.methods for rule in app.url_map.iter_rules()), endpoint


def test_service_permission_and_subscription_are_not_bypassed(product_client, product, app, monkeypatch):
    token = create(product_client, scopes=['services.read'])['access_token']
    remote = api(app, token)
    m.User.update(user_services='').where(m.User.user_id == product.admin.user_id).execute()
    assert remote.get('/api/service/haproxy/11/status').status_code in {401, 403}
    monkeypatch.setattr('app.modules.roxywi.common.return_user_subscription',
                        lambda: {'user_status': 0, 'user_plan': 'user'})
    assert remote.get('/api/operations/1').status_code == 401


def test_reauthentication_throttle_is_shared_and_reset_is_bounded(product_client, product):
    for _ in range(5):
        assert product_client.post(URL, json=body(password='WrongSyntheticPassword')).status_code == 403
    refused = product_client.post(URL, json=body())
    assert refused.status_code == 403 and 'five minutes' in refused.text
    assert m.PersonalAccessToken.select().count() == 0
    m.PersonalTokenGate.update(window_started_at=utc_now()-timedelta(minutes=6)).execute()
    assert product_client.post(URL, json=body()).status_code == 201
    assert m.PersonalTokenGate.get_by_id(product.admin.user_id).attempts == 0


def test_token_metadata_is_owner_only_and_creation_requires_membership(product_client, product):
    created = create(product_client)
    other = m.User.create(username='other-token-user', email='other-token@example.test', password='hash', role_id='1', group_id='2')
    m.PersonalAccessToken.update(user_id=other.user_id).where(m.PersonalAccessToken.id == created['token']['id']).execute()
    assert product_client.get(URL).json['tokens'] == []
    assert product_client.delete(URL+'/'+created['token']['id']).status_code == 404
    assert product_client.post(URL, json=body(group_id=2)).status_code == 403


@pytest.mark.parametrize('changes', [{'expires_days': 0}, {'expires_days': 366}, {'expires_days': True},
                                     {'scopes': ['*']}, {'scopes': []}, {'group_id': True},
                                     {'user_id': 999}, {'name': ' '}, {'scopes': ['settings.write']}])
def test_invalid_requests_do_not_leak_password_or_create_tokens(product_client, product, changes):
    result = product_client.post(URL, json=body(**changes))
    assert result.status_code == 400
    assert 'TestBootstrapPassword!' not in result.text
    assert m.PersonalAccessToken.select().count() == 0


@pytest.mark.parametrize('locale', ['en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'])
def test_token_page_is_available_for_locales_and_has_no_store(product_client, product, locale):
    product_client.set_cookie('lang', locale)
    result = product_client.get('/user/api-access')
    assert result.status_code == 200, result.text
    assert result.headers['Cache-Control'] == 'no-store'


def test_token_schema_upgrade_is_idempotent_and_refuses_destructive_rollback(product):
    migration = importlib.import_module('app.modules.db.migrations.20261029030000_personal_access_tokens')
    migration.up()
    migration.up()
    with pytest.raises(RuntimeError, match='Revoke and preserve'):
        migration.down()


def test_control_permission_reaches_service_handler_but_read_token_cannot(product_client, product, app, monkeypatch):
    calls = []
    monkeypatch.setattr('app.modules.service.action.common_action', lambda *args: calls.append(args))
    reader = api(app, create(product_client, scopes=['services.read'])['access_token'])
    controller = api(app, create(product_client, scopes=['services.control'])['access_token'])
    path = f'/api/service/haproxy/{product.server.server_id}/reload'
    assert reader.post(path).status_code in {401, 403}
    assert calls == []
    assert controller.post(path).status_code == 200
    assert calls == [(product.server.ip, 'reload', 'haproxy')]
    m.UserGroups.update(user_role_id=4).where(m.UserGroups.user_id == product.admin.user_id).execute()
    assert controller.post(path).status_code == 403
    assert len(calls) == 1


def change(product, **changes):
    return m.ConfigChange.create(**{'server_id': product.server.server_id, 'group_id': 1,
        'user_id': product.admin.user_id, 'service': 'haproxy', 'action': 'reload',
        'status': 'pending_approval', 'title': 'Review me', 'remote_path': '/etc/haproxy/haproxy.cfg',
        'draft_path': 'synthetic-draft', 'rollback_path': 'synthetic-before', 'requires_approval': 1, **changes})


def test_two_tokens_of_same_author_cannot_bypass_distinct_approval(product_client, product, app):
    draft = change(product)
    approver = api(app, create(product_client, scopes=['changes.approve'])['access_token'])
    result = approver.post(f'/api/changes/{draft.id}/approve')
    assert result.status_code == 403 and 'author cannot approve' in result.text
    assert m.ConfigChange.get_by_id(draft.id).status == 'pending_approval'


def test_pinned_group_rejects_cross_group_rollout_target_and_service_revocation(product_client, product, app):
    draft = change(product)
    m.ConfigChangeTarget.create(change=draft, server_id=product.other.server_id,
                                server_ip=product.other.ip, server_name='Other target',
                                role='slave', position=0, status='draft', rollback_path='synthetic-other-before')
    deployer = api(app, create(product_client, scopes=['changes.deploy'])['access_token'])
    assert deployer.post(f'/api/changes/{draft.id}/deploy').status_code in {401, 403}
    assert m.InstallationTasks.select().count() == 0
    m.ConfigChangeTarget.delete().execute()
    m.User.update(user_services='').where(m.User.user_id == product.admin.user_id).execute()
    assert deployer.post(f'/api/changes/{draft.id}/deploy').status_code in {401, 403}


def test_optional_mfa_provider_is_required_for_issuance_and_epoch_revokes_tokens(product_client, product, app, monkeypatch):
    from types import SimpleNamespace
    state = {'epoch': 1, 'proof': False}
    def verify(user, data, purpose):
        from app.modules.roxywi.exception import RoxywiPermissionError
        assert purpose == 'personal_token.create'
        if not state['proof']:
            raise RoxywiPermissionError('Second factor required')
    monkeypatch.setattr(service, 'security_provider', lambda: SimpleNamespace(
        require_sensitive_action=verify, user_epoch=lambda user_id: state['epoch'],
        session_user=lambda claims: m.User.get_by_id(claims['user_id'])))
    assert product_client.post(URL, json=body()).status_code == 403
    state['proof'] = True
    token = create(product_client)['access_token']
    assert api(app, token).get('/api/servers').status_code == 200
    state['epoch'] += 1
    assert api(app, token).get('/api/servers').status_code in {401, 422}


@pytest.mark.parametrize('changed', ['epoch', 'password'])
def test_security_reset_during_sensitive_proof_cannot_issue_fresh_token(product_client, product, monkeypatch, changed):
    from types import SimpleNamespace
    state = {'epoch': 1}
    def verify(user, data, purpose):
        if changed == 'epoch':
            state['epoch'] += 1
        else:
            m.User.update(password='ResetDuringProof').where(m.User.user_id == user.user_id).execute()
    monkeypatch.setattr(service, 'security_provider', lambda: SimpleNamespace(
        require_sensitive_action=verify, user_epoch=lambda user_id: state['epoch'],
        session_user=lambda claims: m.User.get_by_id(claims['user_id'])))
    result = product_client.post(URL, json=body())
    assert result.status_code == 403 and 'changed during authentication' in result.text
    assert m.PersonalAccessToken.select().count() == 0


def test_legacy_password_upgrade_keeps_new_token_bound_to_current_hash(product_client, product, app):
    from app.modules.roxy_wi_tools import Tools
    # Frozen historical DB row, shared with the legacy rehash race scenarios.
    # New passwords use scrypt; tests do not generate new weak password hashes.
    legacy = 'e1846d46d83f9c9fb336fc834f407925'
    password = 'LegacyVerifiedPassword!'
    m.User.update(password=legacy).where(m.User.user_id == product.admin.user_id).execute()
    logged_in = product_client.post('/login', json={'login': 'admin', 'pass': password})
    assert logged_in.status_code == 200, logged_in.text
    product_client.environ_base['HTTP_X_CSRF_TOKEN'] = product_client.get_cookie('csrf_access_token').value
    created = create(product_client, password=password)
    user = m.User.get_by_id(product.admin.user_id)
    assert user.password != legacy
    assert Tools.check_password(password, user.password) == (True, False)
    assert m.PersonalAccessToken.get_by_id(created['token']['id']).password_version == service.password_version(user)
    assert api(app, created['access_token']).get('/api/servers').status_code == 200


def test_password_reset_during_password_proof_does_not_bind_old_proof_to_new_hash(product_client, product, monkeypatch):
    def accepted_old_password(login, password):
        m.User.update(password='ResetDuringPasswordProof').where(m.User.user_id == product.admin.user_id).execute()
    monkeypatch.setattr('app.modules.roxywi.auth.check_user_password', accepted_old_password)
    result = product_client.post(URL, json=body())
    assert result.status_code == 403 and 'changed during authentication' in result.text
    assert m.PersonalAccessToken.select().count() == 0


def test_legacy_header_token_cannot_be_combined_with_cookie_to_manage_tokens(product_client, product, app):
    response = app.test_client().post('/api/login', json=dict(login='admin', password='TestBootstrapPassword!'))
    assert response.status_code == 200
    product_client.environ_base['HTTP_AUTHORIZATION'] = 'Bearer '+response.json['access_token']
    assert product_client.get(URL).status_code == 403


def test_csrf_is_required_for_cookie_token_issuance_and_revocation(product_client, product):
    created = create(product_client)
    product_client.environ_base.pop('HTTP_X_CSRF_TOKEN')
    assert product_client.post(URL, json=body()).status_code == 401
    assert product_client.delete(URL+'/'+created['token']['id']).status_code == 401
    assert m.PersonalAccessToken.get_by_id(created['token']['id']).revoked_at is None


def test_retention_only_removes_old_inactive_metadata_and_missing_rows_stay_denied(product_client, product, app):
    created = create(product_client)
    assert service.purge_metadata() == 0
    m.PersonalAccessToken.update(revoked_at=utc_now()-timedelta(days=91)).execute()
    assert service.purge_metadata() == 1
    assert api(app, created['access_token']).get('/api/servers').status_code in {401, 422}


def test_a_different_signed_jwt_cannot_reuse_a_token_metadata_id(product_client, product, app):
    from flask_jwt_extended import decode_token, create_access_token
    created = create(product_client)
    with app.app_context():
        claims = decode_token(created['access_token'])
        impostor = create_access_token(str(product.admin.user_id), additional_claims={
            'credential_type': 'pat', 'group': '1', 'pat_id': created['token']['id'], 'nonce': claims['nonce']})
    assert api(app, impostor).get('/api/servers').status_code in {401, 422}


def test_audit_write_failure_rolls_back_token_creation_and_revocation(product_client, product, monkeypatch):
    created = create(product_client)
    def fail(*args):
        raise service.CredentialWriteUnavailable('Audit storage unavailable; credential was not changed')
    monkeypatch.setattr(service, 'audit_credential', fail)
    assert product_client.post(URL, json=body()).status_code == 503
    assert m.PersonalAccessToken.select().count() == 1
    assert product_client.delete(URL+'/'+created['token']['id']).status_code == 503
    assert m.PersonalAccessToken.get_by_id(created['token']['id']).revoked_at is None


def test_metadata_marks_invalidated_owner_credentials_unavailable(product_client, product):
    created = create(product_client)
    assert created['token']['available'] is True
    m.User.update(password='NewCredentialHash').where(m.User.user_id == product.admin.user_id).execute()
    listed = product_client.get(URL)
    assert listed.status_code == 200
    assert listed.json['tokens'][0]['available'] is False


@pytest.mark.parametrize('operation', ['create', 'preview', 'edit', 'deploy'])
def test_implicit_rollout_topology_cannot_escape_token_group(product_client, product, app, monkeypatch, operation):
    m.Server.update(master=product.server.server_id).where(m.Server.server_id == product.other.server_id).execute()
    remote_reads = []
    monkeypatch.setattr('app.modules.config.config.get_config', lambda *args, **kwargs: remote_reads.append(args))
    scope = 'changes.read' if operation == 'preview' else 'changes.deploy' if operation == 'deploy' else 'changes.write'
    remote = api(app, create(product_client, scopes=[scope])['access_token'])
    if operation == 'create':
        result = remote.post('/api/changes', json={'server_id': product.server.server_id, 'service': 'haproxy',
            'config': 'global\n', 'title': 'Fixed group only'})
    elif operation == 'preview':
        result = remote.get(f'/api/changes/rollout-preview?server_id={product.server.server_id}&service=haproxy')
    else:
        draft = change(product, status='draft')
        if operation == 'edit':
            result = remote.put(f'/api/changes/{draft.id}', json={'batch_size': 1})
        else:
            result = remote.post(f'/api/changes/{draft.id}/deploy')
        assert m.ConfigChange.get_by_id(draft.id).status == 'draft'
    assert result.status_code in {401, 403}, result.text
    assert remote_reads == []
    assert m.InstallationTasks.select().count() == 0
    if operation == 'preview':
        m.Server.update(group_id='1').where(m.Server.server_id == product.other.server_id).execute()
        allowed = remote.get(f'/api/changes/rollout-preview?server_id={product.server.server_id}&service=haproxy')
        assert allowed.status_code == 200, allowed.text
        assert {item['server_id'] for item in allowed.json['data']} == {11, 22}


def test_shared_reauthentication_gate_serializes_concurrent_workers(product):
    from concurrent.futures import ThreadPoolExecutor
    from app.modules.roxywi.exception import RoxywiPermissionError
    def attempt(_):
        try:
            service.sensitive_attempt(product.admin.user_id)
            return True
        except RoxywiPermissionError:
            return False
        finally:
            product.db.close()
    with ThreadPoolExecutor(max_workers=8) as workers:
        accepted = list(workers.map(attempt, range(8)))
    assert sum(accepted) == 5
    assert m.PersonalTokenGate.get_by_id(product.admin.user_id).attempts == 5


def test_deleted_owner_token_and_gate_cannot_authenticate_reused_account_id(product_client, product, app):
    created = create(product_client)
    user_id = product.admin.user_id
    old_hash = m.User.get_by_id(user_id).password
    assert m.PersonalTokenGate.get_by_id(user_id)
    m.User.delete().where(m.User.user_id == user_id).execute()
    assert m.PersonalAccessToken.select().count() == 0
    assert m.PersonalTokenGate.select().count() == 0
    replacement = m.User.create(user_id=user_id, username='replacement-admin',
        email='replacement-admin@example.test', password=old_hash, role_id='1', group_id='1')
    assert replacement.user_id == user_id
    # Even a deliberately cloned password hash and surviving group rows cannot
    # transfer the previous account's personal credential to its replacement.
    assert api(app, created['access_token']).get('/api/servers').status_code in {401, 422}


def test_deleted_group_token_cannot_transfer_to_recreated_group_namespace(product_client, product, app):
    m.UserGroups.create(user_id=product.admin.user_id, user_group_id=2, user_role_id=1)
    created = create(product_client, group_id=2)
    remote = api(app, created['access_token'])
    assert remote.get('/api/servers').status_code == 200
    m.Groups.delete().where(m.Groups.group_id == 2).execute()
    assert m.PersonalAccessToken.select().count() == 0
    m.Groups.create(group_id=2, name='Replacement group')
    assert remote.get('/api/servers').status_code in {401, 422}
    assert product_client.get(URL).json['tokens'] == []


def test_replaced_account_during_accepted_proof_cannot_inherit_token_creation(product_client, product, monkeypatch):
    user_id = product.admin.user_id
    password_hash = m.User.get_by_id(user_id).password
    def old_proof(login, password):
        m.User.delete().where(m.User.user_id == user_id).execute()
        m.User.create(user_id=user_id, username='replacement-user', email='replacement-proof@example.test',
                      password=password_hash, role_id='1', group_id='1')
    monkeypatch.setattr('app.modules.roxywi.auth.check_user_password', old_proof)
    result = product_client.post(URL, json=body())
    assert result.status_code == 403 and 'changed during authentication' in result.text
    assert m.PersonalAccessToken.select().count() == 0


def test_reset_after_jwt_signing_still_cannot_commit_a_personal_credential(product_client, product, monkeypatch):
    original = service.create_access_token
    def reset_after_signing(*args, **kwargs):
        token = original(*args, **kwargs)
        m.User.update(password='ResetImmediatelyBeforeCommit').where(m.User.user_id == product.admin.user_id).execute()
        return token
    monkeypatch.setattr(service, 'create_access_token', reset_after_signing)
    result = product_client.post(URL, json=body())
    assert result.status_code == 403 and 'changed during authentication' in result.text
    assert m.PersonalAccessToken.select().count() == 0


def test_password_change_marker_is_keyed_and_independent_of_fernet(app, product, monkeypatch):
    user = product.admin
    original = service.password_version(user)
    assert len(original) == 64 and all(c in '0123456789abcdef' for c in original)
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE', 'unrelated-encryption-key-rotation')
    assert service.password_version(user) == original
    monkeypatch.setitem(app.config, 'SECRET_KEY', 'a-different-application-key-for-this-test')
    assert service.password_version(user) != original
