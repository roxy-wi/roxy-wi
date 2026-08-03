import pytest
from flask_jwt_extended import create_access_token


def _rule_methods(app, rule_path):
    return next(rule.methods for rule in app.url_map.iter_rules() if str(rule) == rule_path)


@pytest.mark.security
def test_scheduler_api_is_disabled_and_scheduler_is_not_started_in_web_process(app):
    from app import scheduler

    assert app.config['SCHEDULER_API_ENABLED'] is False
    assert app.config['SCHEDULER_ENABLED'] is False
    assert not scheduler.running
    assert not any(str(rule).startswith('/scheduler') for rule in app.url_map.iter_rules())


@pytest.mark.security
@pytest.mark.parametrize('rule_path', [
    '/service/<service>/<server_id>/<any(start, stop, reload, restart):action>',
    '/runtimeapi/table/delete/<server_ip>/<table>/<ip_for_delete>',
    '/runtimeapi/table/clear/<server_ip>/<table>',
    '/runtimeapi/session/delete/<server_ip>/<sess_id>',
    '/waf/<server_ip>/rule/<int:rule_id>/<int:enable>',
    '/waf/<any(haproxy, nginx):service>/mode/<int:server_id>/<any(On, Off, DetectionOnly):waf_mode>',
    '/waf/metric/enable/<int:enable>/<int:server_id>',
    '/admin/tools/update/<service>',
    '/admin/tools/action/<service>/<any(start, stop, restart):action>',
    '/admin/update/check',
    '/server/system_info/update/<server_ip>/<int:server_id>',
])
def test_state_changing_routes_do_not_accept_get(app, rule_path):
    methods = _rule_methods(app, rule_path)
    assert 'POST' in methods
    assert 'GET' not in methods


@pytest.mark.security
def test_option_delete_requires_delete_method(app):
    methods = _rule_methods(app, '/add/option/delete/<int:option_id>')
    assert 'DELETE' in methods
    assert 'GET' not in methods


@pytest.mark.security
def test_api_text_in_url_does_not_bypass_authentication(client):
    response = client.get('/?api=1')
    assert response.status_code == 302
    assert response.location.startswith('/login')


@pytest.mark.security
def test_smon_history_is_not_public(client):
    response = client.get('/smon/history/statuses/1')
    assert response.status_code == 401


@pytest.mark.security
def test_haproxy_dependency_map_is_not_public(client):
    response = client.get('/config/map/haproxy/192.0.2.10/show')
    assert response.status_code == 302
    assert response.location.startswith('/login')


@pytest.mark.security
def test_logout_revokes_bearer_token(app, client):
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})
    headers = {'Authorization': f'Bearer {token}'}

    assert client.post('/logout', headers=headers).status_code == 302
    response = client.get('/', headers=headers)
    assert response.status_code == 302
    assert response.location.startswith('/login')
