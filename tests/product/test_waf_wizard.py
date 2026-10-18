from concurrent.futures import ThreadPoolExecutor
import json
import re

import pytest

from app.modules.config import waf_wizard, waf_state
from app.modules.db.db_model import Server, Waf, WafNginx, WafRules
from app.modules.roxywi import common, auth


LOCALES = ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh']


def payload(**spec):
    return dict(new_waf_rule='Generated rule', new_rule_file='generated.conf', new_rule_description='Wizard test',
                action='save', spec={**waf_wizard.DEFAULT, 'value': '/admin', **spec})


def url(product, service='nginx', rule_id=None):
    prefix = f'/waf/{service}/{product.server.ip}'
    return prefix + (f'/rule/{rule_id}' if rule_id else '') + '/wizard'


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('kind', ['rule', 'exclusion'])
def test_preview_save_reopen_edit_and_apply_use_existing_pipeline(product_client, product, wizard_host, service, kind):
    body = payload(kind=kind, exclude_id=942100)
    endpoint = url(product, service)
    response = product_client.post(endpoint, json={**body, 'action': 'preview'})
    assert response.status_code == 200, response.text
    assert response.json['previous'] == ''
    assert 'Roxy-WI MANAGED' in response.json['config']
    assert WafRules.select().count() == 0
    assert not wizard_host.apply_calls and not wizard_host.uploads
    response = product_client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    rule = WafRules.get_by_id(response.json['id'])
    assert rule.wizard
    assert response.json['edit_url'] == url(product, service, rule.id)
    target = wizard_host.roots[service] / 'rules/generated.conf'
    assert waf_wizard.read_spec(target.read_text())['kind'] == kind
    assert waf_state.status(product.server.server_id, service) == 'pending'
    entry = wizard_host.roots[service] / ('waf.conf' if service == 'nginx' else 'modsecurity.conf')
    assert entry.read_text().index('generated.conf') < entry.read_text().index('crs.conf')
    edit_url = response.json['edit_url']
    response = product_client.get(edit_url)
    assert response.status_code == 200 and 'id="waf-wizard"' in response.text
    assert 'value="/admin"' in response.text
    raw_url = edit_url.removesuffix('/wizard')
    assert product_client.get(raw_url).location.endswith(edit_url)
    response = product_client.post(raw_url + '/save', json={'action': 'save', 'config': '# bypass'})
    assert response.status_code == 409
    body['spec']['value'] = '/changed'
    body['action'] = 'restart' if service == 'haproxy' else 'reload'
    response = product_client.post(edit_url, json=body)
    assert response.status_code == 200, response.text
    assert waf_state.status(product.server.server_id, service) == 'applied'
    assert waf_wizard.read_spec(target.read_text())['value'] == '/changed'
    assert wizard_host.apply_calls[-1]['action'] == body['action']


@pytest.mark.parametrize('plan,status,allowed', [
    ('user', 1, False), ('Trial', 1, False), ('', 1, False), ('company', 1, True),
    ('cloud', 1, True), ('support', 1, True), ('company', 0, False), ('support', 0, False),
])
def test_page_preview_and_write_require_active_enterprise(product_client, product, wizard_host, monkeypatch,
                                                         plan, status, allowed):
    monkeypatch.setattr(common, 'return_user_subscription', lambda: {'user_status': status, 'user_plan': plan})
    response = product_client.get(url(product))
    assert response.status_code == (200 if allowed else 403), response.text
    for action in ('preview', 'save'):
        response = product_client.post(url(product), json={**payload(), 'action': action})
        assert response.status_code == (200 if allowed else 403), response.text
    if not allowed:
        assert not wizard_host.commands and not wizard_host.apply_calls
        assert WafRules.select().count() == 0


def test_downgrade_cannot_edit_existing_managed_rule_via_raw_or_wizard(product_client, product, wizard_host, monkeypatch):
    response = product_client.post(url(product), json=payload())
    edit_url = response.json['edit_url']
    monkeypatch.setattr(common, 'return_user_subscription', lambda: {'user_status': 1, 'user_plan': 'user'})
    assert product_client.post(edit_url, json=payload()).status_code == 403
    assert product_client.post(edit_url.removesuffix('/wizard') + '/save',
                               json={'action': 'save', 'config': '# bypass'}).status_code == 409
    assert len(wizard_host.apply_calls) == 1


@pytest.mark.parametrize('locale', LOCALES)
def test_localized_form_and_field_errors(product_client, product, wizard_host, app, locale):
    product_client.set_cookie('lang', locale)
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_wizard
    assert set(messages) == set(app.jinja_env.get_template('languages/en.html').module.waf_wizard)
    response = product_client.get(url(product))
    assert response.status_code == 200 and messages['title'] in response.text
    response = product_client.post(url(product), json=payload(id=942100))
    assert response.status_code == 400 and response.json['error'] == messages['invalid']
    assert not wizard_host.apply_calls


def test_colliding_id_and_missing_exclusion_target_are_rejected(product_client, product, wizard_host):
    reserved = wizard_host.roots['nginx'] / 'rules/disabled.conf'
    reserved.write_text('SecAction "id:10000,phase:1,pass"\n')
    response = product_client.post(url(product), json=payload())
    assert response.status_code == 400 and 'already used' in response.json['error']
    response = product_client.post(url(product), json=payload(id=10001, kind='exclusion', exclude_id=999999))
    assert response.status_code == 400 and 'not found' in response.json['error']
    assert WafRules.select().count() == 0 and not wizard_host.apply_calls


def test_lost_save_reply_retries_same_file_without_duplicate_include(product_client, product, wizard_host):
    wizard_host.apply_lost = True
    response = product_client.post(url(product), json=payload())
    assert response.status_code == 500
    response = product_client.post(url(product), json=payload())
    assert response.status_code == 200, response.text
    assert WafRules.select().count() == 1
    assert (wizard_host.roots['nginx'] / 'waf.conf').read_text().count('generated.conf') == 1


def test_failed_reload_restores_generated_file_and_form_metadata(product_client, product, wizard_host):
    response = product_client.post(url(product), json=payload())
    endpoint = response.json['edit_url']
    target = wizard_host.roots['nginx'] / 'rules/generated.conf'
    before = target.read_text()
    wizard_host.action_failed = True
    response = product_client.post(endpoint, json={**payload(value='/changed'), 'action': 'reload'})
    assert response.status_code == 500
    assert target.read_text() == before
    assert waf_state.status(product.server.server_id, 'nginx') == 'pending'


def test_manual_rule_stays_in_text_editor(product_client, product, wizard_host):
    response = product_client.post(f'/waf/nginx/{product.server.ip}/rule/create', json=payload())
    rule_id = response.json['id']
    assert not WafRules.get_by_id(rule_id).wizard
    assert 'data-waf-editor' in product_client.get(response.json['edit_url']).text
    assert product_client.get(url(product, rule_id=rule_id)).status_code == 400


def test_service_permission_and_rule_ownership_checked_before_remote_io(product_client, product, wizard_host, monkeypatch):
    rule = WafRules.create(serv=product.other.ip, service='nginx', rule_name='Private', rule_file='private.conf', wizard=True)
    assert product_client.post(url(product, rule_id=rule.id), json=payload()).status_code == 404
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda service: False)
    assert product_client.post(url(product), json=payload()).status_code == 403
    assert not wizard_host.commands and not wizard_host.apply_calls


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_server_choices_only_include_permitted_enabled_waf_hosts(product_client, product, wizard_host, waf_cluster, service):
    slave, _ = waf_cluster
    model = Waf if service == 'haproxy' else WafNginx
    extra = {'metrics': 0} if service == 'haproxy' else {}
    model.create(server_id=slave.server_id, **extra)
    model.create(server_id=product.other.server_id, **extra)
    for index, flags in enumerate(({'enabled': 0}, {service: 0}, {}), start=40):
        server = Server.create(server_id=index, hostname=f'Excluded {index}', ip=f'192.0.2.{index}',
                               group_id='1', cred_id=11, **{'haproxy': 1, 'nginx': 1, **flags})
        if flags:
            model.create(server_id=server.server_id, **extra)
    response = product_client.get(url(product, service=service))
    assert response.status_code == 200, response.text
    targets = json.loads(re.search(r'id="wizard-server-targets"[^>]*>(.*?)</script>', response.text, re.S)[1])
    assert set(targets) == {product.server.ip, slave.ip}
    assert targets[product.server.ip]['sync'] is True
    assert targets[slave.ip]['sync'] is False
    assert not wizard_host.commands


def test_concurrent_creations_cannot_reserve_same_id_in_different_files(app, product, wizard_host):
    def create(index):
        with app.test_client() as client:
            assert client.post('/login', json={'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/admin'}).status_code == 200
            client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value
            body = payload()
            body.update(new_waf_rule=f'Rule {index}', new_rule_file=f'generated-{index}.conf')
            return client.post(url(product), json=body).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, range(2)))
    assert sorted(results) == [200, 400]
    assert WafRules.select().count() == 1
