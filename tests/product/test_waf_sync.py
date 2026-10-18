"""Master/Slave routes exercise real file helpers, catalog and candidate transactions."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.modules.config import waf_state, waf_wizard
from app.modules.db.db_model import Server, WafRules
from app.modules.roxywi import waf


def body(name='generated', **changes):
    spec = dict(version=2, id=None, kind='rule', action='deny', match='all', exclude_id=0,
                exclude_parameter='', conditions=[
                    dict(field='uri', key='', operator='equals', value='/admin'),
                    dict(field='method', key='', operator='equals', value='POST'),
                ])
    spec.update(changes)
    return dict(new_waf_rule=name, new_rule_file=name + '.conf', new_rule_description='Cluster rule',
                action='save', spec=spec)


def wizard_url(product, service):
    return f'/waf/{service}/{product.server.ip}/wizard'


def assert_include(root, service, filename, enabled):
    entry = root / ('modsecurity.conf' if service == 'haproxy' else 'waf.conf')
    lines = [line for line in entry.read_text().splitlines() if filename in line]
    assert len(lines) == 1
    assert lines[0].startswith('# ') is not bool(enabled)


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('match', ['all', 'any'])
def test_create_edit_toggle_apply_delete_are_synchronized(product_client, product, wizard_host, waf_cluster, service, match):
    slave, roots = waf_cluster
    payload = body(match=match)
    response = product_client.post(wizard_url(product, service), json=payload)
    assert response.status_code == 200, response.text
    endpoint, identifier = response.json['edit_url'], response.json['id']
    source_path = wizard_host.roots[service] / 'rules/generated.conf'
    replica_path = roots[service] / 'rules/generated.conf'
    assert source_path.read_bytes() == replica_path.read_bytes()
    replica = WafRules.get(WafRules.serv == slave.ip, WafRules.service == service)
    assert replica.wizard and replica.en == 1
    assert response.json['rule_ids'] == ([10000] if match == 'all' else [10000, 10001])
    payload['spec']['conditions'][0]['value'] = '/changed'
    response = product_client.post(endpoint, json=payload)
    assert response.status_code == 200, response.text
    assert '/changed' in replica_path.read_text() and source_path.read_bytes() == replica_path.read_bytes()
    for enabled in (0, 0, 1):
        response = product_client.post(f'/waf/{service}/{product.server.ip}/rule/{identifier}/{enabled}')
        assert response.status_code == 200, response.text
        for node, root in ((product.server, wizard_host.roots[service]), (slave, roots[service])):
            assert_include(root, service, 'generated.conf', enabled)
            assert waf_state.status(node.server_id, service) == 'pending'
        assert WafRules.get_by_id(replica.id).en == enabled
    response = product_client.post(f'/waf/{service}/{product.server.ip}/apply')
    assert response.status_code == 200, response.text
    for node in (product.server, slave):
        assert waf_state.status(node.server_id, service) == 'applied'
    response = product_client.delete(endpoint.removesuffix('/wizard'))
    assert response.status_code == 200, response.text
    assert not source_path.exists() and not replica_path.exists()
    assert not WafRules.select().exists()


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_auto_ids_reserve_whole_or_block_on_all_nodes(product_client, product, wizard_host, waf_cluster, service):
    _, roots = waf_cluster
    (roots[service] / 'rules/slave-only.conf').write_text('SecAction "id:10001,phase:1,pass"\n')
    payload = body(match='any')
    preview = product_client.post(wizard_url(product, service), json={**payload, 'action': 'preview'})
    assert preview.status_code == 200 and preview.json['rule_ids'] == [10002, 10003], preview.text
    assert not WafRules.select().exists() and not wizard_host.apply_calls
    # Another rule is saved between preview and submit; the preview is no reservation.
    (wizard_host.roots[service] / 'rules/new.conf').write_text('SecAction "id:10002,phase:1,pass"\n')
    response = product_client.post(wizard_url(product, service), json=payload)
    assert response.status_code == 200 and response.json['rule_ids'] == [10003, 10004], response.text


def test_manual_id_conflict_on_slave_is_rejected_before_any_write(product_client, product, wizard_host, waf_cluster):
    _, roots = waf_cluster
    (roots['nginx'] / 'rules/slave-only.conf').write_text('SecAction "id:10001,phase:1,pass"\n')
    response = product_client.post(wizard_url(product, 'nginx'), json=body(match='any', id=10000))
    assert response.status_code == 400, response.text
    assert not WafRules.select().exists() and not wizard_host.apply_calls


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_manual_editor_replicates_content_and_disabled_include(product_client, product, wizard_host, waf_cluster, service):
    slave, roots = waf_cluster
    payload = body()
    response = product_client.post(f'/waf/{service}/{product.server.ip}/rule/create', json=payload)
    assert response.status_code == 200, response.text
    endpoint = response.json['edit_url']
    assert product_client.post(endpoint + '/0').status_code == 200
    response = product_client.post(endpoint + '/save', json={'action': 'save', 'config': '# manual rule\n'})
    assert response.status_code == 200, response.text
    assert (roots[service] / 'rules/generated.conf').read_text() == '# manual rule\n'
    assert_include(roots[service], service, 'generated.conf', False)
    assert not WafRules.get(WafRules.serv == slave.ip, WafRules.service == service).wizard


@pytest.mark.parametrize('operation', ['toggle', 'delete', 'save', 'apply'])
def test_partial_failure_names_slave_and_can_be_retried(product_client, product, wizard_host, waf_cluster, operation):
    slave, roots = waf_cluster
    response = product_client.post(wizard_url(product, 'nginx'), json=body())
    endpoint = response.json['edit_url'].removesuffix('/wizard')

    def run():
        if operation == 'toggle':
            return product_client.post(endpoint + '/0')
        if operation == 'delete':
            return product_client.delete(endpoint)
        if operation == 'apply':
            return product_client.post(f'/waf/nginx/{product.server.ip}/apply')
        return product_client.post(endpoint + '/wizard', json=body())

    wizard_host.failed_hosts.add(slave.ip)
    response = run()
    assert response.status_code == 500 and slave.ip in response.json['error'], response.text
    assert 'synthetic' not in response.text
    wizard_host.failed_hosts.clear()
    response = run()
    assert response.status_code == 200, response.text
    if operation == 'delete':
        assert not WafRules.select().exists()
    elif operation == 'toggle':
        assert_include(roots['nginx'], 'nginx', 'generated.conf', False)
    else:
        assert (roots['nginx'] / 'rules/generated.conf').read_bytes() == (
            wizard_host.roots['nginx'] / 'rules/generated.conf').read_bytes()


def test_lost_slave_upload_reply_preserves_auto_ids_on_create_retry(product_client, product, wizard_host, waf_cluster):
    slave, roots = waf_cluster
    wizard_host.lost_apply_hosts.add(slave.ip)
    response = product_client.post(wizard_url(product, 'nginx'), json=body(match='any'))
    assert response.status_code == 500 and slave.ip in response.json['error'], response.text
    response = product_client.post(wizard_url(product, 'nginx'), json=body(match='any'))
    assert response.status_code == 200 and response.json['rule_ids'] == [10000, 10001], response.text
    assert WafRules.select().count() == 2
    assert_include(roots['nginx'], 'nginx', 'generated.conf', True)
    assert waf_state.status(slave.server_id, 'nginx') == 'pending'


def test_apply_retries_file_sync_before_restarting(product_client, product, wizard_host, waf_cluster):
    slave, roots = waf_cluster
    wizard_host.failed_apply_hosts.add(slave.ip)
    response = product_client.post(wizard_url(product, 'nginx'), json=body())
    assert response.status_code == 500, response.text
    assert (roots['nginx'] / 'rules/generated.conf').read_text().startswith('# Roxy-WI rule creation:')
    wizard_host.failed_apply_hosts.clear()
    response = product_client.post(f'/waf/nginx/{product.server.ip}/apply')
    assert response.status_code == 200, response.text
    assert waf_wizard.read_spec((roots['nginx'] / 'rules/generated.conf').read_text())['id'] == 10000
    assert waf_state.status(slave.server_id, 'nginx') == 'applied'


def test_direct_slave_edit_does_not_write_to_master(product_client, product, wizard_host, waf_cluster):
    slave, _ = waf_cluster
    endpoint = f'/waf/nginx/{slave.ip}/wizard'
    response = product_client.post(endpoint, json=body())
    assert response.status_code == 200, response.text
    assert not (wizard_host.roots['nginx'] / 'rules/generated.conf').exists()
    assert {host for host, _ in wizard_host.commands} == {slave.ip}


@pytest.mark.parametrize('problem', ['foreign_group', 'disabled_service'])
def test_invalid_slave_topology_rejects_before_io(product_client, product, wizard_host, waf_cluster, problem):
    slave, _ = waf_cluster
    if problem == 'foreign_group':
        slave.group_id = 2
    else:
        slave.nginx = 0
    slave.save()
    response = product_client.post(wizard_url(product, 'nginx'), json=body())
    assert response.status_code == 500, response.text
    assert not wizard_host.commands and not wizard_host.apply_calls and not WafRules.select().exists()


def test_concurrent_auto_creation_allocates_distinct_ids_and_replicas(app, product, wizard_host, waf_cluster):
    def create(index):
        with app.test_client() as client:
            assert client.post('/login', json={'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/admin'}).status_code == 200
            client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value
            response = client.post(wizard_url(product, 'nginx'), json=body(name=f'parallel-{index}', match='any'))
            assert response.status_code == 200, response.text
            return response.json['rule_ids']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, range(2)))
    assert sorted(results) == [[10000, 10001], [10002, 10003]]
    assert WafRules.select().count() == 4


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_sync_failures_are_localized_and_keep_pending_state(product_client, product, wizard_host, waf_cluster, app, locale):
    slave, _ = waf_cluster
    product_client.set_cookie('lang', locale)
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_sync
    assert set(messages) == set(app.jinja_env.get_template('languages/en.html').module.waf_sync)
    wizard_host.failed_apply_hosts.add(slave.ip)
    response = product_client.post(wizard_url(product, 'nginx'), json=body())
    assert response.status_code == 500 and response.json['error'] == messages['failed'].format(server=slave.ip)
    for node in (product.server, slave):
        assert waf_state.status(node.server_id, 'nginx') == 'pending'


def test_second_slave_receives_rule_without_duplicate_catalog_entries(product_client, product, wizard_host, waf_cluster):
    second = Server.create(server_id=44, hostname='Second Slave', ip='192.0.2.44', group_id='1',
                           cred_id=11, haproxy=1, nginx=1, master=product.server.server_id)
    roots = wizard_host.add_server(second)
    response = product_client.post(wizard_url(product, 'nginx'), json=body())
    assert response.status_code == 200, response.text
    assert WafRules.select().count() == 3
    assert waf_wizard.read_spec((roots['nginx'] / 'rules/generated.conf').read_text())['id'] == 10000


def test_existing_slave_rule_conflict_never_overwrites_content(product_client, product, wizard_host, waf_cluster):
    slave, roots = waf_cluster
    WafRules.create(serv=slave.ip, service='nginx', rule_name='Unrelated', rule_file='generated.conf', desc='Owned elsewhere')
    path = roots['nginx'] / 'rules/generated.conf'
    path.write_text('# independently managed\n')
    response = product_client.post(wizard_url(product, 'nginx'), json=body())
    assert response.status_code == 500 and 'conflict' in response.json['error'], response.text
    assert path.read_text() == '# independently managed\n'


def test_auto_id_can_resolve_new_slave_conflict_when_editing(product_client, product, wizard_host, waf_cluster):
    _, roots = waf_cluster
    response = product_client.post(wizard_url(product, 'nginx'), json=body())
    endpoint = response.json['edit_url']
    (roots['nginx'] / 'rules/new-local.conf').write_text('SecAction "id:10000,phase:1,pass"\n')
    response = product_client.post(endpoint, json=body())
    assert response.status_code == 200 and response.json['rule_ids'] == [10001], response.text


def test_worker_exit_between_nodes_cannot_report_group_as_applied(product_client, product, wizard_host, waf_cluster, monkeypatch):
    slave, _ = waf_cluster
    response = product_client.post(wizard_url(product, 'nginx'), json={**body(), 'action': 'reload'})
    assert response.status_code == 200, response.text
    for node in (product.server, slave):
        assert waf_state.status(node.server_id, 'nginx') == 'applied'
    upload = waf.config.upload_and_restart

    class WorkerExit(BaseException):
        pass

    def interrupted(address, *args, **kwargs):
        result = upload(address, *args, **kwargs)
        if address == product.server.ip:
            raise WorkerExit()
        return result

    monkeypatch.setattr(waf.config, 'upload_and_restart', interrupted)
    with pytest.raises(WorkerExit):
        product_client.post(response.json['edit_url'], json={**body(), 'action': 'reload'})
    assert waf_state.status(product.server.server_id, 'nginx') == 'applied'
    assert waf_state.status(slave.server_id, 'nginx') == 'pending'
    state = product_client.get(f'/waf/nginx/{product.server.ip}/state')
    assert state.status_code == 200 and 'data-state="pending"' in state.text
    monkeypatch.setattr(waf.config, 'upload_and_restart', upload)
    assert product_client.post(f'/waf/nginx/{product.server.ip}/apply').status_code == 200
    state = product_client.get(f'/waf/nginx/{product.server.ip}/state')
    assert 'data-state="applied"' in state.text
