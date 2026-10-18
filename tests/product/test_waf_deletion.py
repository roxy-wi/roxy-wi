from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.modules.config import waf_state
from app.modules.db.db_model import WafRules
from app.modules.roxywi import waf


def delete(client, product, state, service='nginx'):
    return client.delete(f'/waf/{service}/{product.server.ip}/rule/{state.rules[service].id}')


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('enabled', [0, 1])
def test_delete_removes_only_selected_rule_and_requires_apply(product_client, product, waf_switching,
                                                             service, enabled):
    state = waf_switching
    rule = state.rules[service]
    other_service = 'haproxy' if service == 'nginx' else 'nginx'
    other_file = state.roots[other_service] / 'rules/test.conf'
    other_content = other_file.read_bytes()
    assert product_client.post(f'/waf/{service}/{product.server.ip}/rule/{rule.id}/{enabled}').status_code == 200
    response = delete(product_client, product, state, service)
    assert response.status_code == 200, response.text
    assert response.json == {'status': 'deleted', 'id': rule.id}
    assert not (state.roots[service] / 'rules/test.conf').exists()
    assert 'test.conf' not in state.entrypoints[service].read_text()
    assert not WafRules.get_or_none(WafRules.id == rule.id)
    assert WafRules.get_by_id(state.rules[other_service].id)
    assert other_file.read_bytes() == other_content
    assert waf_state.status(product.server.server_id, service) == 'pending'
    assert delete(product_client, product, state, service).status_code == 404


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('failure', ['fail_before', 'lose_response', 'database'])
def test_failed_delete_preserves_catalog_and_retry_finishes(product_client, product, waf_switching,
                                                           monkeypatch, service, failure):
    state = waf_switching
    remove = waf.waf_sql.delete_waf_rule
    if failure == 'database':
        def fail(*args):
            raise OSError('synthetic database failure')
        monkeypatch.setattr(waf.waf_sql, 'delete_waf_rule', fail)
    else:
        setattr(state, failure, True)
    response = delete(product_client, product, state, service)
    assert response.status_code == 500
    assert 'synthetic' not in response.text
    assert WafRules.get_by_id(state.rules[service].id)
    assert waf_state.status(product.server.server_id, service) == 'pending'
    state.fail_before = False
    monkeypatch.setattr(waf.waf_sql, 'delete_waf_rule', remove)
    assert delete(product_client, product, state, service).status_code == 200
    assert not (state.roots[service] / 'rules/test.conf').exists()
    assert not WafRules.get_or_none(WafRules.id == state.rules[service].id)


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_delete_conflict_is_localized(product_client, product, waf_switching, app, locale):
    product_client.set_cookie('lang', locale)
    entrypoint = waf_switching.entrypoints['nginx']
    entrypoint.write_text(entrypoint.read_text().replace('test.conf', '*.conf'))
    original = entrypoint.read_bytes()
    response = delete(product_client, product, waf_switching)
    assert response.status_code == 409
    assert response.json['error'] == app.jinja_env.get_template(f'languages/{locale}.html').module.waf_delete['conflict']
    assert entrypoint.read_bytes() == original
    assert (waf_switching.roots['nginx'] / 'rules/test.conf').is_file()
    assert WafRules.get_by_id(waf_switching.rules['nginx'].id)


def test_delete_rejects_shared_catalog_file_before_ssh(product_client, product, waf_switching):
    WafRules.create(serv=product.server.ip, service='nginx', rule_name='Shared', rule_file='test.conf', en=1)
    assert delete(product_client, product, waf_switching).status_code == 409
    assert not waf_switching.commands


def test_delete_and_concurrent_toggle_cannot_resurrect_rule(app, product, waf_switching, monkeypatch):
    entered, release = Event(), Event()
    remote = waf.server_mod.ssh_command

    def hold_delete(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return remote(*args, **kwargs)

    monkeypatch.setattr(waf.server_mod, 'ssh_command', hold_delete)

    def request(removing):
        with app.test_client() as client:
            assert client.post('/login', json={'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/admin'}).status_code == 200
            client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value
            client.environ_base['HTTP_ACCEPT'] = 'application/json'
            if removing:
                return delete(client, product, waf_switching).status_code
            return client.post(f'/waf/nginx/{product.server.ip}/rule/{waf_switching.rules["nginx"].id}/1').status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        removing = pool.submit(request, True)
        try:
            assert entered.wait(5)
            enabling = pool.submit(request, False)
        finally:
            release.set()
        assert removing.result(timeout=10) == 200
        assert enabling.result(timeout=10) == 404
    assert not (waf_switching.roots['nginx'] / 'rules/test.conf').exists()
    assert 'test.conf' not in waf_switching.entrypoints['nginx'].read_text()
