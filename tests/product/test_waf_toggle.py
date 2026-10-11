from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.modules.db.db_model import WafRules
from app.modules.roxywi import auth, waf


def toggle(client, product, state, service='nginx', enabled=0, legacy=False):
    prefix = '' if legacy else service + '/'
    return client.post(f'/waf/{prefix}{product.server.ip}/rule/{state.rules[service].id}/{enabled}')


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('legacy', [False, True])
def test_toggle_updates_files_before_database_and_repeats_safely(product_client, product, waf_switching,
                                                                 monkeypatch, service, legacy):
    state = waf_switching
    entrypoint = state.entrypoints[service]
    original = entrypoint.read_bytes()
    other = state.entrypoints['haproxy' if service == 'nginx' else 'nginx']
    unchanged = other.read_bytes()
    update = waf.waf_sql.update_enable_waf_rules
    changes = []

    def update_after_ssh(rule_id, serv, enabled):
        content = entrypoint.read_bytes()
        assert (content == original) == bool(enabled)
        changes.append(enabled)
        update(rule_id, serv, enabled)

    monkeypatch.setattr(waf.waf_sql, 'update_enable_waf_rules', update_after_ssh)
    for enabled in (0, 0, 1, 1):
        response = toggle(product_client, product, state, service, enabled, legacy)
        assert response.status_code == 200, response.text
        assert response.json == {'status': 'updated', 'enabled': enabled}
        assert WafRules.get_by_id(state.rules[service].id).en == enabled
    assert changes == [0, 0, 1, 1]
    assert entrypoint.read_bytes() == original
    assert other.read_bytes() == unchanged
    assert (state.roots[service] / 'rules/test.conf').read_text() == '# customer rule content\n'


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('failure', ['fail_before', 'lose_response', 'database'])
def test_failed_toggle_keeps_database_state_and_can_resume(product_client, product, waf_switching,
                                                          monkeypatch, service, failure):
    state = waf_switching
    update = waf.waf_sql.update_enable_waf_rules
    if failure == 'database':
        def fail_update(*args):
            raise OSError('synthetic database failure')
        monkeypatch.setattr(waf.waf_sql, 'update_enable_waf_rules', fail_update)
    else:
        setattr(state, failure, True)
    response = toggle(product_client, product, state, service)
    assert response.status_code == 500
    assert response.json['status'] == 'failed'
    assert 'synthetic' not in response.text
    assert WafRules.get_by_id(state.rules[service].id).en == 1
    state.fail_before = False
    monkeypatch.setattr(waf.waf_sql, 'update_enable_waf_rules', update)
    assert toggle(product_client, product, state, service).status_code == 200
    assert WafRules.get_by_id(state.rules[service].id).en == 0
    content = state.entrypoints[service].read_bytes()
    assert toggle(product_client, product, state, service).status_code == 200
    assert state.entrypoints[service].read_bytes() == content


@pytest.mark.parametrize('output', ['', '{"status":"ok"}', '{"status":"ok","enabled":1}', 'not JSON'])
def test_unknown_remote_result_does_not_change_database(product_client, product, waf_switching, monkeypatch, output):
    monkeypatch.setattr(waf.server_mod, 'ssh_command', lambda *args, **kwargs: output)
    assert toggle(product_client, product, waf_switching).status_code == 500
    assert WafRules.get_by_id(waf_switching.rules['nginx'].id).en == 1


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_conflict_is_localized_and_never_reports_success(product_client, product, waf_switching, app, locale):
    product_client.set_cookie('lang', locale)
    entrypoint = waf_switching.entrypoints['nginx']
    entrypoint.write_text(entrypoint.read_text().replace('test.conf', '*.conf'))
    original = entrypoint.read_bytes()
    response = toggle(product_client, product, waf_switching)
    assert response.status_code == 409
    assert response.json['error'] == app.jinja_env.get_template(f'languages/{locale}.html').module.waf_toggle['conflict']
    assert WafRules.get_by_id(waf_switching.rules['nginx'].id).en == 1
    assert entrypoint.read_bytes() == original


@pytest.mark.parametrize('rejection', ['invalid_state', 'wrong_service', 'permission'])
def test_toggle_rejections_do_not_reach_ssh(product_client, product, waf_switching, monkeypatch, rejection):
    rule_id = waf_switching.rules['nginx'].id
    service, enabled, status = 'nginx', 0, 403
    if rejection == 'invalid_state':
        enabled, status = 2, 400
    elif rejection == 'wrong_service':
        service, status = 'haproxy', 404
    else:
        monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: False)
    response = product_client.post(f'/waf/{service}/{product.server.ip}/rule/{rule_id}/{enabled}')
    assert response.status_code == status
    assert not waf_switching.commands
    assert WafRules.get_by_id(rule_id).en == 1


def test_concurrent_opposite_requests_leave_database_matching_remote_file(app, product, waf_switching, monkeypatch):
    entered, release = Event(), Event()
    remote = waf.server_mod.ssh_command

    def hold_first(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return remote(*args, **kwargs)

    monkeypatch.setattr(waf.server_mod, 'ssh_command', hold_first)

    def request(enabled):
        with app.test_client() as client:
            assert client.post('/login', json={'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/admin'}).status_code == 200
            client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value
            client.environ_base['HTTP_ACCEPT'] = 'application/json'
            return toggle(client, product, waf_switching, enabled=enabled).status_code

    original = waf_switching.entrypoints['nginx'].read_bytes()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(request, 0)
        try:
            assert entered.wait(5)
            second = pool.submit(request, 1)
        finally:
            release.set()
        assert first.result(timeout=10) == second.result(timeout=10) == 200
    assert WafRules.get_by_id(waf_switching.rules['nginx'].id).en == 1
    assert waf_switching.entrypoints['nginx'].read_bytes() == original
