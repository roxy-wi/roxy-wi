import importlib
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.modules.audit import events, destinations, delivery, domain
from app.modules.common.time import utc_now
from app.modules.db import db_model as m
from app.modules.roxywi.exception import RoxywiConflictError

URL = '/admin/audit-receivers'


def body(**changes):
    return {'name': 'Central audit', 'group_id': 1, 'enabled': True, 'events': ['*'],
            'connection': dict(transport='https', url='https://audit.example.test/events',
                               auth='bearer', secrets=dict(token='SyntheticPrivateToken!')), **changes}


def receiver(product, **changes):
    return destinations.save(body(**changes), group_id=1, role=1, actor_id=product.admin.user_id)


def test_receiver_api_versions_encrypted_credentials_and_group_authority(product_client, product):
    response = product_client.post(URL, json=body())
    assert response.status_code == 201, response.text
    assert response.headers['Cache-Control'] == 'no-store'
    saved = response.json
    assert saved['configured']['token'] and 'SyntheticPrivateToken' not in response.text
    first = destinations.revision(m.AuditDestination.get_by_id(saved['id']))
    assert 'SyntheticPrivateToken' not in first.credentials_encrypted
    assert destinations.resolve_revision(first).credentials['token'] == 'SyntheticPrivateToken!'
    updated = body(revision=1)
    updated['connection']['secrets'] = {}
    result = product_client.put(f'{URL}/{saved["id"]}', json=updated)
    assert result.status_code == 200 and result.json['revision'] == 2
    assert product_client.put(f'{URL}/{saved["id"]}', json=updated).status_code == 409
    assert destinations.resolve_revision(first).revision == 1
    other = receiver(product, group_id=2, name='Other group')
    m.UserGroups.update(user_role_id=2).where(m.UserGroups.user_id == product.admin.user_id).execute()
    assert other['id'] not in [r['id'] for r in product_client.get(URL).json['receivers']]
    assert product_client.put(f'{URL}/{other["id"]}', json=body(revision=1)).status_code == 404
    assert product_client.post(f'{URL}/{other["id"]}/test', json={}).status_code == 404
    assert product_client.post(f'{URL}/{other["id"]}/retry', json={'revision': 1, 'include_pending': True}).status_code == 404
    other_revisions = {row.id for row in m.AuditDestinationRevision.select().where(
        m.AuditDestinationRevision.destination_id == other['id'])}
    status = product_client.get('/admin/audit-status')
    assert status.status_code == 200
    assert not any(row['receiver_revision_id'] in other_revisions for row in status.json['deliveries'])
    assert product_client.post(URL, json=body(group_id=0, name='Shared')).status_code == 403
    m.UserGroups.update(user_role_id=4).where(m.UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.get(URL).status_code == 403


def test_explicit_payload_filters_secret_redaction_and_pinned_revision(product):
    saved = receiver(product, events=['change.applied'])
    before = m.AuditDelivery.select().count()
    event_id = events.record('change.applied', 'succeeded', user_id=product.admin.user_id,
                             group_id=1, source_ip='127.0.0.1', details=dict(
                                 change_id=11, status='applied', password='DO_NOT_EXPORT',
                                 config='PRIVATE_CONFIG', exception='PRIVATE_EXCEPTION'))
    assert m.AuditDelivery.select().count() == before + 1
    payload = json.loads(m.AuditEvent.get_by_id(event_id).payload)
    assert payload['details'] == dict(change_id=11, status='applied')
    assert payload['actor_name'] == 'admin'
    assert 'PRIVATE' not in json.dumps(payload)
    events.record('change.applied', 'succeeded', group_id=2)
    assert m.AuditDelivery.select().count() == before + 1
    row = m.AuditDelivery.get(m.AuditDelivery.event_id == event_id)
    old_revision = row.destination_revision_id
    changed = body(revision=1, enabled=False)
    destinations.save(changed, group_id=1, role=1, actor_id=product.admin.user_id, destination_id=saved['id'])
    assert m.AuditDelivery.get_by_id(row.id).destination_revision_id == old_revision
    assert not events.enabled()
    # Configuration disable is still exported to the old receiver revision.
    assert m.AuditDelivery.select().where(m.AuditDelivery.destination_revision_id == old_revision).count() >= 2


def test_bounded_retry_restart_stale_worker_and_retention(product, monkeypatch):
    receiver(product)
    sent = []
    monkeypatch.setattr(delivery, 'send', lambda *_: (_ for _ in ()).throw(OSError('PRIVATE_ERROR')))
    assert delivery.process(limit=1) == 1
    row = m.AuditDelivery.select().first()
    assert row.status == 'pending' and row.attempts == 1
    assert row.last_error == 'Connection or TLS delivery failed'
    assert row.retry_at > utc_now()
    m.AuditDelivery.update(retry_at=utc_now()-timedelta(seconds=1)).execute()
    first = delivery.claim()
    assert first.status == 'sending'
    m.AuditDelivery.update(claim_expires_at=utc_now()-timedelta(seconds=1)).execute()
    second = delivery.claim()
    assert second.claim_token != first.claim_token
    assert not delivery._finish(first, 'transport_handoff')
    assert delivery._finish(second, 'transport_handoff')
    monkeypatch.setattr(delivery, 'send', lambda connection, payload: sent.append(payload['id']) or 'receiver_accepted')
    event_id = events.record('auth.login', 'failed', group_id=1)
    assert delivery.process() == 1 and sent == [event_id]
    pending = events.record('change.requested', 'requested', group_id=1)
    m.AuditEvent.update(created_at=utc_now()-timedelta(days=40)).execute()
    assert events.prune() == 2
    assert m.AuditEvent.get_by_id(pending)
    assert m.AuditState.get_by_id(1).records == 1


def test_quota_reserve_stops_mutations_but_allows_audited_receiver_repair(product_client, product, monkeypatch):
    receiver(product)
    monkeypatch.setenv('ROXYWI_AUDIT_MAX_EVENTS', '100')
    m.AuditState.update(records=100).execute()
    with pytest.raises(events.AuditStorageUnavailable):
        events.record('change.requested', 'requested', group_id=1)
    response = product_client.post('/admin/audit-receivers/1/retry', json={'revision': 1})
    assert response.status_code == 200
    assert m.AuditState.get_by_id(1).records == 101
    # A normal mutating route is blocked before its body executes.
    response = product_client.post('/api/server/11/maintenance', json={})
    assert response.status_code == 503
    assert 'not started' in response.text
    assert m.AuditState.get_by_id(1).records == 101


def test_failed_delivery_rebind_handles_duplicate_current_uuid(product):
    saved = receiver(product)
    first = destinations.revision(m.AuditDestination.get_by_id(saved['id']))
    destinations.save(body(revision=1), group_id=1, role=1, actor_id=product.admin.user_id,
                      destination_id=saved['id'])
    current = destinations.revision(m.AuditDestination.get_by_id(saved['id']))
    event_id = m.AuditEvent.select().order_by(m.AuditEvent.created_at.desc()).first().event_id
    assert m.AuditDelivery.select().where(m.AuditDelivery.event_id == event_id).count() == 2
    m.AuditDelivery.update(status='failed').execute()
    assert destinations.retry_failed(saved['id'], group_id=1, role=1, actor_id=product.admin.user_id,
                                     expected_revision=2) == 3
    rows = list(m.AuditDelivery.select().where(m.AuditDelivery.event_id == event_id))
    assert len(rows) == 1 and rows[0].destination_revision_id == current.id
    assert rows[0].status == 'pending'
    with pytest.raises(RoxywiConflictError):
        destinations.retry_failed(saved['id'], group_id=1, role=1, actor_id=product.admin.user_id,
                                  expected_revision=1)


def test_domain_result_tracks_foreign_keys_and_safe_digests(product, monkeypatch):
    receiver(product)
    task = m.InstallationTasks.create(service_name='HAProxy', user_id=product.admin.user_id,
                                      group_id=1, operation_id='audit-task', operation_type='ansible', status='running')
    context = domain.operation_started(task)
    task.status = 'completed'
    domain.operation_finished(task, context, False)
    payload = json.loads(m.AuditEvent.select().where(m.AuditEvent.event_type == 'operation.finished').get().payload)
    assert payload['actor_id'] == product.admin.user_id and payload['group_id'] == 1
    assert payload['outcome'] == 'succeeded'
    folder = product.root/'configs'
    snapshots = folder/'changes'
    snapshots.mkdir(parents=True)
    before, after = snapshots/'before.cfg', snapshots/'draft.cfg'
    before.write_text('SECRET old config')
    after.write_text('SECRET new config')
    monkeypatch.setattr('app.modules.config.common.get_config_dir', lambda _: str(folder))
    change = SimpleNamespace(id=33, service='haproxy', status='deployed', group_id=1,
                             user_id=product.admin.user_id, rollback_path=str(before), draft_path=str(after))
    domain.change_event(change, SimpleNamespace(event_type='applied', status='deployed', actor_id=None))
    payload = json.loads(m.AuditEvent.select().where(m.AuditEvent.event_type == 'change.applied').get().payload)
    assert payload['outcome'] == 'succeeded'
    assert len(payload['details']['before_digest']) == 64
    assert payload['details']['before_digest'] != payload['details']['after_digest']
    assert 'SECRET' not in json.dumps(payload)
    assert domain._snapshot_digest(change, '/etc/passwd') is None
    domain.change_event(change, SimpleNamespace(event_type='rolled_back', status='rolled_back', actor_id=None))
    rollback = json.loads(m.AuditEvent.select().where(m.AuditEvent.event_type == 'change.rolled_back').get().payload)
    assert rollback['details']['after_digest'] == payload['details']['before_digest']
    assert rollback['details']['before_digest'] == payload['details']['after_digest']


@pytest.mark.parametrize('locale', ['en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'])
def test_audit_page_locales_and_status(product_client, product, locale):
    product_client.set_cookie('lang', locale)
    assert product_client.get('/admin/audit').status_code == 200
    receiver(product)
    status = product_client.get('/admin/audit-status')
    assert status.status_code == 200
    assert status.json['counts'] == {'pending': 1}
    assert 'SyntheticPrivateToken' not in status.text


def test_upgrade_is_idempotent_and_preserves_data(product):
    receiver(product)
    migration = importlib.import_module('app.modules.db.migrations.20261029020000_external_audit')
    migration.up()
    migration.up()
    assert m.AuditEvent.select().count() == 1
    with pytest.raises(RuntimeError, match='Preserve audit'):
        migration.down()


def test_parallel_writers_keep_event_outbox_and_counter_atomic(product):
    from concurrent.futures import ThreadPoolExecutor
    receiver(product)
    def write(index):
        try:
            return events.record('request.started', 'requested', group_id=1,
                                 details={'request_id': str(index)})
        finally:
            product.db.close()
    with ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(write, range(24)))
    assert len(set(ids)) == 24
    assert m.AuditState.get_by_id(1).records == 25
    assert m.AuditEvent.select().count() == m.AuditDelivery.select().count() == 25


def test_failed_outbox_insert_rolls_back_record_and_count(product, monkeypatch):
    receiver(product)
    before = m.AuditState.get_by_id(1).records
    monkeypatch.setattr(m.AuditDelivery, 'create', lambda **kw: (_ for _ in ()).throw(OSError('PRIVATE_DB_ERROR')))
    with pytest.raises(events.AuditStorageUnavailable, match='Audit storage unavailable'):
        events.record('request.started', 'requested', group_id=1)
    assert m.AuditEvent.select().count() == before
    assert m.AuditState.get_by_id(1).records == before


def test_login_results_never_include_submitted_identity_or_password(product_client, product):
    receiver(product, group_id=0)
    response = product_client.post('/login', json={'login': 'nonexistent-private-user', 'pass': 'PRIVATE_PASSWORD'})
    assert response.status_code in {200, 401}
    event = m.AuditEvent.select().where(m.AuditEvent.event_type == 'auth.login').get()
    assert event.outcome == 'failed'
    assert 'PRIVATE_PASSWORD' not in event.payload
    assert 'nonexistent-private-user' not in event.payload


@pytest.mark.parametrize('status', ['mfa_required', 'enrollment_required'])
def test_pending_local_auth_uses_bounded_login_reserve_without_identity(app, product, monkeypatch, status):
    from flask import jsonify
    receiver(product, group_id=0)
    monkeypatch.setenv('ROXYWI_AUDIT_MAX_EVENTS', '100')
    m.AuditState.update(records=100).where(m.AuditState.id == 1).execute()
    monkeypatch.setitem(app.view_functions, 'login_page', lambda: (jsonify(status=status), 202))
    response = app.test_client().post('/login', json={'login': 'PRIVATE_IDENTITY', 'pass': 'PRIVATE_PASSWORD'})
    assert response.status_code == 202
    event = m.AuditEvent.select().where(m.AuditEvent.event_type == 'auth.login').get()
    assert event.outcome == 'pending'
    assert m.AuditState.get_by_id(1).records == 101
    assert 'PRIVATE_IDENTITY' not in event.payload and 'PRIVATE_PASSWORD' not in event.payload


def test_rotation_preserves_all_pinned_receiver_revisions(product, monkeypatch):
    from cryptography.fernet import Fernet
    from rotate_credential_secret import rotate_credentials
    receiver(product)
    destinations.save(body(revision=1), group_id=1, role=1,
                      actor_id=product.admin.user_id, destination_id=1)
    new_key = Fernet.generate_key()
    old_key = __import__('os').environ['ROXYWI_SECRET_PHRASE']
    monkeypatch.setenv('ROXYWI_OLD_SECRET_PHRASE', old_key)
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE', new_key.decode())
    assert rotate_credentials() >= 2
    for row in m.AuditDestinationRevision.select():
        value = Fernet(new_key).decrypt(row.credentials_encrypted.removeprefix('fernet:').encode())
        assert json.loads(value)['token'] == 'SyntheticPrivateToken!'
    assert rotate_credentials() == 0


def test_shared_adapter_is_optional_and_does_not_accept_uninstalled_profile_ids(product_client, product):
    assert destinations.shared_profiles() is None
    data = body(profile_id=1)
    data.pop('connection')
    result = product_client.post(URL, json=data)
    assert result.status_code == 400
    assert m.AuditDestination.select().count() == 0


def test_receiver_checks_are_audited_without_claiming_udp_delivery(product_client, product, monkeypatch):
    saved = receiver(product)
    monkeypatch.setattr('app.routes.admin.audit_routes.check_connection',
                        lambda _: dict(status='rejected', http_status=403, detail='Receiver response'))
    result = product_client.post(f'{URL}/{saved["id"]}/test', json={})
    assert result.status_code == 200
    event = m.AuditEvent.select().where(m.AuditEvent.event_type == 'audit.receiver.checked').get()
    assert event.outcome == 'failed'
    monkeypatch.setattr('app.routes.admin.audit_routes.check_connection',
                        lambda _: dict(status='unverified', detail='UDP has no acknowledgement'))
    product_client.post(f'{URL}/{saved["id"]}/test', json={})
    assert m.AuditEvent.select().where((m.AuditEvent.event_type == 'audit.receiver.checked') &
                                      (m.AuditEvent.outcome == 'unknown')).exists()


def test_successful_login_can_use_repair_reserve_but_normal_mutations_cannot(product, app, monkeypatch):
    receiver(product)
    monkeypatch.setenv('ROXYWI_AUDIT_MAX_EVENTS', '100')
    m.AuditState.update(records=100).execute()
    fresh = app.test_client()
    result = fresh.post('/login', json=dict(login='admin', **{'pass': 'TestBootstrapPassword!'}))
    assert result.status_code == 200 and result.json['status'] == 'done'
    assert fresh.get_cookie('access_token_cookie')
    assert m.AuditState.get_by_id(1).records == 101
    fresh.environ_base['HTTP_X_CSRF_TOKEN'] = fresh.get_cookie('csrf_access_token').value
    refused = fresh.post('/api/server/11/maintenance', json={})
    assert refused.status_code == 503


def test_real_change_timeline_prefix_filters_and_validation_outcome(product):
    from app.modules.change import automation
    receiver(product, events=['change.validated'])
    change = m.ConfigChange.create(server_id=product.server.server_id, group_id=1,
        user_id=product.admin.user_id, service='haproxy', action='reload', status='pending_approval',
        title='Synthetic validation', remote_path='/etc/haproxy/haproxy.cfg',
        draft_path='not-a-managed-snapshot', rollback_path='not-a-managed-snapshot', requires_approval=1)
    event = automation.record_event(change.id, 'change.validated', 'Configuration validated', status='pending_approval')
    assert event is not None
    exported = m.AuditEvent.get(m.AuditEvent.event_type == 'change.validated')
    assert exported.outcome == 'succeeded'
    assert json.loads(exported.payload)['details']['status'] == 'pending_approval'
    assert m.AuditDelivery.select().where(m.AuditDelivery.event_id == exported.event_id).count() == 1
    assert not m.AuditEvent.select().where(m.AuditEvent.event_type == 'change.change.validated').exists()
    domain.change_event(change, SimpleNamespace(event_type='operation.queued', status='validated', actor_id=None))
    queued = m.AuditEvent.get(m.AuditEvent.event_type == 'change.operation.queued')
    assert queued.outcome == 'accepted'


def test_retargeting_cannot_forward_hidden_credentials_without_replacement(product_client, product):
    saved = receiver(product)
    original = destinations.revision(m.AuditDestination.get_by_id(saved['id']))
    changed = body(revision=1)
    changed['connection']['url'] = 'https://different.example.test/events'
    changed['connection']['secrets'] = {}
    refused = product_client.put(f'{URL}/{saved["id"]}', json=changed)
    assert refused.status_code == 400 and 'Re-enter or clear' in refused.text
    assert m.AuditDestination.get_by_id(saved['id']).revision == 1
    changed['connection']['secrets'] = {'token': 'ExplicitReplacementToken!'}
    accepted = product_client.put(f'{URL}/{saved["id"]}', json=changed)
    assert accepted.status_code == 200
    current = destinations.revision(m.AuditDestination.get_by_id(saved['id']))
    assert destinations.resolve_revision(current).credentials['token'] == 'ExplicitReplacementToken!'
    assert destinations.resolve_revision(original).credentials['token'] == 'SyntheticPrivateToken!'
    assert 'ExplicitReplacementToken!' not in accepted.text


def test_receiver_check_is_refused_before_network_if_intent_cannot_persist(product_client, product, monkeypatch):
    saved = receiver(product)
    calls = []
    monkeypatch.setattr('app.routes.admin.audit_routes.check_connection', lambda _: calls.append(True))
    monkeypatch.setenv('ROXYWI_AUDIT_MAX_EVENTS', '100')
    m.AuditState.update(records=200).execute()
    result = product_client.post(f'{URL}/{saved["id"]}/test', json={})
    assert result.status_code == 503
    assert calls == []


def test_receiver_check_reports_result_failure_after_network_without_claiming_rollback(product_client, product, monkeypatch):
    saved = receiver(product)
    calls = []
    def check(_):
        assert m.AuditEvent.select().where(m.AuditEvent.event_type == 'audit.receiver.check_requested').exists()
        calls.append(True)
        m.AuditState.update(records=200).execute()
        return dict(status='connected', detail='Connected')
    monkeypatch.setattr('app.routes.admin.audit_routes.check_connection', check)
    monkeypatch.setenv('ROXYWI_AUDIT_MAX_EVENTS', '100')
    result = product_client.post(f'{URL}/{saved["id"]}/test', json={})
    assert result.status_code == 503 and 'may have executed' in result.text
    assert calls == [True]


@pytest.mark.parametrize(('method', 'path', 'data'), [
    ('get', '/admin/audit', None), ('get', URL, None), ('get', '/admin/audit-status', None),
    ('post', URL, body()), ('put', URL+'/1', body(revision=1)),
    ('post', URL+'/1/test', {}), ('post', URL+'/1/retry', {'revision': 1}),
    ('delete', URL+'/1', {'revision': 1}),
])
def test_audit_admin_requires_unambiguous_cookie_session(product_client, product, app, method, path, data):
    receiver(product)
    token = product_client.get_cookie('access_token_cookie').value
    fresh = app.test_client()
    fresh.environ_base['HTTP_AUTHORIZATION'] = 'Bearer '+token
    assert getattr(fresh, method)(path, json=data).status_code in {401, 403}
    product_client.environ_base['HTTP_AUTHORIZATION'] = 'Bearer '+token
    assert getattr(product_client, method)(path, json=data).status_code == 403


@pytest.mark.parametrize(('method', 'path', 'data'), [
    ('post', URL, body(name='CSRF forbidden')), ('put', URL+'/1', body(revision=1)),
    ('post', URL+'/1/test', {}), ('post', URL+'/1/retry', {'revision': 1}),
    ('delete', URL+'/1', {'revision': 1}),
])
def test_audit_admin_mutations_require_cookie_csrf(product_client, product, method, path, data):
    receiver(product)
    product_client.environ_base.pop('HTTP_X_CSRF_TOKEN')
    assert getattr(product_client, method)(path, json=data).status_code == 401
    assert m.AuditDestination.select().count() == 1
    assert m.AuditDestination.get_by_id(1).revision == 1
    assert m.AuditEvent.select().count() == 1


def test_http_intent_precedes_side_effect_and_result_failure_is_explicit(product_client, product, monkeypatch):
    receiver(product)
    monkeypatch.setenv('ROXYWI_AUDIT_MAX_EVENTS', '100')
    calls = []
    def execute(*args):
        started = m.AuditEvent.get(m.AuditEvent.event_type == 'request.started')
        assert json.loads(started.payload)['details']['route'] == '/api/service/<any(haproxy, nginx, apache, keepalived):service>/<int:server_id>/<any(start, stop, reload, restart):action>'
        calls.append(args)
        m.AuditState.update(records=200).execute()
    monkeypatch.setattr('app.modules.service.action.common_action', execute)
    result = product_client.post(f'/api/service/haproxy/{product.server.server_id}/reload', json={'password': 'PRIVATE_BODY'})
    assert calls == [(product.server.ip, 'reload', 'haproxy')]
    assert result.status_code == 503 and 'may have completed' in result.text
    assert 'PRIVATE_BODY' not in ''.join(row.payload for row in m.AuditEvent.select())
    assert not m.AuditEvent.select().where(m.AuditEvent.event_type == 'request.finished').exists()


def test_concurrent_delivery_claims_assign_each_uuid_only_once(product):
    from concurrent.futures import ThreadPoolExecutor
    receiver(product)
    for index in range(24):
        events.record('request.started', 'requested', group_id=1, details={'request_id': str(index)})
    def claim(_):
        try:
            row = delivery.claim()
            return (row.id, row.event_id) if row else None
        finally:
            product.db.close()
    with ThreadPoolExecutor(max_workers=6) as workers:
        claimed = [row for row in workers.map(claim, range(40)) if row]
    assert len(claimed) == len(set(claimed)) == 25
    assert len({row[1] for row in claimed}) == 25
    assert m.AuditDelivery.select().where((m.AuditDelivery.status == 'sending') &
                                        (m.AuditDelivery.attempts == 1)).count() == 25


def test_login_result_storage_failure_returns_valid_error_without_issuing_cookie(product, app, monkeypatch):
    receiver(product)
    monkeypatch.setenv('ROXYWI_AUDIT_MAX_EVENTS', '100')
    m.AuditState.update(records=200).execute()
    fresh = app.test_client()
    result = fresh.post('/login', json=dict(login='admin', **{'pass': 'TestBootstrapPassword!'}))
    assert result.status_code == 503 and 'sign in again' in result.json['error']
    assert fresh.get_cookie('access_token_cookie') is None
    assert 'access_token' not in result.json


def test_already_executed_change_result_can_use_reserved_quota(product, monkeypatch):
    from app.modules.change import automation
    receiver(product, events=['change.validated'])
    monkeypatch.setenv('ROXYWI_AUDIT_MAX_EVENTS', '100')
    m.AuditState.update(records=100).execute()
    change = m.ConfigChange.create(server_id=product.server.server_id, group_id=1,
        user_id=product.admin.user_id, service='haproxy', action='reload', status='pending_approval',
        title='Synthetic validation result', remote_path='/etc/haproxy/haproxy.cfg',
        draft_path='not-a-managed-snapshot', rollback_path='not-a-managed-snapshot', requires_approval=1)
    assert automation.record_event(change.id, 'change.validated', 'Validated', status='pending_approval')
    exported = m.AuditEvent.get(m.AuditEvent.event_type == 'change.validated')
    assert exported.outcome == 'succeeded'
    assert m.AuditState.get_by_id(1).records == 101
    assert m.AuditDelivery.select().where(m.AuditDelivery.event_id == exported.event_id).count() == 1


def test_explicit_pending_requeue_uses_current_revision_and_preserves_inflight_and_terminal(product):
    saved = receiver(product)
    first = destinations.revision(m.AuditDestination.get_by_id(saved['id']))
    ids = {key: events.record('request.started', 'requested', group_id=1)
           for key in ['pending', 'sending', 'terminal', 'duplicate_sending', 'duplicate_pending']}
    m.AuditDelivery.update(status='sending', claim_token='original-inflight',
        claim_expires_at=utc_now()+timedelta(minutes=1)).where(m.AuditDelivery.event_id == ids['sending']).execute()
    m.AuditDelivery.update(status='receiver_accepted').where(m.AuditDelivery.event_id == ids['terminal']).execute()
    destinations.save(body(revision=1), group_id=1, role=1, actor_id=product.admin.user_id, destination_id=saved['id'])
    current = destinations.revision(m.AuditDestination.get_by_id(saved['id']))
    sending = m.AuditDelivery.create(event_id=ids['duplicate_sending'], destination_revision_id=current.id,
        status='sending', claim_token='current-inflight', claim_expires_at=utc_now()+timedelta(minutes=1))
    pending = m.AuditDelivery.create(event_id=ids['duplicate_pending'], destination_revision_id=current.id,
        status='pending', retry_at=utc_now()+timedelta(hours=1))
    destinations.retry_failed(saved['id'], group_id=1, role=1, actor_id=product.admin.user_id, expected_revision=2)
    assert m.AuditDelivery.get(m.AuditDelivery.event_id == ids['pending']).destination_revision_id == first.id
    assert destinations.retry_failed(saved['id'], group_id=1, role=1, actor_id=product.admin.user_id,
                                    expected_revision=2, include_pending=True) > 0
    rebound = m.AuditDelivery.get(m.AuditDelivery.event_id == ids['pending'])
    assert rebound.destination_revision_id == current.id and rebound.retry_at <= utc_now()
    unchanged = m.AuditDelivery.get(m.AuditDelivery.event_id == ids['sending'])
    assert unchanged.destination_revision_id == first.id and unchanged.claim_token == 'original-inflight'
    terminal = m.AuditDelivery.get(m.AuditDelivery.event_id == ids['terminal'])
    assert terminal.destination_revision_id == first.id and terminal.status == 'receiver_accepted'
    duplicate = m.AuditDelivery.get(m.AuditDelivery.event_id == ids['duplicate_sending'])
    assert duplicate.id == sending.id and duplicate.claim_token == 'current-inflight' and duplicate.status == 'sending'
    duplicate = m.AuditDelivery.get(m.AuditDelivery.event_id == ids['duplicate_pending'])
    assert duplicate.id == pending.id and duplicate.status == 'pending' and duplicate.retry_at <= utc_now()


@pytest.mark.parametrize(('failure', 'status'), [('certificate', 'failed'), ('tls_eof', 'pending'), ('timeout', 'pending')])
def test_tls_authentication_failure_is_repairable_and_transient_errors_retry_safely(product, monkeypatch, failure, status):
    import ssl
    receiver(product)
    error = {'certificate': ssl.SSLCertVerificationError, 'tls_eof': ssl.SSLEOFError, 'timeout': TimeoutError}[failure]
    monkeypatch.setattr(delivery, 'send', lambda *_: (_ for _ in ()).throw(error('PRIVATE_TLS_DETAILS')))
    assert delivery.process(limit=1) == 1
    row = m.AuditDelivery.select().first()
    assert row.status == status and 'PRIVATE' not in row.last_error


@pytest.mark.parametrize('invalid', ['true', 1, None, []])
def test_pending_requeue_requires_explicit_boolean(product_client, product, invalid):
    receiver(product)
    result = product_client.post(URL+'/1/retry', json={'revision': 1, 'include_pending': invalid})
    assert result.status_code == 400
    assert m.AuditDelivery.select().count() == 1


def test_optional_shared_profile_pins_credentials_and_cannot_copy_them_to_inline_target(product_client, product, monkeypatch):
    from app.modules.integrations.connection_options import ResolvedConnection, parse_input
    from app.modules.roxywi.exception import RoxywiConflictError
    state, uses = {'revision': 1, 'enabled': True}, []
    settings = parse_input(body()['connection'] | {'name': 'Shared profile', 'group_id': 1}).model_dump(
        exclude={'name', 'group_id', 'enabled', 'revision', 'secrets', 'clear_secrets'})
    def resolve(profile_id, group_id, revision=None):
        assert profile_id == 7 and group_id == 1
        if not state['enabled']:
            raise RoxywiConflictError('Shared profile disabled')
        revision = revision or state['revision']
        return ResolvedConnection(7, revision, settings, {'token': 'PinnedSharedSecret' if revision == 1 else 'ChangedSharedSecret'})
    monkeypatch.setattr(destinations, 'shared_profiles', lambda: SimpleNamespace(
        resolve=resolve, bind_use=lambda *args, **kwargs: uses.append((args, kwargs))))
    data = body(profile_id=7)
    data.pop('connection')
    created = product_client.post(URL, json=data)
    assert created.status_code == 201, created.text
    saved = created.json
    pinned = destinations.revision(m.AuditDestination.get_by_id(saved['id']))
    assert saved['profile_revision'] == 1 and saved['configured']['token'] and uses
    assert 'PinnedSharedSecret' not in created.text
    state['revision'] = 2
    assert destinations.resolve_revision(pinned).credentials['token'] == 'PinnedSharedSecret'
    state['enabled'] = False
    with pytest.raises(RoxywiConflictError):
        destinations.resolve_revision(pinned)
    state['enabled'] = True
    inline = body(revision=1)
    inline['connection']['url'] = 'https://different.example.test/capture'
    inline['connection']['secrets'] = {}
    result = product_client.put(f'{URL}/{saved["id"]}', json=inline)
    assert result.status_code == 400
    assert m.AuditDestination.get_by_id(saved['id']).revision == 1
    inline['connection']['secrets'] = {'token': 'ExplicitInlineSecret'}
    accepted = product_client.put(f'{URL}/{saved["id"]}', json=inline)
    assert accepted.status_code == 200
    assert destinations.resolve_revision(pinned).credentials['token'] == 'PinnedSharedSecret'


def disabled_receiver(product, saved):
    current = m.AuditDestination.get_by_id(saved['id'])
    return destinations.save(body(name=current.name, group_id=current.group_id, enabled=False, revision=current.revision),
        group_id=1, role=1, actor_id=product.admin.user_id, destination_id=current.id)


def finish_receiver_work(receiver_id):
    ids = m.AuditDestinationRevision.select(m.AuditDestinationRevision.id).where(
        m.AuditDestinationRevision.destination_id == receiver_id)
    m.AuditDelivery.update(status='receiver_accepted', claim_token=None, claim_expires_at=None).where(
        m.AuditDelivery.destination_revision_id.in_(ids)).execute()


def test_group_lifecycle_blocks_deletion_until_safe_receiver_cleanup_and_reuse_has_no_data(product_client, product):
    from peewee import IntegrityError
    group = m.Groups.create(name='Original isolated tenant')
    saved = receiver(product, group_id=group.group_id)
    assert m.AuditDestination.get_by_id(saved['id']).scope_group == group.group_id
    with pytest.raises(IntegrityError):
        group.delete_instance()
    enabled = product_client.delete(f'{URL}/{saved["id"]}', json={'revision': 1})
    assert enabled.status_code == 409 and 'Disable' in enabled.text
    disabled = disabled_receiver(product, saved)
    assert product_client.delete(f'{URL}/{saved["id"]}', json={'revision': 1}).status_code == 409
    pending = product_client.delete(f'{URL}/{saved["id"]}', json={'revision': disabled['revision']})
    assert pending.status_code == 409 and 'Undelivered work' in pending.text
    finish_receiver_work(saved['id'])
    history_count = m.AuditEvent.select().count()
    removed = product_client.delete(f'{URL}/{saved["id"]}', json={'revision': disabled['revision']})
    assert removed.status_code == 200 and removed.headers['Cache-Control'] == 'no-store'
    assert m.AuditDestination.select().count() == m.AuditDestinationRevision.select().count() == m.AuditDelivery.select().count() == 0
    assert m.AuditEvent.select().count() == history_count+1
    assert m.AuditEvent.select().where(m.AuditEvent.event_type == 'audit.receiver.deleted').exists()
    assert group.delete_instance() == 1
    replacement = m.Groups.create(name='Replacement tenant')
    assert replacement.group_id == group.group_id
    assert destinations.list_destinations(replacement.group_id, 2) == []


@pytest.mark.parametrize('status', ['pending', 'sending', 'failed'])
def test_receiver_delete_never_discards_undelivered_work(product_client, product, status):
    saved = disabled_receiver(product, receiver(product))
    finish_receiver_work(saved['id'])
    row = m.AuditDelivery.select().first()
    m.AuditDelivery.update(status=status).where(m.AuditDelivery.id == row.id).execute()
    result = product_client.delete(f'{URL}/{saved["id"]}', json={'revision': saved['revision']})
    assert result.status_code == 409
    assert m.AuditDelivery.get_by_id(row.id).status == status
    assert m.AuditDestination.get_by_id(saved['id'])


def test_shared_zero_scope_never_requires_or_creates_group_zero(product_client, product):
    assert not m.Groups.select().where(m.Groups.group_id == 0).exists()
    saved = receiver(product, group_id=0, enabled=False)
    assert m.AuditDestination.get_by_id(saved['id']).scope_group is None
    assert product_client.delete(f'{URL}/{saved["id"]}', json={'revision': 1}).status_code == 200
    assert not m.Groups.select().where(m.Groups.group_id == 0).exists()


@pytest.mark.parametrize(('role', 'status'), [(2, 404), (3, 403), (4, 403)])
def test_receiver_delete_enforces_current_group_and_role(product_client, product, role, status):
    saved = receiver(product, group_id=2, enabled=False)
    m.UserGroups.update(user_role_id=role).where(m.UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.delete(f'{URL}/{saved["id"]}', json={'revision': 1}).status_code == status
    assert m.AuditDestination.get_by_id(saved['id'])


@pytest.mark.parametrize('revision', [None, True, '1', 2])
def test_receiver_delete_requires_current_integer_revision(product_client, product, revision):
    saved = receiver(product, enabled=False)
    result = product_client.delete(f'{URL}/{saved["id"]}', json={'revision': revision})
    assert result.status_code == (409 if revision == 2 else 400)
    assert m.AuditDestination.get_by_id(saved['id'])


def test_receiver_delete_audit_failure_rolls_back_data_and_scope_protection(product_client, product, monkeypatch):
    from peewee import IntegrityError
    group = m.Groups.create(group_id=40, name='Protected tenant')
    saved = disabled_receiver(product, receiver(product, group_id=group.group_id))
    finish_receiver_work(saved['id'])
    counts = (m.AuditEvent.select().count(), m.AuditDelivery.select().count(), m.AuditDestinationRevision.select().count())
    monkeypatch.setenv('ROXYWI_AUDIT_MAX_EVENTS', '100')
    m.AuditState.update(records=200).execute()
    result = product_client.delete(f'{URL}/{saved["id"]}', json={'revision': saved['revision']})
    assert result.status_code == 503
    assert m.AuditDestination.get_by_id(saved['id']).scope_group == group.group_id
    assert counts == (m.AuditEvent.select().count(), m.AuditDelivery.select().count(), m.AuditDestinationRevision.select().count())
    with pytest.raises(IntegrityError):
        group.delete_instance()


def test_receiver_deletion_event_targets_only_other_receivers_and_preserves_history(product_client, product):
    saved = receiver(product)
    other = receiver(product, group_id=0, name='Independent security collector')
    disabled = disabled_receiver(product, saved)
    finish_receiver_work(saved['id'])
    old_events = {row.event_id for row in m.AuditEvent.select()}
    assert product_client.delete(f'{URL}/{saved["id"]}', json={'revision': disabled['revision']}).status_code == 200
    assert old_events.issubset({row.event_id for row in m.AuditEvent.select()})
    deleted = m.AuditEvent.get(m.AuditEvent.event_type == 'audit.receiver.deleted')
    outbound = list(m.AuditDelivery.select().where(m.AuditDelivery.event_id == deleted.event_id))
    assert len(outbound) == 1
    assert m.AuditDestinationRevision.get_by_id(outbound[0].destination_revision_id).destination_id == other['id']


def test_receiver_delete_releases_only_own_optional_profile_uses_transactionally(product_client, product, monkeypatch):
    from peewee import Model, IntegerField, CharField
    class ProfileUse(Model):
        profile_id = IntegerField()
        consumer = CharField()
        consumer_id = CharField()
        class Meta:
            database = product.db
            table_name = 'review_profile_uses'
    product.db.create_tables([ProfileUse])
    monkeypatch.setattr(m, 'ConnectionProfileUse', ProfileUse, raising=False)
    monkeypatch.setattr(destinations, 'shared_profiles', lambda: SimpleNamespace())
    saved = receiver(product, enabled=False)
    revision = destinations.revision(m.AuditDestination.get_by_id(saved['id']))
    m.AuditDestinationRevision.update(profile_id=7, profile_revision=1).where(m.AuditDestinationRevision.id == revision.id).execute()
    consumer_id = f'{saved["id"]}:1'
    ProfileUse.create(profile_id=7, consumer='audit', consumer_id=consumer_id)
    ProfileUse.create(profile_id=7, consumer='other', consumer_id=consumer_id)
    monkeypatch.setenv('ROXYWI_AUDIT_MAX_EVENTS', '100')
    m.AuditState.update(records=200).execute()
    assert product_client.delete(f'{URL}/{saved["id"]}', json={'revision': 1}).status_code == 503
    assert ProfileUse.select().count() == 2
    m.AuditState.update(records=1).execute()
    assert product_client.delete(f'{URL}/{saved["id"]}', json={'revision': 1}).status_code == 200
    assert ProfileUse.select().count() == 1 and ProfileUse.get().consumer == 'other'


@pytest.mark.parametrize(('group_id', 'scope_group'), [(1, None), (2, 1), (1, 2), (0, 1)])
def test_receiver_scope_pointer_database_constraint_blocks_inconsistent_ownership(product, group_id, scope_group):
    from peewee import IntegrityError
    saved = receiver(product, enabled=False)
    with pytest.raises(IntegrityError):
        m.AuditDestination.update(group_id=group_id, scope_group=scope_group).where(m.AuditDestination.id == saved['id']).execute()
    row = m.AuditDestination.get_by_id(saved['id'])
    assert row.group_id == row.scope_group == 1


def test_blocked_group_delete_preserves_oidc_mapping_membership_and_settings(product_client, product):
    from app.modules.db import group as group_sql
    group = m.Groups.create(name='Tenant with OIDC metadata')
    mapping = m.OidcGroupMapping.create(provider_id=77, external_group='synthetic-team', group_id=group.group_id, role_id=2)
    m.UserGroups.create(user_id=product.admin.user_id, user_group_id=group.group_id, user_role_id=2)
    m.Setting.create(param='review_scope', value='preserve', section='main', desc='Synthetic setting', group_id=group.group_id)
    saved = receiver(product, group_id=group.group_id, enabled=False)
    with pytest.raises(Exception, match='error:'):
        group_sql.delete_group(group.group_id)
    assert m.Groups.get_by_id(group.group_id)
    assert m.OidcGroupMapping.get_by_id(mapping.id)
    assert m.UserGroups.select().where(m.UserGroups.user_group_id == group.group_id).count() == 1
    assert m.Setting.select().where(m.Setting.group_id == group.group_id).count() == 1
    assert product_client.delete(f'{URL}/{saved["id"]}', json={'revision': 1}).status_code == 200
    assert group_sql.delete_group(group.group_id) is True
    assert not m.OidcGroupMapping.select().where(m.OidcGroupMapping.group_id == group.group_id).exists()
    assert not m.UserGroups.select().where(m.UserGroups.user_group_id == group.group_id).exists()
    assert not m.Setting.select().where(m.Setting.group_id == group.group_id).exists()
