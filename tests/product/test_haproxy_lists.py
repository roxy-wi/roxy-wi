from flask import g
import pytest
from pydantic import ValidationError

from app.modules.config import add
from app.modules.db.db_model import Server
from app.modules.service import haproxy_lists as lists, haproxy_targets
from app.modules.service.haproxy_list_models import ListContent, ListIdentity, ListChange, RuntimeEntry
from tests.fixtures.haproxy_lists import list_hosts


URL = '/add/haproxy/lists/192.0.2.11'


def detail(client, name='allowed.lst', color='black'):
    response = client.get(URL, query_string={'name': name, 'color': color})
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def save(client, *, content='', snapshot=None, name='allowed.lst', operation='save'):
    snapshot = snapshot or detail(client, name)
    return client.put(URL, json=dict(color='black', name=name, content=content,
                                    revision=snapshot['revision'], operation=operation))


def test_empty_list_updates_runtime_files_and_catalog(product_client, product, list_hosts):
    response = save(product_client)
    assert response.status_code == 200, response.get_json()
    assert list_hosts.nodes[product.server.ip].active == []
    assert list_hosts.local.read_text() == ''
    assert (list_hosts.nodes[product.server.ip].root / 'black/allowed.lst').read_text() == ''
    assert response.get_json()['nodes'][0] == {'server': product.server.ip, 'file': 'saved', 'runtime': 'applied'}


def test_subnets_ipv6_comments_and_dotted_names(product_client, product, list_hosts):
    content = '# private\n192.0.2.0/24\n2001:db8::1\n2001:db8:1::/48\n'
    response = save(product_client, content=content)
    assert response.status_code == 200, response.get_json()
    assert list_hosts.local.read_text() == content
    assert len(list_hosts.nodes[product.server.ip].active) == 3
    response = save(product_client, content=content, name='office.prod.lst')
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['nodes'][0]['runtime'] == 'unused'
    assert (list_hosts.local.parent / 'office.prod.lst').exists()
    assert not (list_hosts.local.parent / 'office.lst').exists()


def test_rejected_commit_restores_remote_file_and_keeps_catalog(product_client, product, list_hosts):
    list_hosts.reject_commit.add(product.server.ip)
    response = save(product_client, content='192.0.2.2')
    assert response.status_code == 502
    assert response.get_json()['nodes'][0] == {'server': product.server.ip, 'file': 'restored', 'runtime': 'failed'}
    assert list_hosts.local.read_text() == '192.0.2.1\n'
    host = list_hosts.nodes[product.server.ip]
    assert (host.root / 'black/allowed.lst').read_text() == '192.0.2.1\n'
    assert host.active == ['192.0.2.1']


def test_lost_commit_response_reports_uncertainty_without_replaying(product_client, product, list_hosts):
    list_hosts.lose_commit.add(product.server.ip)
    response = save(product_client, content='192.0.2.2')
    assert response.status_code == 502
    assert response.get_json()['nodes'][0]['runtime'] == 'unknown'
    assert list_hosts.local.read_text() == '192.0.2.1\n'
    assert list_hosts.nodes[product.server.ip].active == ['192.0.2.2']
    assert sum(command.startswith('commit') for _, command in list_hosts.calls) == 1
    assert detail(product_client)['nodes'][0]['state'] == 'different'


@pytest.mark.parametrize('source', ['local', 'remote', 'runtime', 'process', 'config'])
def test_stale_editor_never_overwrites_changes(product_client, product, list_hosts, source):
    snapshot = detail(product_client)
    host = list_hosts.nodes[product.server.ip]
    if source == 'local':
        list_hosts.local.write_text('192.0.2.3\n')
    elif source == 'remote':
        (host.root / 'black/allowed.lst').write_text('192.0.2.3\n')
    elif source == 'runtime':
        host.active = ['192.0.2.3']
    elif source == 'process':
        host.pid += 1
    else:
        host.config += '# external edit\n'
    list_hosts.calls.clear()
    response = save(product_client, snapshot=snapshot, content='192.0.2.2')
    assert response.status_code == 409
    assert response.get_json()['code'] == 'changed'
    assert not any(command.startswith(('prepare', 'file:save')) for _, command in list_hosts.calls)


def test_linked_nodes_are_prepared_and_report_partial_failure(product_client, product, list_hosts, monkeypatch):
    peer = Server.create(server_id=33, hostname='Peer', ip='192.0.2.33', group_id='1', cred_id=11, haproxy=1)
    list_hosts.add(peer)
    monkeypatch.setattr(haproxy_targets.server_sql, 'is_master', lambda _: [(peer.ip, peer.hostname)])
    list_hosts.fail_file.add(peer.ip)
    response = save(product_client, content='192.0.2.2')
    assert response.status_code == 502
    assert response.get_json()['nodes'] == [
        {'server': product.server.ip, 'file': 'saved', 'runtime': 'applied'},
        {'server': peer.ip, 'file': 'unknown', 'runtime': 'pending'}]
    first_write = next(i for i, (_, command) in enumerate(list_hosts.calls) if command == 'file:save')
    assert any(ip == peer.ip and command.startswith('prepare') for ip, command in list_hosts.calls[:first_write])
    assert list_hosts.local.read_text() == '192.0.2.1\n'


def test_cross_group_peer_is_rejected_before_io(product_client, product, list_hosts, monkeypatch):
    monkeypatch.setattr(haproxy_targets.server_sql, 'is_master', lambda _: [(product.other.ip, 'Foreign')])
    response = product_client.get(URL)
    assert response.status_code in (403, 404)
    assert not list_hosts.calls


def test_delete_used_list_and_unrelated_node_reference_are_blocked(product_client, product, list_hosts):
    response = save(product_client, operation='delete')
    assert response.status_code == 409
    host = list_hosts.nodes[product.server.ip]
    host.loaded, host.config = False, 'frontend public\n'
    peer = Server.create(server_id=33, hostname='Other', ip='192.0.2.33', group_id='1', cred_id=11, haproxy=1)
    list_hosts.add(peer)
    response = save(product_client, operation='delete')
    assert response.status_code == 409
    assert response.get_json()['code'] == 'list_in_use'
    assert list_hosts.local.exists()


def test_delete_ssh_failure_is_not_success_and_retains_local_copy(product_client, product, list_hosts):
    host = list_hosts.nodes[product.server.ip]
    host.loaded, host.config = False, 'frontend public\n'
    list_hosts.fail_file.add(product.server.ip)
    response = product_client.delete('/add/haproxy/list', json={
        'name': 'allowed.lst', 'color': 'black', 'server_ip': product.server.ip})
    assert response.status_code == 502
    assert list_hosts.local.exists()
    list_hosts.fail_file.clear()
    response = save(product_client, operation='delete')
    assert response.status_code == 200, response.get_json()
    assert not list_hosts.local.exists()


def test_invalid_content_and_name_do_not_open_remote_connection(product_client, list_hosts):
    for change in ({'content': '192.0.2.1\nnot-an-ip'}, {'name': '../private.lst'}):
        response = product_client.put(URL, json={
            'name': 'allowed.lst', 'color': 'black', 'content': '', 'revision': 'a' * 64, **change})
        assert response.status_code == 400, response.get_json()
    assert not list_hosts.calls


def test_legacy_empty_post_uses_new_workflow(product_client, product, list_hosts):
    response = product_client.post('/add/haproxy/list', json={
        'server_ip': product.server.ip, 'name': 'allowed.lst', 'color': 'black', 'content': '', 'action': 'save'})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['data']
    assert list_hosts.local.read_text() == ''


def test_legacy_runtime_entry_validates_identity_before_mutation(app, product, list_hosts):
    with app.test_request_context():
        g.user_params = {'user_id': product.admin.user_id, 'group_id': 1, 'role': 1}
        body = RuntimeEntry(name='allowed.lst', color='black', acl_id=9, entry='2001:db8::1')
        with pytest.raises(lists.ListError, match='changed'):
            lists.change_entry(product.server.ip, 1, body)
    assert not any(command.startswith(('prepare', 'file:save')) for _, command in list_hosts.calls)


def test_legacy_runtime_ipv6_entry_persists_and_accepts_crlf_files(product_client, product, list_hosts):
    host = list_hosts.nodes[product.server.ip]
    (host.root / 'black/allowed.lst').write_bytes(b'192.0.2.1\r\n')
    assert detail(product_client)['nodes'][0]['state'] == 'synced'
    response = product_client.post('/runtimeapi/list/add', data={
        'serv': product.server.ip, 'list_name': 'black/allowed.lst', 'list_id_for_add': '0',
        'list_ip_for_add': '2001:db8::1'})
    assert response.text == 'ok', response.text
    assert '2001:db8::1' in host.active
    assert '2001:db8::1' in list_hosts.local.read_text()
    response = product_client.post('/runtimeapi/list/delete', data={
        'serv': product.server.ip, 'list_name': 'black/allowed.lst', 'list_id_for_delete': '0',
        'list_ip_id_for_delete': '0x2', 'list_ip_for_delete': '2001:db8::1'})
    assert response.text == 'ok', response.text
    assert host.active == ['192.0.2.1']
    assert list_hosts.local.read_text() == '192.0.2.1\n'


def test_create_failure_propagates_and_dotted_name_is_preserved(app, product, list_hosts, monkeypatch):
    with app.test_request_context():
        g.user_params = {'user_id': product.admin.user_id, 'group_id': 1, 'role': 1}
        add.create_bwlist(product.server.ip, 'office.prod', 'white', 1)
        assert lists.local_path(1, ListIdentity(name='office.prod', color='white')).exists()
        monkeypatch.setattr(lists.list_files, 'write_file', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('disk full')))
        with pytest.raises(OSError):
            add.create_bwlist(product.server.ip, 'new', 'white', 1)


def test_content_validation_reports_line_and_normalizes_host_masks():
    assert ListContent(content='192.0.2.1/32\n2001:db8::1/128').content == '192.0.2.1\n2001:db8::1\n'
    with pytest.raises(ValidationError, match='Line 2'):
        ListContent(content='# comment\ninvalid')


def test_malformed_existing_file_can_be_opened_and_repaired(product_client, list_hosts):
    list_hosts.local.write_text('invalid entry\n')
    response = product_client.get(URL)
    assert response.status_code == 200
    snapshot = detail(product_client)
    assert snapshot['nodes'][0]['state'] == 'different'
    assert save(product_client, snapshot=snapshot, content='192.0.2.2').status_code == 200


def test_all_nodes_reject_protected_replica_before_io(app, product, list_hosts, monkeypatch):
    peer = Server.create(server_id=33, hostname='Protected', ip='192.0.2.33', group_id='1', cred_id=11,
                         haproxy=1, protected=1)
    monkeypatch.setattr(haproxy_targets.server_sql, 'is_master', lambda _: [(peer.ip, peer.hostname)])
    with app.test_request_context():
        g.user_params = {'user_id': product.admin.user_id, 'group_id': 1, 'role': 3}
        with pytest.raises(Exception, match='permission'):
            lists.change(product.server.ip, 1, ListChange(name='allowed', color='black', revision='a' * 64))
    assert not list_hosts.calls


def test_translations_cover_all_list_messages(app):
    english = app.jinja_env.get_template('languages/en.html').module.haproxy_lists
    for language in ('ru', 'fr', 'es-ES', 'pt-br', 'zh'):
        translated = app.jinja_env.get_template(f'languages/{language}.html').module.haproxy_lists
        assert translated.keys() == english.keys()
        assert all(translated.values())
