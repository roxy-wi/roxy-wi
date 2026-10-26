from pathlib import Path
from copy import deepcopy
import hashlib

import pytest

from app.modules.db import add as add_sql
from app.modules.db.db_model import ActionHistory, HaproxySection, Setting, UserGroups
from app.modules.service.stats import haproxy_stats_maxconn as maxconn
from app.modules.service.stats.haproxy_stats import parse_stats
from tests.fixtures.haproxy_stats import stats_csv
from tests.fixtures.haproxy_maxconn import maxconn_host  # noqa: F401


def body(scope='server', value=150):
    row = 0 if scope == 'frontend' else 1
    return dict(scope=scope, value=value, row_key=None if scope == 'global' else parse_stats(stats_csv())[row]['key'],
                pid=100, uptime=3600, targets=['192.0.2.11', '192.0.2.33'])


def post(client, product, payload):
    return client.post(f'/stats/maxconn/haproxy/{product.server.ip}', json=payload)


@pytest.mark.parametrize('scope,value,command,fragment', [
    ('server', 150, 'set maxconn server web/one 150', 'check maxconn 150 # maxconn 99 comment'),
    ('server', 0, 'set maxconn server web/one 0', 'check maxconn 0 # maxconn 99 comment'),
    ('frontend', 1800, 'set maxconn frontend public 1800', 'bind :80\n    maxconn 1800'),
    ('global', 1900, 'set maxconn global 1900', 'global\n    maxconn 1900'),
])
def test_maxconn_updates_runtime_config_and_history_on_all_nodes(product_client, product, maxconn_host, scope, value, command, fragment):
    response = post(product_client, product, body(scope, value))
    assert response.status_code == 200, response.text
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json['nodes'] == [dict(server=ip, runtime='applied', config='saved') for ip in body()['targets']]
    assert maxconn_host.writes == [(ip, command) for ip in body()['targets']]
    assert maxconn_host.validations == body()['targets']
    assert all(fragment in text for text in maxconn_host.configs.values())
    assert [entry[2].get('record_version', True) for entry in maxconn_host.saves] == [True, True]
    assert Path(maxconn_host.saves[0][1]).is_file(), 'Saved version must remain readable'
    assert ActionHistory.select().where(ActionHistory.action == f'HAProxy Stats: {command}; configuration saved').count() == 2


def test_preview_resolves_authorized_topology_without_writes(product_client, product, maxconn_host):
    response = product_client.get(f'/stats/maxconn/haproxy/{product.server.ip}')
    assert response.status_code == 200
    assert [node['ip'] for node in response.json['targets']] == body()['targets']
    assert not maxconn_host.writes and not maxconn_host.saves


@pytest.mark.parametrize('override', [
    {'scope': 'backend'}, {'scope': []}, {'value': True}, {'value': '150'}, {'value': 1.5},
    {'value': -1}, {'value': 2147483648}, {'pid': '100'}, {'uptime': -1}, {'row_key': []},
    {'targets': '192.0.2.11'}, {'command': 'show info'},
])
def test_invalid_payload_never_writes(product_client, product, maxconn_host, override):
    assert post(product_client, product, {**body(), **override}).status_code == 400
    assert not maxconn_host.writes and not maxconn_host.saves


@pytest.mark.parametrize('payload,code', [
    (None, 'invalid_action'),
    ([], 'invalid_action'),
    ({}, 'invalid_action'),
    ({**body(), 'value': True}, 'invalid_maxconn'),
    ({**body(), 'value': 'private-invalid-limit'}, 'invalid_maxconn'),
    ({**body(), 'value': -1, 'pid': '100'}, 'invalid_maxconn'),
    ({**body(), 'value': -1, 'unexpected': True}, 'invalid_action'),
    ({k: v for k, v in body(value=-1).items() if k != 'targets'}, 'invalid_action'),
    (body('global', 0), 'invalid_maxconn'),
    (body('frontend', 0), 'invalid_maxconn'),
    ({**body('global'), 'row_key': 'unexpected'}, 'invalid_action'),
    ({**body(), 'pid': True}, 'invalid_action'),
])
def test_pydantic_rejects_invalid_requests_before_service_with_existing_errors(
    product_client, product, monkeypatch, payload, code,
):
    monkeypatch.setattr(maxconn, 'change', lambda *args: pytest.fail('Invalid request reached service'))
    response = post(product_client, product, payload)
    assert response.status_code == 400
    assert response.json == {'status': 'error', 'code': code}
    assert response.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('scope', ['global', 'frontend'])
def test_persisted_global_and_frontend_require_positive_limit(product_client, product, maxconn_host, scope):
    assert post(product_client, product, body(scope, 0)).status_code == 400
    assert not maxconn_host.writes


@pytest.mark.parametrize('case', ['pid', 'uptime', 'row', 'topology', 'replica_missing', 'reload_during_validation', 'topology_during_validation', 'ceiling', 'config_target', 'validation'])
def test_preflight_failure_does_not_apply_any_changes(product_client, product, maxconn_host, case):
    payload = body()
    if case == 'pid':
        payload['pid'] = 101
    elif case == 'uptime':
        payload['uptime'] = 4000
    elif case == 'row':
        payload['row_key'] = parse_stats(stats_csv())[3]['key']
    elif case == 'topology':
        payload['targets'].pop()
    elif case == 'replica_missing':
        maxconn_host.rows['192.0.2.33'].pop(1)
    elif case == 'reload_during_validation':
        maxconn_host.validation_hook = lambda ip: maxconn_host.info.update({ip: maxconn_host.info[ip].replace('Pid: 100', 'Pid: 200')})
    elif case == 'topology_during_validation':
        def unlink(ip):
            maxconn_host.linked.master = 0
            maxconn_host.linked.save()
        maxconn_host.validation_hook = unlink
    elif case == 'ceiling':
        payload = body('global', 1500)
        maxconn_host.info['192.0.2.33'] = maxconn_host.info['192.0.2.33'].replace('Hard_maxconn: 2000', 'Hard_maxconn: 1000')
    elif case == 'config_target':
        maxconn_host.configs[product.server.ip] = 'global\n    maxconn 2000\n'
    else:
        maxconn_host.fail_validation = '192.0.2.33'
    response = post(product_client, product, payload)
    assert response.status_code == 409, response.text
    assert not maxconn_host.writes and not maxconn_host.saves


@pytest.mark.parametrize('failure', ['runtime', 'denied', 'save', 'concurrent_config'])
def test_partial_and_uncertain_results_are_explicit_without_retries(product_client, product, maxconn_host, failure):
    if failure in ('runtime', 'denied'):
        maxconn_host.fail_runtime = '192.0.2.33'
        if failure == 'denied':
            maxconn_host.reply = 'Permission denied\n'
    elif failure == 'save':
        maxconn_host.fail_save = '192.0.2.33'
    else:
        maxconn_host.validation_hook = lambda ip: maxconn_host.configs.update({ip: maxconn_host.configs[ip] + '# concurrent edit\n'}) if ip.endswith('.33') else None
    response = post(product_client, product, body())
    assert response.status_code == 502
    assert response.json['code'] == 'maxconn_incomplete'
    assert response.json['nodes'][0] == dict(server=product.server.ip, runtime='applied', config='saved')
    node = response.json['nodes'][1]
    assert node['runtime'] == ('unknown' if failure == 'runtime' else 'failed' if failure == 'denied' else 'applied')
    assert node['config'] == ('pending' if failure in ('runtime', 'denied') else 'unknown')
    assert len(maxconn_host.writes) == 2 and len(maxconn_host.saves) == 1
    assert 'private-' not in response.text
    if failure == 'concurrent_config':
        assert '# concurrent edit' in maxconn_host.configs['192.0.2.33']


def test_permissions_csrf_policy_and_related_node_access(product_client, product, maxconn_host):
    url = f'/stats/maxconn/haproxy/{product.server.ip}'
    assert product_client.post(url, json=body(), headers={'X-CSRF-TOKEN': ''}).status_code == 401
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.get(url).status_code == 403
    assert post(product_client, product, body()).status_code == 403
    UserGroups.update(user_role_id=3).where(UserGroups.user_id == product.admin.user_id).execute()
    maxconn_host.linked.group_id = 2
    maxconn_host.linked.save()
    assert product_client.get(url).status_code == 403
    assert post(product_client, product, body()).status_code == 403
    maxconn_host.linked.group_id = 1
    maxconn_host.linked.save()
    Setting.insert(param='haproxy_deployment_mode', value='change_center', group_id=1, section='change_center', desc='Test policy').on_conflict_replace().execute()
    response = post(product_client, product, body())
    assert response.status_code == 403 and response.json['code'] == 'maxconn_policy'
    assert not maxconn_host.writes and not maxconn_host.saves


def test_listen_frontend_and_commented_server_config(product_client, product, maxconn_host):
    maxconn_host.configs[product.server.ip] = maxconn_host.configs[product.server.ip].replace('frontend public', 'listen public')
    assert post(product_client, product, body('frontend', 500)).status_code == 200
    assert 'listen public\n    bind :80\n    maxconn 500' in maxconn_host.configs[product.server.ip]
    maxconn_host.configs[product.server.ip] = maxconn_host.configs[product.server.ip].replace('check maxconn 100 #', 'check #')
    assert post(product_client, product, body('server', 75)).status_code == 200
    assert 'check maxconn 75 # maxconn 99 comment' in maxconn_host.configs[product.server.ip]


def test_legacy_maxconn_routes_are_removed(product_client, product):
    assert product_client.get(f'/runtimeapi/maxconn/{product.server.ip}').status_code == 404
    for scope in ('global', 'frontend', 'backend'):
        assert product_client.post(f'/runtimeapi/maxconn/{scope}/{product.server.ip}', data={'maxconn': 150}).status_code == 404
    assert '#maxconn' not in product_client.get('/runtimeapi').text


def saved_section(server_id, kind='global', name='global', path='/etc/haproxy/haproxy.cfg'):
    return HaproxySection.create(server_id=server_id, type=kind, name=name, config_path=path,
        file_id=hashlib.sha256(path.encode()).hexdigest(), config={
            'maxconn': 5000, 'option': 'log global', 'custom_field': {'keep': True},
            'backend_servers': [{'server': 'one', 'port': 8080, 'maxconn': 100},
                                {'server': 'two', 'port': 8080, 'maxconn': 200}]})


@pytest.mark.parametrize('scope,kind,name', [('global', 'global', 'global'), ('frontend', 'frontend', 'public'),
    ('frontend', 'listen', 'public'), ('server', 'backend', 'web'), ('server', 'listen', 'web')])
def test_maxconn_syncs_edit_section_on_each_saved_node_without_touching_other_data(product_client, product, maxconn_host, scope, kind, name):
    if kind == 'listen':
        old_kind = 'frontend' if scope == 'frontend' else 'backend'
        for ip in maxconn_host.configs:
            maxconn_host.configs[ip] = maxconn_host.configs[ip].replace(old_kind + ' ' + name, 'listen ' + name)
    records = [saved_section(node, kind, name) for node in (product.server.server_id, maxconn_host.linked.server_id)]
    extra = saved_section(product.server.server_id, kind, name, '/etc/haproxy/extra.cfg')
    other = saved_section(product.other.server_id, kind, name)
    untouched = deepcopy(extra.config)
    response = post(product_client, product, body(scope, 150))
    assert response.status_code == 200, response.text
    for record in records:
        expected = deepcopy(record.config)
        if scope == 'server':
            expected['backend_servers'][0]['maxconn'] = 150
        else:
            expected['maxconn'] = 150
        url = f'/add/haproxy/{record.server_id_id}/section/{kind}' + ('' if kind == 'global' else '/' + name)
        section = product_client.get(url)
        assert section.status_code == 200, section.text
        assert section.json['config'] == expected
    assert HaproxySection.get_by_id(extra.id).config == untouched
    assert HaproxySection.get_by_id(other.id).config == untouched


@pytest.mark.parametrize('failure', ['runtime', 'save', 'validation', 'database'])
def test_section_settings_follow_only_confirmed_saves(product_client, product, maxconn_host, monkeypatch, failure):
    first = saved_section(product.server.server_id)
    second = saved_section(maxconn_host.linked.server_id)
    if failure == 'database':
        update = add_sql.update_haproxy_section_maxconn
        def fail_replica(server_id, *args, **kwargs):
            if server_id == maxconn_host.linked.server_id:
                raise RuntimeError('private-database-failure')
            return update(server_id, *args, **kwargs)
        monkeypatch.setattr(add_sql, 'update_haproxy_section_maxconn', fail_replica)
    else:
        setattr(maxconn_host, 'fail_' + failure, maxconn_host.linked.ip)
    response = post(product_client, product, body('global', 1900))
    assert response.status_code == (409 if failure == 'validation' else 502)
    assert HaproxySection.get_by_id(first.id).config['maxconn'] == (5000 if failure == 'validation' else 1900)
    assert HaproxySection.get_by_id(second.id).config['maxconn'] == 5000
    if failure == 'database':
        assert response.json['code'] == 'maxconn_section_sync_failed'
        assert all(node['config'] == 'saved' for node in response.json['nodes'])
        assert len(maxconn_host.writes) == 2
    assert 'private-' not in response.text


def test_manual_sections_are_not_created_as_incomplete_forms(product_client, product, maxconn_host):
    assert post(product_client, product, body('global', 1900)).status_code == 200
    assert HaproxySection.select().count() == 0


def test_section_sync_preserves_concurrent_edit_and_is_idempotent(product_client, product, monkeypatch):
    record = saved_section(product.server.server_id)
    read = HaproxySection.get_or_none
    calls = []
    def concurrent(*args, **kwargs):
        section = read(*args, **kwargs)
        if not calls:
            changed = {**section.config, 'option': 'concurrent option'}
            HaproxySection.update(config=changed).where(HaproxySection.id == section.id).execute()
        calls.append(True)
        return section
    monkeypatch.setattr(HaproxySection, 'get_or_none', concurrent)
    add_sql.update_haproxy_section_maxconn(product.server.server_id, 'global', 'global', 3999)
    assert len(calls) == 2
    add_sql.update_haproxy_section_maxconn(product.server.server_id, 'global', 'global', 3999)
    saved = HaproxySection.get_by_id(record.id).config
    assert saved == {**record.config, 'option': 'concurrent option', 'maxconn': 3999}


@pytest.mark.parametrize('scope', ['global', 'frontend', 'server'])
def test_maxconn_preserves_replica_configuration_and_records_its_own_version(product_client, product, maxconn_host, scope):
    replica = maxconn_host.linked.ip
    maxconn_host.configs[replica] = maxconn_host.configs[replica].replace('bind :80', 'bind :8088') + '# replica-only\n'
    assert post(product_client, product, body(scope, 150)).status_code == 200
    assert 'bind :8088' in maxconn_host.configs[replica]
    assert '# replica-only' in maxconn_host.configs[replica]
    assert 'bind :8088' not in maxconn_host.configs[product.server.ip]
    assert maxconn_host.saves[0][1] != maxconn_host.saves[1][1]
    for ip, filename, kwargs in maxconn_host.saves:
        assert Path(filename).read_text(encoding='utf-8') == maxconn_host.configs[ip]
        assert kwargs.get('record_version', True)


def test_missing_server_in_saved_form_is_reported_as_sync_failure(product_client, product, maxconn_host):
    record = saved_section(product.server.server_id, 'backend', 'web')
    HaproxySection.update(config={**record.config, 'backend_servers': []}).where(HaproxySection.id == record.id).execute()
    response = post(product_client, product, body('server', 150))
    assert response.status_code == 502
    assert response.json['code'] == 'maxconn_section_sync_failed'
    assert response.json['nodes'][0]['config'] == 'saved'
    assert response.json['nodes'][1]['runtime'] == 'pending'
