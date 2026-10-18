import importlib
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from threading import Event

import pytest

from app.modules.config import candidate, waf_state
from app.modules.db.db_model import Server, WafConfigState, WafRules
from app.modules.roxywi import auth, waf


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_restart_hint_only_describes_pending_changes(product_client, product, waf_applying, app, service, locale):
    product_client.set_cookie('lang', locale)
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module
    hint = messages.waf_mode['hint_' + service]
    state_url = f'/waf/{service}/{product.server.ip}/state'
    label = '<span data-waf-apply-label class="rw-change-state-label" title="'
    assert 'modsecurity.conf' not in hint
    assert label + messages.waf_apply['scope'] + '"' in unescape(product_client.get(state_url).text)

    saved = product_client.post(f'/waf/{service}/mode/{product.server.server_id}/DetectionOnly')
    assert saved.status_code == 200
    assert label + hint + '"' in unescape(product_client.get(state_url).text)
    overview = product_client.get(f'/waf/overview/{service}/{product.server.ip}')
    assert 'data-waf-mode-hint' not in overview.text
    assert label + hint + '"' in unescape(overview.text)

    applied = product_client.post(f'/waf/{service}/{product.server.ip}/apply', json={})
    assert applied.status_code == 200
    assert label + messages.waf_apply['scope'] + '"' in unescape(product_client.get(state_url).text)


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('service,failure,code,detail', [
    ('nginx', 'valid', 'validation_failed', None),
    ('nginx', 'action_failed', 'nginx_apply_failed', 'action_failed'),
    ('haproxy', 'ready', 'haproxy_apply_failed', 'agent_unready'),
])
def test_apply_reports_localized_failure_without_claiming_recovery(product_client, product, waf_applying,
                                                                  app, locale, service, failure, code, detail):
    product_client.set_cookie('lang', locale)
    setattr(waf_applying, failure, failure == 'action_failed')
    response = product_client.post(f'/waf/{service}/{product.server.ip}/apply', json={})
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module
    assert response.status_code == 500
    expected = messages.waf_apply[code]
    if detail:
        expected += ' ' + messages.waf_error_details[detail]
    assert response.json['error'] == expected
    assert waf_state.status(product.server.server_id, service) == 'pending'


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_all_waf_writes_remain_pending_until_a_confirmed_apply(product_client, product, waf_applying,
                                                            waf_switching, service):
    client, state, server = product_client, waf_applying, product.server
    apply_url = f'/waf/{service}/{server.ip}/apply'
    assert waf_state.status(server.server_id, service) == 'unknown'
    assert client.post(apply_url, json={}).status_code == 200
    assert waf_state.status(server.server_id, service) == 'applied'
    rule = waf_switching.rules[service]
    writes = [
        (f'/waf/{service}/mode/{server.server_id}/DetectionOnly', {}),
        (f'/waf/{service}/{server.ip}/rule/{rule.id}/0', {}),
        (f'/waf/{service}/{server.ip}/rule/create', {'new_waf_rule': 'New', 'new_rule_file': 'new.conf',
                                                   'new_rule_description': 'New rule'}),
        (f'/waf/{service}/{server.ip}/rule/{rule.id}/save', {'action': 'save', 'config': '# changed rule\n'}),
    ]
    for url, payload in writes:
        response = client.post(url, json=payload)
        assert response.status_code == 200, response.text
        assert waf_state.status(server.server_id, service) == 'pending'
        assert 'data-state="pending"' in client.get(f'/waf/{service}/{server.ip}/state').text
        assert client.post(apply_url, json={}).status_code == 200
        assert waf_state.status(server.server_id, service) == 'applied'
    assert waf_state.status(server.server_id, 'nginx' if service == 'haproxy' else 'haproxy') == 'unknown'
    assert state.apply_calls[-1]['apply_only'] is True
    assert state.apply_calls[-1]['candidate'] == ''
    assert state.apply_calls[-1]['action'] == ('restart' if service == 'haproxy' else 'reload')


@pytest.mark.parametrize('service,action', [('haproxy', 'restart'), ('nginx', 'reload')])
def test_save_and_apply_confirms_previously_pending_mode_and_rules(product_client, product, waf_applying,
                                                                waf_switching, service, action):
    client, server = product_client, product.server
    assert client.post(f'/waf/{service}/mode/{server.server_id}/Off').status_code == 200
    rule = waf_switching.rules[service]
    response = client.post(f'/waf/{service}/{server.ip}/rule/{rule.id}/save',
                           json={'action': action, 'config': '# all changes applied\n'})
    assert response.status_code == 200, response.text
    assert waf_state.status(server.server_id, service) == 'applied'


@pytest.mark.parametrize('service,action', [('haproxy', 'save'), ('haproxy', 'restart'),
                                          ('nginx', 'save'), ('nginx', 'reload')])
def test_rule_save_synchronizes_replicas_without_repeating_master(product_client, product, waf_applying,
                                                                waf_switching, monkeypatch, service, action):
    server = product.server
    # Existing installations can also contain a self-referencing master row.
    Server.update(master=server.server_id).where(Server.server_id == server.server_id).execute()
    replica = Server.create(hostname='Replica', ip='192.0.2.33', group_id='1', cred_id=11,
                            haproxy=1, nginx=1, master=server.server_id, description='WAF replica')
    roots = waf_applying.add_server(replica)
    rule = waf_switching.rules[service]
    WafRules.create(serv=replica.ip, service=service, rule_name=rule.rule_name, rule_file=rule.rule_file, en=rule.en)
    targets = []
    ssh = waf.server_mod.ssh_command

    def recorded(target, *args, **kwargs):
        targets.append(target)
        return ssh(target, *args, **kwargs)

    monkeypatch.setattr(waf.server_mod, 'ssh_command', recorded)
    response = product_client.post(f'/waf/{service}/{server.ip}/rule/{rule.id}/save',
                                   json={'action': action, 'config': '# synchronized rule\n'})
    assert response.status_code == 200, response.text
    assert set(targets) == {server.ip, replica.ip}
    assert waf_applying.apply_hosts == [server.ip, replica.ip]
    assert (waf_applying.roots[service] / 'rules/test.conf').read_text() == '# synchronized rule\n'
    assert (roots[service] / 'rules/test.conf').read_text() == '# synchronized rule\n'
    assert waf_state.status(server.server_id, service) == ('pending' if action == 'save' else 'applied')
    assert waf_state.status(replica.server_id, service) == ('pending' if action == 'save' else 'applied')


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('failure', ['apply_disconnected', 'apply_lost', 'action_failed', 'invalid_result'])
def test_failed_or_unconfirmed_apply_never_clears_pending_changes(product_client, product, waf_applying, service, failure):
    client, state, server = product_client, waf_applying, product.server
    url = f'/waf/{service}/{server.ip}/apply'
    assert client.post(url, json={}).status_code == 200
    if failure == 'invalid_result':
        state.apply_response = 'null'
    else:
        setattr(state, failure, True)
    response = client.post(url, json={})
    assert response.status_code == 500
    assert waf_state.status(server.server_id, service) == 'pending'
    assert 'synthetic' not in response.text
    state.apply_response = None
    state.apply_disconnected = state.action_failed = False
    assert client.post(url, json={}).status_code == 200
    assert waf_state.status(server.server_id, service) == 'applied'


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_validation_or_readiness_failure_keeps_saved_files_and_pending_state(product_client, product,
                                                                           waf_applying, service):
    state = waf_applying
    state.valid = state.ready = False
    original = (state.roots[service] / 'modsecurity.conf').read_bytes()
    response = product_client.post(f'/waf/{service}/{product.server.ip}/apply', json={})
    assert response.status_code == 500
    assert (state.roots[service] / 'modsecurity.conf').read_bytes() == original
    assert waf_state.status(product.server.server_id, service) == 'pending'


def test_lost_write_response_invalidates_previous_apply(product_client, product, waf_applying):
    assert product_client.post(f'/waf/nginx/{product.server.ip}/apply', json={}).status_code == 200
    waf_applying.lose_response = True
    assert product_client.post(f'/waf/nginx/mode/{product.server.server_id}/Off').status_code == 500
    assert waf_state.status(product.server.server_id, 'nginx') == 'pending'
    assert (waf_applying.roots['nginx'] / 'modsecurity.conf').read_text() == 'SecRuleEngine Off\n'


def test_newer_revision_is_never_cleared_by_an_older_confirmation(product_client, product, waf_applying, monkeypatch):
    check = candidate.check_result

    def concurrent_change(output):
        check(output)
        WafConfigState.update(revision='newer').execute()

    monkeypatch.setattr(candidate, 'check_result', concurrent_change)
    assert product_client.post(f'/waf/nginx/{product.server.ip}/apply', json={}).status_code == 500
    assert waf_state.status(product.server.server_id, 'nginx') == 'pending'


def test_apply_and_mode_save_are_serialized_and_later_save_stays_pending(app, product, waf_applying, monkeypatch):
    entered, release, mode_attempted = Event(), Event(), Event()
    ssh = waf.server_mod.ssh_command

    def held(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return ssh(*args, **kwargs)

    monkeypatch.setattr(waf.server_mod, 'ssh_command', held)

    def post(url, saving=False):
        with app.test_client() as client:
            assert client.post('/login', json={'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/admin'}).status_code == 200
            client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value
            if saving:
                mode_attempted.set()
            return client.post(url, json={}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        apply = pool.submit(post, f'/waf/nginx/{product.server.ip}/apply')
        try:
            assert entered.wait(5)
            mode = pool.submit(post, f'/waf/nginx/mode/{product.server.server_id}/Off', True)
            assert mode_attempted.wait(5)
            assert not waf_applying.commands
        finally:
            release.set()
        assert apply.result(timeout=10) == mode.result(timeout=10) == 200
    assert waf_state.status(product.server.server_id, 'nginx') == 'pending'


@pytest.mark.parametrize('endpoint', ['apply', 'state'])
@pytest.mark.parametrize('rejection', ['service', 'other_group'])
def test_permission_failure_does_not_reach_state_or_ssh(product_client, product, waf_applying, monkeypatch, endpoint, rejection):
    server = product.server
    if rejection == 'service':
        monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: False)
    else:
        server = product.other
    url = f'/waf/nginx/{server.ip}/{endpoint}'
    response = product_client.post(url, json={}) if endpoint == 'apply' else product_client.get(url)
    assert response.status_code == 403
    assert WafConfigState.select().count() == 0
    assert not waf_applying.apply_calls


def test_apply_requires_csrf_token(product_client, product, waf_applying):
    del product_client.environ_base['HTTP_X_CSRF_TOKEN']
    assert product_client.post(f'/waf/nginx/{product.server.ip}/apply', json={}).status_code == 401
    assert not waf_applying.apply_calls
    assert WafConfigState.select().count() == 0


def test_failed_revision_reservation_prevents_remote_apply(product_client, product, waf_applying, monkeypatch):
    def unavailable(**kwargs):
        raise OSError('synthetic database write failure')

    monkeypatch.setattr(WafConfigState, 'get_or_create', unavailable)
    response = product_client.post(f'/waf/nginx/{product.server.ip}/apply', json={})
    assert response.status_code == 500
    assert not waf_applying.apply_calls
    assert WafConfigState.select().count() == 0


def test_state_migration_is_repeatable_and_does_not_invent_an_applied_baseline(product):
    migration = importlib.import_module('app.modules.db.migrations.20261012000000_waf_config_state')
    migration.down()
    migration.up()
    assert waf_state.status(product.server.server_id, 'nginx') == 'unknown'
    with waf_state.track_changes(product.server.server_id, 'nginx'):
        pass
    migration.up()
    assert waf_state.status(product.server.server_id, 'nginx') == 'pending'
    product.db.close()
    product.db.connect()
    assert waf_state.status(product.server.server_id, 'nginx') == 'pending'
