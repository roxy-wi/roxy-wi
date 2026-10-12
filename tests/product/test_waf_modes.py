from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.modules.roxywi import auth, waf


LOCALES = ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh']


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('mode', ['On', 'Off', 'DetectionOnly'])
def test_mode_save_is_service_scoped_and_idempotent(product_client, product, waf_modes, service, mode):
    path = waf_modes.roots[service] / 'modsecurity.conf'
    other = waf_modes.roots['nginx' if service == 'haproxy' else 'haproxy'] / 'modsecurity.conf'
    other_contents = other.read_bytes()
    original = path.read_bytes()
    url = f'/waf/{service}/mode/{product.server.server_id}/{mode}'
    response = product_client.post(url)
    assert response.status_code == 200 and response.json == {'status': 'Ok', 'mode': mode}
    assert path.read_bytes() == original.replace(b'On', mode.encode())
    modified = path.stat().st_mtime_ns
    assert product_client.post(url).status_code == 200
    assert path.stat().st_mtime_ns == modified
    assert other.read_bytes() == other_contents
    assert all(args == ['set-mode', f'/srv/{service} custom/waf/modsecurity.conf', mode]
               for _, args in waf_modes.commands)


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('failure', ['fail_before', 'lose_response'])
def test_failed_mode_save_can_be_retried_without_false_success(product_client, product, waf_modes, service, failure):
    setattr(waf_modes, failure, True)
    path = waf_modes.roots[service] / 'modsecurity.conf'
    url = f'/waf/{service}/mode/{product.server.server_id}/DetectionOnly'
    response = product_client.post(url)
    assert response.status_code == 500 and response.json['status'] == 'failed'
    assert 'synthetic' not in response.text
    assert path.read_text() == ('SecRuleEngine On\n' if failure == 'fail_before' else 'SecRuleEngine DetectionOnly\n')
    waf_modes.fail_before = False
    assert product_client.post(url).status_code == 200
    assert path.read_text() == 'SecRuleEngine DetectionOnly\n'


@pytest.mark.parametrize('output', ['', 'null', '{"status":"ok"}', '{"status":"ok","mode":"On"}', 'not JSON'])
def test_unconfirmed_result_is_never_success(product_client, product, waf_modes, monkeypatch, output):
    monkeypatch.setattr(waf.server_mod, 'ssh_command', lambda *a, **kw: output)
    response = product_client.post(f'/waf/haproxy/mode/{product.server.server_id}/Off')
    assert response.status_code == 500 and response.json['status'] == 'failed'


@pytest.mark.parametrize('locale', LOCALES)
def test_ambiguous_mode_returns_localized_conflict_and_preserves_file(product_client, product, waf_modes, app, locale):
    product_client.set_cookie('lang', locale)
    path = waf_modes.roots['nginx'] / 'modsecurity.conf'
    content = b'SecRuleEngine On\nSecRuleEngine Off\n'
    path.write_bytes(content)
    response = product_client.post(f'/waf/nginx/mode/{product.server.server_id}/DetectionOnly')
    assert response.status_code == 409
    assert response.json['error'] == app.jinja_env.get_template(f'languages/{locale}.html').module.waf_mode['conflict']
    assert path.read_bytes() == content


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('failure', ['ambiguous', 'connection'])
def test_unreadable_mode_is_not_rendered_as_uninstalled(product_client, product, waf_modes, service, failure):
    if failure == 'ambiguous':
        (waf_modes.roots[service] / 'modsecurity.conf').write_bytes(b'# no explicit mode\n')
    else:
        waf_modes.fail_before = True
    response = product_client.get(f'/waf/overview/{service}/{product.server.ip}')
    assert response.status_code == 200
    assert 'data-confirmed-mode="" disabled' in response.text
    assert 'Cannot read a single configured mode' in response.text
    assert 'installWaf(' not in response.text


@pytest.mark.parametrize('rejection', ['permission', 'other_group', 'invalid_mode'])
def test_rejected_mode_changes_do_not_reach_ssh(product_client, product, waf_modes, monkeypatch, rejection):
    server, mode, status = product.server.server_id, 'Off', 403
    if rejection == 'permission':
        monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: False)
    elif rejection == 'other_group':
        server = product.other.server_id
    else:
        mode, status = 'invalid', 404
    response = product_client.post(f'/waf/nginx/mode/{server}/{mode}')
    assert response.status_code == status
    assert not waf_modes.commands


def test_mode_change_and_rule_toggle_share_the_operation_lock(app, product, waf_modes, waf_switching, monkeypatch):
    entered, release = Event(), Event()
    ssh = waf.server_mod.ssh_command

    def held(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return ssh(*args, **kwargs)

    monkeypatch.setattr(waf.server_mod, 'ssh_command', held)

    def post(url):
        with app.test_client() as client:
            assert client.post('/login', json={'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/admin'}).status_code == 200
            client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value
            client.environ_base['HTTP_ACCEPT'] = 'application/json'
            return client.post(url).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        mode = pool.submit(post, f'/waf/haproxy/mode/{product.server.server_id}/DetectionOnly')
        try:
            assert entered.wait(5)
            toggle = pool.submit(post, f'/waf/haproxy/{product.server.ip}/rule/{waf_switching.rules["haproxy"].id}/0')
        finally:
            release.set()
        assert mode.result(timeout=10) == toggle.result(timeout=10) == 200
    text = (waf_modes.roots['haproxy'] / 'modsecurity.conf').read_text()
    assert text.startswith('SecRuleEngine DetectionOnly\n')
    assert '# Include ' in text
