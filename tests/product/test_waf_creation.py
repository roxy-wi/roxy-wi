from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.modules.db.db_model import WafRules
from app.modules.roxywi import auth, waf


PAYLOAD = {'new_waf_rule': 'Правило & règle <test>', 'new_rule_description': "Protection d'aujourd’hui · 规则",
           'new_rule_file': 'custom-rule'}


def create(client, product, service='nginx', payload=None):
    return client.post(f'/waf/{service}/{product.server.ip}/rule/create', json=PAYLOAD if payload is None else payload)


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_create_and_retry_keep_one_file_include_and_row(product_client, product, waf_creation, service):
    response = create(product_client, product, service)
    assert response.status_code == 200, response.text
    rule = WafRules.get_by_id(response.json['id'])
    assert (rule.serv, rule.service, rule.rule_name, rule.desc, rule.rule_file) == (
        product.server.ip, service, PAYLOAD['new_waf_rule'], PAYLOAD['new_rule_description'], 'custom-rule.conf')
    root = waf_creation.roots[service]
    entrypoint = root / 'modsecurity.conf'
    assert entrypoint.read_text().count('custom-rule.conf') == 1
    assert waf_creation.commands[0][1][:2] == [
        f'/srv/{service} custom/waf/{entrypoint.name}', f'/srv/{service} custom/waf/rules/custom-rule.conf']
    # A repeat must not re-enable or overwrite a rule already edited by the user.
    rule.en = 0
    rule.save()
    (root / 'rules/custom-rule.conf').write_text('# edited after creation\n')
    retry = create(product_client, product, service, {**PAYLOAD, 'new_rule_file': 'custom-rule.conf'})
    assert retry.json == response.json
    assert WafRules.select().count() == 1
    assert WafRules.get_by_id(rule.id).en == 0
    assert len(waf_creation.commands) == 1
    assert (root / 'rules/custom-rule.conf').read_text() == '# edited after creation\n'
    assert product_client.get(response.json['edit_url']).status_code == 200


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('failure', ['fail_before', 'lose_response', 'database'])
def test_failed_creation_can_resume_without_duplicates(product_client, product, waf_creation, monkeypatch, service, failure):
    insert = waf.waf_sql.insert_new_waf_rule
    if failure == 'database':
        def unavailable(*args):
            raise OSError('synthetic database failure')
        monkeypatch.setattr(waf.waf_sql, 'insert_new_waf_rule', unavailable)
    else:
        setattr(waf_creation, failure, True)
    response = create(product_client, product, service)
    assert response.status_code == 500
    assert 'synthetic' not in response.text
    assert WafRules.select().count() == 0
    waf_creation.fail_before = False
    monkeypatch.setattr(waf.waf_sql, 'insert_new_waf_rule', insert)
    response = create(product_client, product, service)
    assert response.status_code == 200, response.text
    assert WafRules.select().count() == 1
    root = waf_creation.roots[service]
    assert len(list((root / 'rules').iterdir())) == 1
    assert sum(path.read_text().count('custom-rule.conf') for path in root.glob('*.conf')) == 1


@pytest.mark.parametrize('field,value', [
    ('new_waf_rule', ''), ('new_waf_rule', 42), ('new_waf_rule', 'x' * 256),
    ('new_rule_description', None), ('new_rule_description', 'x' * 4097),
    ('new_rule_file', '../outside'), ('new_rule_file', '/tmp/outside'), ('new_rule_file', 'name;touch owned'),
    ('new_rule_file', 'a b'), ('new_rule_file', 'a\\b'), ('new_rule_file', 'правило'),
    ('new_rule_file', 'a\n.conf'), ('new_rule_file', 'a' * 251), ('new_rule_file', '.conf'),
])
def test_invalid_creation_has_no_side_effects(product_client, product, waf_creation, field, value):
    response = create(product_client, product, payload={**PAYLOAD, field: value})
    assert response.status_code == 400, response.text
    assert not waf_creation.commands
    assert WafRules.select().count() == 0


@pytest.mark.parametrize('payload', [[], 'text', 1])
def test_invalid_json_type_is_bad_request(product_client, product, waf_creation, payload):
    assert create(product_client, product, payload=payload).status_code == 400
    assert not waf_creation.commands


@pytest.mark.parametrize('field,value', [
    ('new_waf_rule', 'Different name'), ('new_rule_file', 'different-file'),
    ('new_rule_description', 'Different description'),
])
def test_duplicate_name_or_file_is_a_conflict(product_client, product, waf_creation, field, value):
    assert create(product_client, product).status_code == 200
    assert create(product_client, product, payload={**PAYLOAD, field: value}).status_code == 409
    assert len(waf_creation.commands) == 1
    assert WafRules.select().count() == 1


def test_foreign_remote_file_is_not_overwritten_or_registered(product_client, product, waf_creation):
    rule = waf_creation.roots['nginx'] / 'rules/custom-rule.conf'
    rule.write_text('# existing customer rule\n')
    response = create(product_client, product)
    assert response.status_code == 409
    assert rule.read_text() == '# existing customer rule\n'
    assert WafRules.select().count() == 0


def test_service_permission_is_checked_before_ssh(product_client, product, waf_creation, monkeypatch):
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda service: False)
    assert create(product_client, product).status_code == 403
    assert not waf_creation.commands


def test_same_name_and_file_are_independent_for_each_service(product_client, product, waf_creation):
    responses = [create(product_client, product, service) for service in ('haproxy', 'nginx')]
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json['id'] != responses[1].json['id']


@pytest.mark.parametrize('same_filename', [True, False])
def test_concurrent_requests_do_not_create_duplicate_names(app, product, waf_creation, same_filename):
    ready = Barrier(2, timeout=15)

    def request(index):
        with app.test_client() as client:
            login = client.post('/login', json={'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/admin'})
            assert login.status_code == 200
            client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value
            client.environ_base['HTTP_ACCEPT'] = 'application/json'
            ready.wait()
            payload = dict(PAYLOAD)
            if not same_filename and index:
                payload['new_rule_file'] = 'other-file'
            response = create(client, product, payload=payload)
            return response.status_code, response.json

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, range(2)))
    assert sorted(status for status, body in results) == ([200, 200] if same_filename else [200, 409])
    if same_filename:
        assert results[0][1]['id'] == results[1][1]['id']
    assert WafRules.select().count() == 1
    assert len(waf_creation.commands) == 1
    assert len(list((waf_creation.roots['nginx'] / 'rules').iterdir())) == 1


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_creation_failure_is_localized(product_client, product, waf_creation, app, locale):
    product_client.set_cookie('lang', locale)
    waf_creation.fail_before = True
    response = create(product_client, product)
    message = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_create['failed']
    assert response.status_code == 500
    assert response.json['error'] == message
