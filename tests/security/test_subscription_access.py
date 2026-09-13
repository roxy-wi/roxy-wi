from types import SimpleNamespace

import pytest
import jwt as pyjwt
from flask_jwt_extended import create_access_token

import app.modules.change.service as change_service
import app.modules.oidc.login as oidc_login
import app.modules.service.backup as backup_service
import app.modules.subscription.access as subscription_access
import app.modules.tools.smon as smon_service
from app.modules.roxywi.exception import RoxywiPermissionError


@pytest.mark.security
def test_socket_ticket_requires_managed_services_subscription(app, client, monkeypatch):
    monkeypatch.setattr(
        subscription_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'Trial'},
    )
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})

    response = client.get(
        '/socket-ticket',
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
    )

    assert response.status_code == 403
    assert response.get_json()['error'] == (
        'Additional services require an active User plan or higher'
    )


@pytest.mark.security
def test_socket_ticket_contains_signed_short_lived_group_identity(app, client, monkeypatch):
    monkeypatch.setattr(
        subscription_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'user'},
    )
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})

    response = client.get(
        '/socket-ticket',
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
    )

    assert response.status_code == 200
    response_data = response.get_json()
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Pragma'] == 'no-cache'
    claims = pyjwt.decode(
        response_data['token'],
        app.config['JWT_SECRET_KEY'],
        algorithms=['HS256'],
        audience='roxy-socket',
    )
    assert response_data['expires_in'] == app.config['SOCKET_TICKET_SECONDS']
    assert claims['user_id'] == '1'
    assert claims['group'] == '1'
    assert claims['socket_ticket'] is True
    assert claims['exp'] - claims['iat'] == response_data['expires_in']


@pytest.mark.security
def test_browser_socket_identity_is_not_read_from_hidden_html_fields():
    from pathlib import Path

    base_template = Path('app/templates/base.html').read_text(encoding='utf-8')
    browser_script = Path('app/static/js/script.js').read_text(encoding='utf-8')

    assert 'user_group_socket' not in base_template
    assert 'user_id_socket' not in base_template
    assert 'alert_group ' not in browser_script
    assert "fetch('/socket-ticket'" in browser_script
    assert "type: 'authenticate'" in browser_script


@pytest.mark.security
@pytest.mark.parametrize(
    ('feature', 'allowed_plans'),
    (
        (subscription_access.OIDC, {'company', 'cloud', 'support'}),
        (subscription_access.CHANGE_CENTER, {'support'}),
        (subscription_access.GIT_BACKUP, {'support'}),
        (subscription_access.SMON_STATUS_PAGES, {'support'}),
        (
            subscription_access.MANAGED_SERVICES,
            {'user', 'company', 'cloud', 'support'},
        ),
    ),
)
def test_feature_policy_uses_explicit_active_plan_allowlists(feature, allowed_plans):
    for plan in ('user', 'Trial', 'company', 'cloud', 'support'):
        subscription = {'user_status': 1, 'user_plan': plan}
        assert subscription_access.is_feature_available(feature, subscription) is (
            plan.lower() in allowed_plans
        )

    assert not subscription_access.is_feature_available(
        feature, {'user_status': 0, 'user_plan': next(iter(allowed_plans))}
    )


@pytest.mark.security
@pytest.mark.parametrize('subscription', (None, {}, [], 'support', {'user_status': 'bad'}))
def test_feature_policy_fails_closed_for_missing_or_malformed_entitlement(
    monkeypatch, subscription
):
    monkeypatch.setattr(
        subscription_access.roxywi_common,
        'return_user_subscription',
        lambda: subscription,
    )

    assert not subscription_access.is_feature_available(subscription_access.CHANGE_CENTER)
    with pytest.raises(RoxywiPermissionError, match='Premium'):
        subscription_access.require_feature(subscription_access.CHANGE_CENTER)


@pytest.mark.security
def test_feature_policy_registry_cannot_be_mutated_at_runtime():
    with pytest.raises(TypeError):
        subscription_access.FEATURE_POLICIES['bypass'] = subscription_access.FEATURE_POLICIES[
            subscription_access.OIDC
        ]


@pytest.mark.security
def test_distributed_worker_lifecycle_is_not_managed_by_the_roxy_wi_host(
    app, client, monkeypatch
):
    from app.routes.admin import routes as admin_routes

    monkeypatch.setattr(
        subscription_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'Trial'},
    )
    monkeypatch.setattr(admin_routes.roxywi_auth, 'page_for_admin', lambda **_kwargs: None)
    actions = []
    monkeypatch.setattr(
        admin_routes.roxy,
        'action_service',
        lambda action, service: actions.append((action, service)) or 'ok',
    )
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    start_response = client.post(
        '/admin/tools/action/roxy-wi-checker/start',
        headers=headers,
    )
    stop_response = client.post(
        '/admin/tools/action/roxy-wi-checker/stop',
        headers=headers,
    )

    assert start_response.status_code == 200
    assert 'worker host or by its orchestrator' in start_response.get_data(as_text=True)
    assert stop_response.status_code == 200
    assert 'worker host or by its orchestrator' in stop_response.get_data(as_text=True)
    assert actions == []


@pytest.mark.security
def test_business_services_recheck_entitlement_before_side_effects(monkeypatch):
    monkeypatch.setattr(
        subscription_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'company'},
    )
    side_effects = []
    monkeypatch.setattr(
        change_service.change_sql,
        'get_change',
        lambda *_args: side_effects.append('change-db-read'),
    )
    monkeypatch.setattr(
        oidc_login,
        '_resolve_user',
        lambda *_args: side_effects.append('oidc-user-write'),
    )
    monkeypatch.setattr(
        backup_service.installation_mod,
        'run_ansible',
        lambda *_args: side_effects.append('ansible'),
    )
    monkeypatch.setattr(
        smon_service.smon_sql,
        'add_status_page',
        lambda *_args: side_effects.append('smon-db-write'),
    )

    with pytest.raises(RoxywiPermissionError, match='Change Center'):
        change_service.cancel_change(1, group_id=1)
    monkeypatch.setattr(
        subscription_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'user'},
    )
    with pytest.raises(RoxywiPermissionError, match='OIDC'):
        oidc_login.complete_oidc_login(None, {})
    monkeypatch.setattr(
        subscription_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'company'},
    )
    with pytest.raises(RoxywiPermissionError, match='Git backup'):
        backup_service.create_git_backup_inv(
            SimpleNamespace(), '192.0.2.1', 'haproxy'
        )
    with pytest.raises(RoxywiPermissionError, match='SMON status pages'):
        smon_service.create_status_page('name', 'slug', '', [1])

    assert side_effects == []


@pytest.mark.security
def test_http_routes_cannot_bypass_premium_service_guards(app, client, monkeypatch):
    monkeypatch.setattr(
        subscription_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'company'},
    )
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
    }

    responses = (
        client.post('/server/backup/git', json={}, headers=headers),
        client.post('/api/server/backup/git', json={}, headers=headers),
        client.post('/smon/status-page', data={}, headers=headers),
        client.get('/smon/status/checks/1', headers=headers),
    )

    assert [response.status_code for response in responses] == [403, 403, 403, 403]
    assert responses[0].get_json()['error'] == 'Git backup requires an active Premium plan'
    assert responses[2].get_json()['error'] == 'SMON status pages require an active Premium plan'
