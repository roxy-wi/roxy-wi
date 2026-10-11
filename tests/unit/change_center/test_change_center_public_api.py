from types import SimpleNamespace

import pytest
from flask_jwt_extended import create_access_token

import app.api.routes.change_routes as public_change_api


def _change(change_id=1, service='haproxy', group_id=1):
    return SimpleNamespace(id=change_id, service=service, group_id=group_id, server_id=10)


@pytest.fixture()
def public_api(app, monkeypatch):
    user_params = {
        'user_id': 1,
        'user': 'admin',
        'role': 1,
        'group_id': 1,
        'lang': 'en',
    }
    monkeypatch.setattr(
        public_change_api.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'support'},
    )
    monkeypatch.setattr(
        public_change_api.roxywi_common,
        'get_users_params',
        lambda **_kwargs: dict(user_params),
    )
    monkeypatch.setattr(
        public_change_api.roxywi_common,
        'check_user_group_for_flask',
        lambda: True,
    )
    monkeypatch.setattr(public_change_api.roxywi_common, 'logging', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(public_change_api.roxywi_auth, 'is_admin', lambda **_kwargs: True)
    monkeypatch.setattr(
        public_change_api.roxywi_auth,
        'is_access_permit_to_service',
        lambda _service: True,
    )
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})
    return user_params, {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}


def test_public_change_api_requires_jwt(client, public_api):
    response = client.get('/api/changes', headers={'Accept': 'application/json'})

    assert response.status_code == 401


def test_public_change_api_keeps_subscription_gate(client, monkeypatch, public_api):
    _user_params, headers = public_api
    monkeypatch.setattr(
        public_change_api.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 0, 'user_plan': 'support'},
    )

    response = client.get('/api/changes', headers=headers)

    assert response.status_code == 401


@pytest.mark.parametrize('plan', ('user', 'company', 'cloud', 'Trial'))
def test_public_change_api_rejects_active_non_premium_plans(
    client, monkeypatch, public_api, plan
):
    _user_params, headers = public_api
    monkeypatch.setattr(
        public_change_api.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': plan},
    )

    response = client.get('/api/changes', headers=headers)

    expected_status = 401 if plan == 'user' else 403
    assert response.status_code == expected_status


def test_public_change_api_lists_filtered_permitted_changes(client, monkeypatch, public_api):
    _user_params, headers = public_api
    changes = [_change(1, 'haproxy'), _change(2, 'nginx')]
    received_filters = []
    monkeypatch.setattr(
        public_change_api.change_sql,
        'list_changes',
        lambda group_id, **kwargs: received_filters.append((group_id, kwargs)) or changes,
    )
    monkeypatch.setattr(
        public_change_api.roxywi_auth,
        'is_access_permit_to_service',
        lambda service: service == 'haproxy',
    )
    monkeypatch.setattr(
        public_change_api.change_service,
        'serialize_change',
        lambda change: {'id': change.id, 'service': change.service},
    )

    response = client.get(
        '/api/changes?service=haproxy&status=validated',
        headers=headers,
    )

    assert response.status_code == 200
    assert response.get_json()['data'] == [{'id': 1, 'service': 'haproxy'}]
    assert received_filters == [(1, {'service': 'haproxy', 'status': 'validated'})]


def test_public_change_api_validates_query_enums(client, public_api):
    _user_params, headers = public_api

    response = client.get('/api/changes?status=made_up', headers=headers)

    assert response.status_code == 400


def test_public_change_api_creates_draft(client, monkeypatch, public_api):
    _user_params, headers = public_api
    change = _change(12)
    received = {}

    def create_change(body, *_args):
        received['execution_mode'] = body.execution_mode
        return change

    monkeypatch.setattr(public_change_api.change_service, 'create_change', create_change)
    monkeypatch.setattr(
        public_change_api.change_service,
        'serialize_change',
        lambda item: {'id': item.id, 'service': item.service},
    )

    response = client.post(
        '/api/changes',
        headers=headers,
        json={
            'server_id': 10,
            'service': 'haproxy',
            'action': 'reload',
            'execution_mode': 'parallel',
            'config': 'global\n',
            'title': 'Public API change',
            'requires_approval': True,
        },
    )

    assert response.status_code == 201
    assert response.get_json()['data']['id'] == 12
    assert received['execution_mode'] == 'parallel'


def test_public_change_api_protects_active_group(client, monkeypatch, public_api):
    _user_params, headers = public_api
    monkeypatch.setattr(
        public_change_api.change_sql,
        'get_change',
        lambda _change_id: _change(13, group_id=2),
    )

    response = client.get('/api/changes/13', headers=headers)

    assert response.status_code == 403


def test_public_change_api_updates_draft(client, monkeypatch, public_api):
    _user_params, headers = public_api
    change = _change(14)
    monkeypatch.setattr(public_change_api.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(public_change_api.change_service, 'update_change', lambda *_args: change)
    monkeypatch.setattr(
        public_change_api.change_service,
        'serialize_change',
        lambda item: {'id': item.id},
    )

    response = client.put('/api/changes/14', headers=headers, json={'title': 'Updated'})

    assert response.status_code == 200
    assert response.get_json()['data']['id'] == 14


@pytest.mark.parametrize(
    'action',
    ('validate', 'approve', 'deploy', 'rollback', 'cancel', 'recover', 'pause', 'resume', 'promote'),
)
def test_public_change_api_exposes_each_workflow_action(
    client, monkeypatch, public_api, action
):
    _user_params, headers = public_api
    change = _change(15)
    monkeypatch.setattr(public_change_api.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(
        public_change_api.change_service,
        f'{action}_change',
        lambda *_args: change,
    )
    monkeypatch.setattr(
        public_change_api.change_service,
        'serialize_change',
        lambda item: {'id': item.id},
    )

    response = client.post(f'/api/changes/15/{action}', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['data']['id'] == 15


def test_public_change_api_limits_approval_to_administrators(
    client, monkeypatch, public_api
):
    user_params, headers = public_api
    user_params['role'] = 3
    change = _change(16)
    monkeypatch.setattr(public_change_api.change_sql, 'get_change', lambda _change_id: change)

    response = client.post('/api/changes/16/approve', headers=headers)

    assert response.status_code == 403


def test_public_change_api_previews_and_controls_rollout_targets(
    client, monkeypatch, public_api
):
    _user_params, headers = public_api
    change = _change(17)
    monkeypatch.setattr(public_change_api.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(
        public_change_api.change_service,
        'rollout_preview',
        lambda *_args: [{'server_id': 10, 'role': 'master'}],
    )
    monkeypatch.setattr(
        public_change_api.change_service,
        'retry_target',
        lambda *_args: change,
    )
    monkeypatch.setattr(
        public_change_api.change_service,
        'serialize_change',
        lambda item: {'id': item.id},
    )

    preview = client.get(
        '/api/changes/rollout-preview?server_id=10&service=haproxy',
        headers=headers,
    )
    action = client.post('/api/changes/17/targets/21/retry', headers=headers)

    assert preview.status_code == 200
    assert preview.get_json()['data'][0]['role'] == 'master'
    assert action.status_code == 200
    assert action.get_json()['data']['id'] == 17


def test_public_change_api_exposes_stage_four_automation(
    client, monkeypatch, public_api
):
    _user_params, headers = public_api
    change = _change(18)
    webhook = SimpleNamespace(id=4)
    monkeypatch.setattr(public_change_api.change_sql, 'get_change', lambda _change_id: change)
    monkeypatch.setattr(public_change_api.change_sql, 'list_webhooks', lambda _group_id: [webhook])
    monkeypatch.setattr(public_change_api.change_automation, 'schedule_change', lambda *_args: change)
    monkeypatch.setattr(public_change_api.change_automation, 'check_change_drift', lambda *_args: change)
    monkeypatch.setattr(
        public_change_api.change_automation,
        'list_audit_events',
        lambda *_args, **_kwargs: [{'id': 1, 'service': 'haproxy'}],
    )
    monkeypatch.setattr(
        public_change_api.change_automation,
        'deployment_statistics',
        lambda _group_id, days, **_kwargs: {'period_days': days},
    )
    monkeypatch.setattr(
        public_change_api.change_automation,
        'serialize_webhook',
        lambda item: {'id': item.id, 'secret_configured': False},
    )
    monkeypatch.setattr(
        public_change_api.change_service, 'serialize_change', lambda item: {'id': item.id}
    )

    scheduled = client.post(
        '/api/changes/18/schedule',
        headers=headers,
        json={'scheduled_at': '2099-01-01T10:00:00Z'},
    )
    drift = client.post('/api/changes/18/drift', headers=headers)
    timeline = client.get('/api/changes/18/events', headers=headers)
    audit = client.get('/api/changes/audit?q=node', headers=headers)
    statistics = client.get('/api/changes/statistics?days=60', headers=headers)
    webhooks = client.get('/api/changes/webhooks', headers=headers)

    assert scheduled.status_code == 200
    assert drift.status_code == 200
    assert timeline.get_json()['data'][0]['id'] == 1
    assert audit.get_json()['data'][0]['service'] == 'haproxy'
    assert statistics.get_json()['data']['period_days'] == 60
    assert webhooks.get_json()['data'][0]['id'] == 4


def test_swagger_contains_configuration_change_entity(client, public_api):
    _user_params, headers = public_api
    response = client.get('/api/spec', headers=headers)

    assert response.status_code == 200
    spec = response.get_json()
    expected_paths = {
        '/api/changes',
        '/api/changes/rollout-preview',
        '/api/changes/{change_id}',
        '/api/changes/{change_id}/validate',
        '/api/changes/{change_id}/approve',
        '/api/changes/{change_id}/deploy',
        '/api/changes/{change_id}/rollback',
        '/api/changes/{change_id}/cancel',
        '/api/changes/{change_id}/recover',
        '/api/changes/{change_id}/pause',
        '/api/changes/{change_id}/resume',
        '/api/changes/{change_id}/promote',
        '/api/changes/{change_id}/targets/{target_id}/{action}',
        '/api/changes/{change_id}/schedule',
        '/api/changes/{change_id}/schedule/cancel',
        '/api/changes/{change_id}/drift',
        '/api/changes/{change_id}/events',
        '/api/changes/{change_id}/report',
        '/api/changes/audit',
        '/api/changes/statistics',
        '/api/changes/notification-destinations',
        '/api/changes/webhooks',
        '/api/changes/webhooks/{webhook_id}',
        '/api/changes/webhooks/{webhook_id}/test',
    }
    assert expected_paths <= set(spec['paths'])
    assert '/changes/api' not in spec['paths']
    assert {
        'ConfigChange', 'ConfigChangeCreate', 'ConfigChangeUpdate', 'ConfigChangeTarget',
        'ConfigChangeSchedule', 'ConfigChangeEvent', 'ConfigChangeWebhook',
        'NotificationDestination', 'NotificationDestinationOption',
        'ConfigChangeStatistics',
    } <= set(spec['definitions'])
    assert any(tag['name'] == 'Configuration changes' for tag in spec['tags'])
    assert spec['securityDefinitions']['BearerAuth']['name'] == 'Authorization'
    deploy_operation = spec['paths']['/api/changes/{change_id}/deploy']['post']
    assert deploy_operation['tags'] == ['Configuration changes']
    assert deploy_operation['security'] == [{'BearerAuth': []}]
    assert 'auto_rollback_failed' in spec['definitions']['ConfigChange']['properties']['status']['enum']
    assert 'deployment_interrupted' in spec['definitions']['ConfigChange']['properties']['status']['enum']
    assert spec['definitions']['ConfigChange']['properties']['targets']['items'] == {
        '$ref': '#/definitions/ConfigChangeTarget'
    }
    assert spec['definitions']['ConfigChangeTarget']['properties']['role']['enum'] == [
        'slave', 'master', 'standalone'
    ]
    assert spec['definitions']['ConfigChangeCreate']['properties']['execution_mode'] == {
        'type': 'string',
        'enum': ['rolling', 'parallel'],
        'default': 'rolling',
        'description': 'Rolling applies nodes sequentially; parallel applies up to eight nodes concurrently',
    }
    assert spec['definitions']['ConfigChange']['properties']['execution_mode']['enum'] == [
        'rolling', 'parallel'
    ]
    assert spec['definitions']['ConfigChange']['properties']['manual_promotion']['type'] == 'boolean'
    assert spec['definitions']['ConfigChangeTarget']['properties']['is_canary']['type'] == 'boolean'
    assert 'awaiting_promotion' in spec['definitions']['ConfigChange']['properties']['status']['enum']
    assert 'scheduled' in spec['definitions']['ConfigChange']['properties']['status']['enum']
    assert 'schedule_missed' in spec['definitions']['ConfigChange']['properties']['status']['enum']
    assert spec['definitions']['ConfigChange']['properties']['drift_status']['type'] == 'string'
    assert spec['definitions']['ConfigChangeCreate']['properties']['notification_channels']['type'] == 'array'
    assert spec['definitions']['ConfigChangeCreate']['properties']['notification_destinations']['items'] == {
        '$ref': '#/definitions/NotificationDestination'
    }
