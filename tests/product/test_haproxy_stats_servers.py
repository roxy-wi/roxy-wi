import hashlib
from pathlib import Path

import pytest

from app.modules.db import add as add_sql
from app.modules.db.db_model import HaproxySection, Setting, UserGroups
from app.modules.service.stats import haproxy_stats_config as stats_config
from app.modules.service.stats import haproxy_stats_servers as servers
from app.modules.service.stats.haproxy_stats import parse_stats
from tests.fixtures.haproxy_stats import stats_csv
from tests.fixtures.haproxy_servers import server_host, maxconn_host  # noqa: F401


def request_body(action='edit'):
    row = parse_stats(stats_csv())[3 if action == 'add' else 1]
    return dict(action=action, row_key=row['key'], pid=100, uptime=3600)


def prepare(client, product, action='edit', value=None):
    body = request_body(action)
    response = client.get(f'/stats/servers/haproxy/{product.server.ip}', query_string=body)
    assert response.status_code == 200, response.text
    return {**body, 'revision': response.json['revision'], 'targets': [n['ip'] for n in response.json['targets']],
            'value': value if value is not None else {'address': '192.0.2.45', 'port': 8181} if action == 'edit' else None}


def post(client, product, body):
    return client.post(f'/stats/servers/haproxy/{product.server.ip}', json=body)


@pytest.mark.parametrize('action', ['add', 'edit', 'delete'])
def test_server_operations_persist_each_nodes_config_and_section(product_client, product, server_host, action):
    value = {'name': 'new', 'address': '2001:db8::10', 'port': 9000, 'check': False, 'check_port': 9001} if action == 'add' else None
    body = prepare(product_client, product, action, value)
    assert not server_host.saves and not server_host.writes
    response = post(product_client, product, body)
    assert response.status_code == 200, response.text
    assert response.headers['Cache-Control'] == 'no-store'
    assert all(node['config'] == node['settings'] == 'saved' and node['runtime'] == 'applied' for node in response.json['nodes'])
    assert len(server_host.saves) == 2 and len(server_host.validations) == 2
    assert '# replica-specific configuration' not in server_host.configs[product.server.ip]
    assert '# replica-specific configuration' in server_host.configs[server_host.linked.ip]
    for record in server_host.records:
        saved = HaproxySection.get_by_id(record.id).config
        assert saved['option'] == record.config['option']
        if action == 'add':
            assert saved['backend_servers'][-1] == {
                'name': 'new', 'server': '2001:db8::10', 'port': 9000, 'port_check': 9001,
                'check_enabled': False, 'maxconn': 0, 'backup': False, 'send_proxy': False}
        elif action == 'edit':
            assert saved['backend_servers'][0] == {**record.config['backend_servers'][0], 'server': '192.0.2.45', 'port': 8181}
            assert 'server one 192.0.2.45:8181 check maxconn 100 # maxconn 99 comment' in server_host.configs[product.server.ip]
        else:
            assert saved['backend_servers'] == record.config['backend_servers'][1:]
            assert 'server one ' not in server_host.configs[product.server.ip]
    if action != 'delete':
        assert all('Pid: 100' in info for info in server_host.info.values())
        assert all(save[2]['action'] == 'save' for save in server_host.saves)
        assert server_host.writes
    if action == 'add':
        assert 'server new [2001:db8::10]:9000 port 9001 no-check maxconn 0' in server_host.configs[product.server.ip]


@pytest.mark.parametrize('change', ['config', 'settings', 'process', 'topology'])
def test_changes_after_opening_dialog_are_rejected_without_writes(product_client, product, server_host, change):
    body = prepare(product_client, product)
    if change == 'config':
        server_host.configs[server_host.linked.ip] += '# concurrent\n'
    elif change == 'settings':
        record = server_host.records[1]
        HaproxySection.update(config={**record.config, 'option': 'new option'}).where(HaproxySection.id == record.id).execute()
    elif change == 'process':
        server_host.info[server_host.linked.ip] = server_host.info[server_host.linked.ip].replace('Pid: 100', 'Pid: 999')
    else:
        server_host.linked.master = 0
        server_host.linked.save()
    response = post(product_client, product, body)
    assert response.status_code == 409, response.text
    assert not server_host.saves


@pytest.mark.parametrize('failure', ['validation', 'runtime', 'save', 'database', 'concurrent_config', 'reload'])
def test_partial_results_and_preflight_failures_are_explicit(product_client, product, server_host, monkeypatch, failure):
    body = prepare(product_client, product)
    if failure == 'database':
        update = add_sql.update_haproxy_server_settings
        def fail(record, updated):
            if record.id == server_host.records[1].id:
                raise RuntimeError('private-database-detail')
            return update(record, updated)
        monkeypatch.setattr(add_sql, 'update_haproxy_server_settings', fail)
    elif failure == 'concurrent_config':
        server_host.validation_hook = lambda ip: server_host.configs.__setitem__(ip, server_host.configs[ip] + '# concurrent\n')
    elif failure == 'reload':
        server_host.validation_hook = lambda ip: server_host.info.__setitem__(ip, server_host.info[ip].replace('Pid: 100', 'Pid: 999'))
    else:
        setattr(server_host, 'fail_' + failure, server_host.linked.ip)
    response = post(product_client, product, body)
    assert response.status_code == (409 if failure in ('validation', 'reload') else 502), response.text
    assert 'private-' not in response.text
    if failure in ('validation', 'reload', 'concurrent_config'):
        assert not server_host.saves
    if failure in ('save', 'database'):
        assert response.json['nodes'][0]['settings'] == 'saved'
        assert response.json['nodes'][1]['settings'] == 'pending'
        assert HaproxySection.get_by_id(server_host.records[0].id).config['backend_servers'][0]['server'] == '192.0.2.45'
        assert HaproxySection.get_by_id(server_host.records[1].id).config == server_host.records[1].config


@pytest.mark.parametrize('value', [
    {'address': '192.0.2.50;show info', 'port': 80},
    {'address': '192.0.2.50\nbackend bad', 'port': 80},
    {'address': 'fe80::1%eth0\nbackend bad', 'port': 80},
    {'address': 'fe80::1%eth0', 'port': 80},
    {'address': ['192.0.2.50'], 'port': 80},
    {'address': '192.0.2.50', 'port': True},
    {'address': '192.0.2.50', 'port': 0},
    {'address': '192.0.2.50', 'port': 65536},
])
def test_invalid_inputs_do_not_write(product_client, product, server_host, value):
    body = prepare(product_client, product)
    assert post(product_client, product, {**body, 'value': value}).status_code == 400
    assert not server_host.saves


def test_duplicate_and_missing_section_record_do_not_silently_change_form(product_client, product, server_host):
    value = dict(name='one', address='192.0.2.50', port=80, check=True, check_port=80)
    assert post(product_client, product, prepare(product_client, product, 'add', value)).status_code == 409
    record = server_host.records[0]
    HaproxySection.update(config={**record.config, 'backend_servers': []}).where(HaproxySection.id == record.id).execute()
    assert post(product_client, product, prepare(product_client, product)).status_code == 409
    assert not server_host.saves


def test_authorization_and_deployment_policy_cover_every_node(product_client, product, server_host):
    body = prepare(product_client, product)
    assert product_client.post(f'/stats/servers/haproxy/{product.server.ip}', json=body, headers={'X-CSRF-TOKEN': ''}).status_code == 401
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    assert post(product_client, product, body).status_code == 403
    UserGroups.update(user_role_id=3).where(UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.post(f'/stats/servers/haproxy/{product.other.ip}', json=body).status_code == 403
    server_host.linked.group_id = 2
    server_host.linked.save()
    assert post(product_client, product, body).status_code == 403
    server_host.linked.group_id = 1
    server_host.linked.save()
    Setting.insert(param='haproxy_deployment_mode', value='change_center', group_id=1,
                   section='change_center', desc='Test').on_conflict_replace().execute()
    assert post(product_client, product, body).status_code == 403
    assert not server_host.saves


def test_old_server_routes_and_tab_are_removed(product_client, product):
    for method in ('post', 'put', 'delete'):
        assert getattr(product_client, method)('/runtimeapi/server', data={'serv': product.server.ip}).status_code == 404
    assert 'href="#servers"' not in product_client.get('/runtimeapi').text


def test_manual_sections_stay_manual_and_ipv6_edit_preserves_options(product_client, product, server_host):
    HaproxySection.delete().execute()
    body = prepare(product_client, product, value={'address': '2001:db8::1', 'port': 443})
    assert post(product_client, product, body).status_code == 200
    assert HaproxySection.select().count() == 0
    assert 'server one [2001:db8::1]:443 check maxconn 100 # maxconn 99 comment' in server_host.configs[product.server.ip]


def test_maxconn_still_finds_server_after_address_change(product_client, product, server_host):
    assert post(product_client, product, prepare(product_client, product)).status_code == 200
    add_sql.update_haproxy_section_maxconn(product.server.server_id, 'backend', 'web', 42, server_name='one')
    record = HaproxySection.get_by_id(server_host.records[0].id)
    assert record.config['backend_servers'][0]['maxconn'] == 42
    assert record.config['backend_servers'][0]['server'] == '192.0.2.45'


def test_replaying_request_does_not_apply_twice(product_client, product, server_host):
    body = prepare(product_client, product)
    assert post(product_client, product, body).status_code == 200
    assert post(product_client, product, body).status_code == 409
    assert len(server_host.saves) == 2


@pytest.mark.parametrize('managed', [False, True])
def test_add_stays_in_its_section_and_managed_block(product_client, product, server_host, managed):
    end_marker = '# END Roxy-WI MANAGED backend web do not edit it directly'
    next_section = '# BEGIN Roxy-WI MANAGED ring logs do not edit it directly\nring logs\n    size 32768\n'
    for ip, content in server_host.configs.items():
        if managed:
            content = content.replace('backend web\n', '# BEGIN Roxy-WI MANAGED backend web do not edit it directly\nbackend web\n')
            content += end_marker + '\n'
        server_host.configs[ip] = content + next_section
    value = dict(name='new', address='192.0.2.50', port=80, check=True, check_port=80)
    assert post(product_client, product, prepare(product_client, product, 'add', value)).status_code == 200
    for content in server_host.configs.values():
        assert content.index('server new ') < content.index(next_section)
        if managed:
            assert content.index('server new ') < content.index(end_marker)


def test_settings_compare_and_swap_preserves_concurrent_form_edit(product_client, product, server_host, monkeypatch):
    body = prepare(product_client, product)
    save = stats_config.config.upload_and_restart
    record = server_host.records[0]
    concurrent = {**record.config, 'option': 'new option'}
    def save_and_edit(*args, **kwargs):
        save(*args, **kwargs)
        HaproxySection.update(config=concurrent).where(HaproxySection.id == record.id).execute()
    monkeypatch.setattr(stats_config.config, 'upload_and_restart', save_and_edit)
    response = post(product_client, product, body)
    assert response.status_code == 502
    assert response.json['code'] == 'server_section_sync_failed'
    assert response.json['nodes'][0] == dict(server=product.server.ip, config='saved', runtime='applied', settings='pending')
    assert HaproxySection.get_by_id(record.id).config == concurrent
    assert len(server_host.saves) == 1


@pytest.mark.parametrize('duplicate', [False, True])
def test_multiple_files_resolve_exact_section_and_keep_other_files(product_client, product, server_host, monkeypatch, duplicate):
    main, backend = '/etc/haproxy/haproxy.cfg', '/etc/haproxy/backends.cfg'
    contents = {ip: {main: 'global\n    maxconn 2000\n', backend: content} for ip, content in server_host.configs.items()}
    if duplicate:
        contents[product.server.ip][main] += 'backend web\n    server one 192.0.2.30:8080\n'
    for record in server_host.records:
        HaproxySection.update(config_path=backend, file_id=hashlib.sha256(backend.encode()).hexdigest()).where(HaproxySection.id == record.id).execute()
    monkeypatch.setattr(servers.haproxy_files, 'multiple_files_enabled', lambda node: True)
    monkeypatch.setattr(servers.haproxy_files, 'discover_sources', lambda *args: dict(state='ready', files=[main, backend]))
    def download(ip, filename, *, config_file_name):
        Path(filename).write_bytes(contents[ip][config_file_name].encode())
    monkeypatch.setattr(stats_config.config, 'get_config', download)
    if duplicate:
        response = product_client.get(f'/stats/servers/haproxy/{product.server.ip}', query_string=request_body())
        assert response.status_code == 409
        assert not server_host.saves
        return
    body = prepare(product_client, product)
    response = post(product_client, product, body)
    assert response.status_code == 200, response.text
    assert all(saved[2]['config_file_name'] == backend for saved in server_host.saves)
    assert all(files[main] == 'global\n    maxconn 2000\n' for files in contents.values())
    assert HaproxySection.get_by_id(server_host.records[0].id).config['backend_servers'][0]['port'] == 8181


@pytest.mark.parametrize('name', ['bad name', 'bad\nbackend bad', 'bad;show info', 'a' * 256])
def test_add_rejects_invalid_names(product_client, product, server_host, name):
    value = dict(name=name, address='192.0.2.50', port=80, check=True, check_port=80)
    assert post(product_client, product, prepare(product_client, product, 'add', value)).status_code == 400
    assert not server_host.saves


@pytest.mark.parametrize('patch,code', [
    ({'value': {'address': 'secret-invalid-address', 'port': 80}}, 'server_invalid_address'),
    ({'value': {'address': '192.0.2.10', 'port': True}}, 'server_invalid_port'),
    ({'action': 'add', 'value': {'name': 'bad name', 'address': '192.0.2.10', 'port': 80,
                              'check': True, 'check_port': 80}}, 'server_invalid_fields'),
    ({'value': {'address': '192.0.2.10'}}, 'invalid_action'),
    ({'action': 'delete', 'value': {'address': '192.0.2.10', 'port': 80}}, 'invalid_action'),
    ({'pid': '100'}, 'invalid_action'),
    ({'unexpected': True}, 'invalid_action'),
])
def test_pydantic_rejects_request_before_service_and_preserves_public_errors(product_client, product, monkeypatch, patch, code):
    monkeypatch.setattr(servers, 'change', lambda *args: pytest.fail('Invalid request reached service'))
    body = {**request_body(), 'revision': 'a' * 64, 'targets': [product.server.ip],
            'value': {'address': '192.0.2.10', 'port': 80}, **patch}
    response = post(product_client, product, body)
    assert response.status_code == 400
    assert response.json == {'status': 'error', 'code': code}
    assert response.headers['Cache-Control'] == 'no-store'


def test_pydantic_rejects_bad_query_before_reading_nodes(product_client, product, monkeypatch):
    monkeypatch.setattr(servers, 'describe', lambda *args: pytest.fail('Invalid query reached service'))
    response = product_client.get(f'/stats/servers/haproxy/{product.server.ip}',
                                  query_string={**request_body(), 'pid': 'invalid'})
    assert response.status_code == 400
    assert response.json == {'status': 'error', 'code': 'invalid_action'}


@pytest.mark.parametrize('action', ['add', 'edit'])
def test_runtime_rejection_does_not_persist_or_continue_to_replica(product_client, product, server_host, action):
    server_host.fail_runtime = product.server.ip
    server_host.reply = 'Permission denied'
    value = dict(name='new', address='192.0.2.50', port=80, check=True, check_port=81) if action == 'add' else None
    response = post(product_client, product, prepare(product_client, product, action, value))
    assert response.status_code == 502
    assert len(server_host.writes) == 1
    assert not server_host.saves
    assert response.json['nodes'][0]['config'] == 'pending'
    assert response.json['nodes'][1]['runtime'] == 'pending'
    assert all(HaproxySection.get_by_id(record.id).config == record.config for record in server_host.records)


def test_add_uses_each_nodes_defaults_and_same_health_ssl_options_as_config(product_client, product, server_host):
    for index, record in enumerate(server_host.records):
        updated = {**record.config, 'servers_check': {'check_enabled': True, 'inter': 5 + index, 'rise': 3, 'fall': 4},
                   'ssl': {'ssl_check_backend': False}}
        HaproxySection.update(config=updated).where(HaproxySection.id == record.id).execute()
    for ip, content in server_host.configs.items():
        server_host.configs[ip] = content.replace('backend web\n', 'backend web\n    default-server weight 23\n')
    value = dict(name='new', address='192.0.2.50', port=80, check=True, check_port=81)
    assert post(product_client, product, prepare(product_client, product, 'add', value)).status_code == 200
    for index, ip in enumerate((product.server.ip, server_host.linked.ip)):
        options = f'port 81 check inter {5 + index} rise 3 fall 4 ssl verify none maxconn 0'
        assert f'server new 192.0.2.50:80 {options}' in server_host.configs[ip]
        assert (ip, f'add server web/new 192.0.2.50:80 weight 23 {options}') in server_host.writes
        assert [cmd for node, cmd in server_host.writes if node == ip][-2:] == [
            'enable health web/new', 'set server web/new state ready']
