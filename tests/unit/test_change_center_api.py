from types import SimpleNamespace
from contextlib import contextmanager

import pytest
from flask_jwt_extended import create_access_token

import app.routes.change.routes as change_routes
from app.modules.roxywi.exception import (
    RoxywiConflictError,
    RoxywiResourceNotFound,
    RoxywiValidationError,
)


def _change(change_id=1, service='haproxy', group_id=1):
    return SimpleNamespace(id=change_id, service=service, group_id=group_id, server_id=10, status='paused', active_task_id=None)


@pytest.fixture()
def change_api(app, monkeypatch):
    @contextmanager
    def locked_change(change_id, _group_id, **_kwargs):
        # These tests isolate HTTP contracts. Real row locking and contention
        # are exercised against the database in test_change_operations.py.
        yield change_routes.change_sql.get_change(change_id)

    monkeypatch.setattr(change_routes.change_operations, 'locked_change', locked_change)
    user_params = {
        'user_id': 1,
        'user': 'admin',
        'role': 1,
        'group_id': 1,
        'lang': 'en',
    }
    monkeypatch.setattr(
        change_routes.roxywi_common,
        'get_users_params',
        lambda **_kwargs: dict(user_params),
    )
    monkeypatch.setattr(
        change_routes.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'support'},
    )
    monkeypatch.setattr(change_routes.roxywi_auth, 'is_admin', lambda **_kwargs: True)
    monkeypatch.setattr(
        change_routes.roxywi_auth,
        'is_access_permit_to_service',
        lambda _service: True,
    )
    monkeypatch.setattr(change_routes.roxywi_common, 'logging', lambda *_args, **_kwargs: None)
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})
    return user_params, {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}


@pytest.mark.parametrize(
    ('user_status', 'plan'),
    ((1, 'user'), (1, 'company'), (1, 'cloud'), (1, 'Trial'), (0, 'support')),
)
def test_change_center_shows_upgrade_page_but_internal_api_rejects_non_premium_plans(
    client, monkeypatch, change_api, user_status, plan
):
    _user_params, headers = change_api
    monkeypatch.setattr(
        change_routes.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': user_status, 'user_plan': plan},
    )
    monkeypatch.setattr(
        change_routes,
        'render_template',
        lambda template, **_kwargs: template,
    )

    page_response = client.get('/changes', headers=headers)
    api_response = client.get('/changes/api', headers=headers)

    assert page_response.status_code == 200
    assert page_response.get_data(as_text=True) == 'change_center.html'
    assert api_response.status_code == 403
    assert api_response.get_json()['error'] == 'Change Center requires an active Premium plan'


def test_change_api_lists_only_permitted_services(client, monkeypatch, change_api):
    _user_params, headers = change_api
    changes = [_change(1, 'haproxy'), _change(2, 'nginx')]
    monkeypatch.setattr(change_routes.change_sql, 'list_changes', lambda *_args, **_kwargs: changes)
    monkeypatch.setattr(
        change_routes.roxywi_auth,
        'is_access_permit_to_service',
        lambda service: service == 'haproxy',
    )
    monkeypatch.setattr(
        change_routes.change_service,
        'serialize_change',
        lambda change: {'id': change.id, 'service': change.service},
    )

    response = client.get('/changes/api?service=haproxy&status=validated', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['data'] == [{'id': 1, 'service': 'haproxy'}]


def test_change_api_lists_sanitized_notification_destinations(
    client, monkeypatch, change_api
):
    _user_params, headers = change_api
    destinations = [{
        'channel': 'telegram', 'channel_label': 'Telegram',
        'recipient_id': 9, 'label': 'Operations', 'destination': 'Operations',
    }]
    monkeypatch.setattr(
        change_routes.change_automation,
        'list_notification_destinations',
        lambda group_id: destinations if group_id == 1 else [],
    )

    response = client.get(
        '/changes/api/notification-destinations', headers=headers
    )

    assert response.status_code == 200
    assert response.get_json()['data'] == destinations


def test_change_api_rejects_unsupported_service_filter(client, change_api):
    _user_params, headers = change_api

    response = client.get('/changes/api?service=ssh', headers=headers)

    assert response.status_code == 400
    assert response.get_json()['error'] == 'Unsupported service filter'


def test_change_api_creates_and_returns_change(client, monkeypatch, change_api):
    _user_params, headers = change_api
    created = _change(7)
    monkeypatch.setattr(change_routes.change_service, 'create_change', lambda *_args: created)
    monkeypatch.setattr(
        change_routes.change_service,
        'serialize_change',
        lambda change: {'id': change.id, 'service': change.service},
    )

    response = client.post(
        '/changes/api',
        headers=headers,
        json={
            'server_id': 10,
            'service': 'haproxy',
            'action': 'reload',
            'config': 'global\n',
            'title': 'API change',
        },
    )

    assert response.status_code == 201
    assert response.get_json()['data']['id'] == 7


def test_change_api_rejects_creation_without_service_access(client, monkeypatch, change_api):
    _user_params, headers = change_api
    monkeypatch.setattr(
        change_routes.roxywi_auth,
        'is_access_permit_to_service',
        lambda _service: False,
    )

    response = client.post(
        '/changes/api',
        headers=headers,
        json={
            'server_id': 10,
            'service': 'haproxy',
            'config': 'global\n',
            'title': 'Forbidden change',
        },
    )

    assert response.status_code == 403
    assert 'No access' in response.get_json()['error']


def test_change_api_returns_not_found_for_unknown_change(client, monkeypatch, change_api):
    _user_params, headers = change_api
    monkeypatch.setattr(
        change_routes.change_sql,
        'get_change',
        lambda _change_id: (_ for _ in ()).throw(RoxywiResourceNotFound()),
    )

    response = client.get('/changes/api/999', headers=headers)

    assert response.status_code == 404
    assert response.get_json()['status'] == 'failed'


@pytest.mark.parametrize(('group_id', 'service_allowed'), ((2, True), (1, False)))
def test_change_api_protects_group_and_service_access(
    client, monkeypatch, change_api, group_id, service_allowed
):
    _user_params, headers = change_api
    monkeypatch.setattr(
        change_routes.change_sql,
        'get_change',
        lambda _change_id: _change(5, group_id=group_id),
    )
    monkeypatch.setattr(
        change_routes.roxywi_auth,
        'is_access_permit_to_service',
        lambda _service: service_allowed,
    )

    response = client.get('/changes/api/5', headers=headers)

    assert response.status_code == 403


def test_change_api_updates_draft(client, monkeypatch, change_api):
    _user_params, headers = change_api
    change = _change(6)
    monkeypatch.setattr(change_routes.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(change_routes.change_service, 'update_change', lambda *_args: change)
    monkeypatch.setattr(
        change_routes.change_service,
        'serialize_change',
        lambda item: {'id': item.id},
    )

    response = client.put('/changes/api/6', headers=headers, json={'title': 'Updated'})

    assert response.status_code == 200
    assert response.get_json()['data']['id'] == 6


def test_change_api_maps_update_conflict(client, monkeypatch, change_api):
    _user_params, headers = change_api
    change = _change(6)
    monkeypatch.setattr(change_routes.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(
        change_routes.change_service,
        'update_change',
        lambda *_args: (_ for _ in ()).throw(RoxywiConflictError('Already deployed')),
    )

    response = client.put('/changes/api/6', headers=headers, json={'title': 'Updated'})

    assert response.status_code == 409
    assert response.get_json()['error'] == 'Already deployed'


@pytest.mark.parametrize(
    'action',
    ('validate', 'deploy', 'rollback', 'cancel', 'recover', 'pause', 'resume', 'promote'),
)
def test_change_api_exposes_workflow_actions(client, monkeypatch, change_api, action):
    _user_params, headers = change_api
    change = _change(8)
    queued = action in ('validate', 'deploy', 'rollback', 'resume', 'promote')
    calls = []

    def enqueue(change_id, operation, group_id, actor_id, **kwargs):
        calls.append((change_id, operation, group_id, actor_id, kwargs))
        change.active_task_id = 42
        return change

    monkeypatch.setattr(change_routes.change_operations, 'enqueue', enqueue)
    monkeypatch.setattr(change_routes.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(
        change_routes.change_service,
        f'{action}_change',
        lambda *_args: pytest.fail('Web must queue remote work') if queued else change,
    )
    monkeypatch.setattr(
        change_routes.change_service,
        'serialize_change',
        lambda item: {'id': item.id},
    )

    response = client.post(f'/changes/api/{change.id}/{action}', headers=headers)

    assert response.status_code == (202 if queued else 200)
    assert response.get_json()['data']['id'] == change.id
    if queued:
        assert response.get_json()['status'] == 'accepted'
        assert response.get_json()['tasks_ids'] == [42]
        assert calls == [(change.id, action, 1, 1, {'target_id': None})]
    else:
        assert calls == []


def test_change_api_requires_admin_for_approval(client, monkeypatch, change_api):
    user_params, headers = change_api
    user_params['role'] = 3

    response = client.post('/changes/api/1/approve', headers=headers)

    assert response.status_code == 403


def test_change_api_previews_rollout_topology(client, monkeypatch, change_api):
    _user_params, headers = change_api
    monkeypatch.setattr(
        change_routes.change_service,
        'rollout_preview',
        lambda server_id, service, group_id: [{
            'server_id': int(server_id), 'service': service, 'group_id': group_id,
        }],
    )

    response = client.get(
        '/changes/api/rollout-preview?server_id=10&service=haproxy',
        headers=headers,
    )

    assert response.status_code == 200
    assert response.get_json()['data'] == [
        {'server_id': 10, 'service': 'haproxy', 'group_id': 1}
    ]


@pytest.mark.parametrize('action', ('retry', 'rollback', 'exclude', 'include'))
def test_change_api_exposes_per_target_actions(
    client, monkeypatch, change_api, action
):
    _user_params, headers = change_api
    change = _change(12)
    calls = []

    def enqueue(change_id, operation, group_id, actor_id, *, target_id):
        calls.append((change_id, operation, group_id, actor_id, target_id))
        change.active_task_id = 42
        return change

    monkeypatch.setattr(change_routes.change_operations, 'enqueue', enqueue)
    monkeypatch.setattr(change_routes.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(
        change_routes.change_service,
        f'{action}_target' if action in ('retry', 'rollback', 'exclude', 'include') else action,
        lambda *_args, **_kwargs: change if action == 'exclude' else pytest.fail('Web must queue remote work'),
    )
    monkeypatch.setattr(
        change_routes.change_service,
        'serialize_change',
        lambda item: {'id': item.id},
    )

    response = client.post(
        f'/changes/api/12/targets/22/{action}',
        headers=headers,
        json={} if action == 'exclude' else None,
    )

    assert response.status_code == (200 if action == 'exclude' else 202)
    assert response.get_json()['data']['id'] == 12
    assert calls == ([] if action == 'exclude' else [(12, action, 1, 1, 22)])


def test_change_api_allows_distinct_admin_to_approve(client, monkeypatch, change_api):
    _user_params, headers = change_api
    change = _change(11)
    monkeypatch.setattr(change_routes.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(change_routes.change_service, 'approve_change', lambda *_args: change)
    monkeypatch.setattr(
        change_routes.change_service,
        'serialize_change',
        lambda item: {'id': item.id},
    )

    response = client.post('/changes/api/11/approve', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['data']['id'] == 11


def test_change_api_maps_queue_validation_error(client, monkeypatch, change_api):
    _user_params, headers = change_api
    change = _change(9)
    monkeypatch.setattr(change_routes.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(
        change_routes.change_operations,
        'enqueue',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RoxywiValidationError('Unsupported operation')),
    )

    response = client.post('/changes/api/9/deploy', headers=headers)

    assert response.status_code == 400
    assert response.get_json()['error'] == 'Unsupported operation'


def test_change_api_hides_unexpected_exception_behind_failed_response(
    client, monkeypatch, change_api
):
    _user_params, headers = change_api
    monkeypatch.setattr(
        change_routes.change_sql,
        'list_changes',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('database unavailable')),
    )

    response = client.get('/changes/api', headers=headers)

    assert response.status_code == 500
    assert response.get_json() == {
        'status': 'failed',
        'error': 'Internal server error',
    }


@pytest.mark.parametrize(
    ('path', 'handler_name'),
    (
        ('schedule/cancel', 'cancel_schedule'),
        ('drift', 'check_change_drift'),
    ),
)
def test_change_api_exposes_automation_actions(
    client, monkeypatch, change_api, path, handler_name
):
    user_params, headers = change_api
    change = _change(31)
    calls = []
    if path == 'drift':
        def enqueue(change_id, action, group_id, actor_id, **_kwargs):
            assert action == 'drift'
            calls.append((change_id, group_id, actor_id))
            change.active_task_id = 42
            return change
        monkeypatch.setattr(change_routes.change_operations, 'enqueue', enqueue)
    monkeypatch.setattr(change_routes.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(
        change_routes.change_automation,
        handler_name,
        lambda change_id, group_id, actor_id: calls.append(
            (change_id, group_id, actor_id)
        ) or change,
    )
    monkeypatch.setattr(
        change_routes.change_service, 'serialize_change', lambda item: {'id': item.id}
    )

    response = client.post(f'/changes/api/31/{path}', headers=headers)

    assert response.status_code == (202 if path == 'drift' else 200)
    assert calls == [(31, 1, user_params['user_id'])]


def test_change_api_schedules_with_maintenance_window(
    client, monkeypatch, change_api
):
    user_params, headers = change_api
    change = _change(32)
    captured = {}
    monkeypatch.setattr(change_routes.change_sql, 'get_change', lambda _change_id: change)

    def schedule(change_id, body, group_id, actor_id):
        captured.update(
            change_id=change_id,
            scheduled_at=body.scheduled_at,
            window_end=body.maintenance_window_end,
            group_id=group_id,
            actor_id=actor_id,
        )
        return change

    monkeypatch.setattr(change_routes.change_automation, 'schedule_change', schedule)
    monkeypatch.setattr(
        change_routes.change_service, 'serialize_change', lambda item: {'id': item.id}
    )

    response = client.post(
        '/changes/api/32/schedule',
        headers=headers,
        json={
            'scheduled_at': '2099-01-01T10:00:00Z',
            'maintenance_window_end': '2099-01-01T11:00:00Z',
        },
    )

    assert response.status_code == 200
    assert captured['change_id'] == 32
    assert captured['group_id'] == 1
    assert captured['actor_id'] == user_params['user_id']
    assert captured['window_end'] > captured['scheduled_at']


def test_change_api_exposes_filtered_audit_statistics_and_report(
    client, monkeypatch, change_api
):
    _user_params, headers = change_api
    change = _change(33)
    captured = {}
    monkeypatch.setattr(change_routes.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(
        change_routes.change_automation,
        'list_audit_events',
        lambda group_id, query, **kwargs: captured.update(
            group_id=group_id, service=query.service, change_id=kwargs.get('change_id')
        ) or [{'id': 1, 'service': 'haproxy'}],
    )
    monkeypatch.setattr(
        change_routes.change_automation,
        'deployment_statistics',
        lambda group_id, days, **_kwargs: {'group_id': group_id, 'period_days': days},
    )
    monkeypatch.setattr(
        change_routes.change_automation,
        'build_change_report',
        lambda _change, **kwargs: 'a,b\n1,2\n' if kwargs.get('as_csv') else {'id': 33},
    )

    audit = client.get('/changes/api/audit?service=haproxy&q=node', headers=headers)
    timeline = client.get('/changes/api/33/events', headers=headers)
    statistics = client.get('/changes/api/statistics?days=90', headers=headers)
    report = client.get('/changes/api/33/report?format=csv', headers=headers)

    assert audit.status_code == 200
    assert timeline.status_code == 200
    assert statistics.get_json()['data']['period_days'] == 90
    assert report.mimetype == 'text/csv'
    assert 'change-33-report.csv' in report.headers['Content-Disposition']
    assert captured['change_id'] == 33


def test_change_api_manages_webhooks_without_exposing_secret(
    client, monkeypatch, change_api
):
    _user_params, headers = change_api
    webhook = SimpleNamespace(id=7)
    monkeypatch.setattr(change_routes.change_sql, 'list_webhooks', lambda _group_id: [webhook])
    monkeypatch.setattr(change_routes.change_automation, 'create_webhook', lambda *_args: webhook)
    monkeypatch.setattr(change_routes.change_automation, 'update_webhook', lambda *_args: webhook)
    monkeypatch.setattr(change_routes.change_automation, 'delete_webhook', lambda *_args: None)
    monkeypatch.setattr(change_routes.change_automation, 'queue_webhook_test', lambda *_args: webhook)
    monkeypatch.setattr(
        change_routes.change_automation,
        'serialize_webhook',
        lambda item: {'id': item.id, 'secret_configured': True},
    )

    listed = client.get('/changes/api/webhooks', headers=headers)
    created = client.post(
        '/changes/api/webhooks',
        headers=headers,
        json={'name': 'automation', 'url': 'https://hooks.example.test/roxy-wi'},
    )
    updated = client.put(
        '/changes/api/webhooks/7', headers=headers, json={'enabled': False}
    )
    tested = client.post('/changes/api/webhooks/7/test', headers=headers)
    deleted = client.delete('/changes/api/webhooks/7', headers=headers)

    assert listed.status_code == 200
    assert created.status_code == 201
    assert updated.status_code == 200
    assert tested.status_code == 200
    assert deleted.status_code == 200
    assert 'secret' not in created.get_json()['data']


def test_change_api_requires_admin_to_manage_webhooks(
    client, change_api
):
    user_params, headers = change_api
    user_params['role'] = 3

    response = client.get('/changes/api/webhooks', headers=headers)

    assert response.status_code == 403
