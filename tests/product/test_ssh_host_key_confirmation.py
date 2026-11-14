"""Exercise server registration and host-key approval through real HTTP routes."""
import importlib
from types import SimpleNamespace

import paramiko
import pytest
from peewee import SqliteDatabase

from app.modules.db.db_model import Cred, Server, UserGroups
from app.modules.server import host_keys, ssh


@pytest.fixture
def ssh_peer(product, monkeypatch):
    keys = [paramiko.RSAKey.generate(1024) for _ in range(2)]
    values = [key.get_name() + ' ' + key.get_base64() for key in keys]
    state = SimpleNamespace(key=values[0], replacement=values[1], probes=[], scans=[])

    def probe(host, port, preferred=None):
        state.probes.append((host, port))
        return state.key

    monkeypatch.setattr(host_keys, 'probe', probe)
    monkeypatch.setattr('app.modules.server.server.update_server_after_creating',
                        lambda *args: state.scans.append(args))
    return state


def body(**changes):
    return dict(hostname='New SSH server', ip='192.0.2.33', port=2222, cred_id=11,
                group_id=1, description='Host key test', **changes)


def challenge(client, payload, url='/api/server'):
    response = client.post(url, json=payload)
    assert response.status_code == 409, response.text
    assert response.json['code'] == 'ssh_host_key_confirmation_required'
    return response.json


@pytest.mark.parametrize('url', ['/api/server', '/server'])
def test_creation_requires_confirmation_then_pins_key(product_client, ssh_peer, url):
    payload = body()
    review = challenge(product_client, payload, url)
    assert review['host_key'] == dict(host='192.0.2.33', port=2222, algorithm='ssh-rsa',
                                    fingerprint=host_keys.fingerprint(ssh_peer.key), changed=False)
    assert not Server.select().where(Server.ip == payload['ip']).exists()
    assert not ssh_peer.scans
    response = product_client.post(url, json=dict(payload, ssh_host_key_confirmation=review['confirmation']))
    assert response.status_code == 201, response.text
    server = Server.get_by_id(response.json['id'])
    assert server.ssh_host_key == ssh_peer.key
    assert ssh.return_ssh_keys_path(server.ip)['host_key'] == dict(host=server.ip, port=2222, key=ssh_peer.key)
    assert len(ssh_peer.scans) == 1
    duplicate = product_client.post(url, json=dict(payload, ssh_host_key_confirmation=review['confirmation']))
    assert duplicate.status_code == 409
    assert len(ssh_peer.scans) == 1


def test_key_changed_during_confirmation_requires_new_review(product_client, ssh_peer):
    payload = body()
    review = challenge(product_client, payload)
    ssh_peer.key = ssh_peer.replacement
    changed = challenge(product_client, dict(payload, ssh_host_key_confirmation=review['confirmation']))
    assert changed['host_key']['changed']
    assert changed['host_key']['previous_fingerprint'] == review['host_key']['fingerprint']
    assert not Server.select().where(Server.ip == payload['ip']).exists()
    assert not ssh_peer.scans


@pytest.mark.parametrize('change', ['port', 'ip', 'credential', 'tamper', 'expired'])
def test_confirmation_cannot_be_reused_for_changed_or_invalid_requests(product_client, ssh_peer, monkeypatch, change):
    payload = body()
    review = challenge(product_client, payload)
    payload['ssh_host_key_confirmation'] = review['confirmation']
    if change == 'port':
        payload['port'] = 2223
    elif change == 'ip':
        payload['ip'] = '192.0.2.34'
    elif change == 'credential':
        Cred.create(id=12, name='Other SSH', username='other', group_id=1)
        payload['cred_id'] = 12
    elif change == 'tamper':
        payload['ssh_host_key_confirmation'] += 'broken'
    else:
        monkeypatch.setattr(host_keys, 'CONFIRMATION_TTL', -1)
    response = product_client.post('/api/server', json=payload)
    assert response.status_code == 409, response.text
    assert len(ssh_peer.probes) == 1
    assert not ssh_peer.scans


def test_virtual_ip_does_not_probe_or_authenticate(product_client, ssh_peer):
    response = product_client.post('/api/server', json=body(type_ip=True))
    assert response.status_code == 201, response.text
    assert Server.get_by_id(response.json['id']).ssh_host_key is None
    assert ssh_peer.probes == ssh_peer.scans == []


def test_disabling_scan_does_not_bypass_confirmation(product_client, ssh_peer):
    challenge(product_client, body(scan_server=False))
    assert not Server.select().where(Server.ip == '192.0.2.33').exists()
    assert not ssh_peer.scans


@pytest.mark.parametrize('server_id,role', [(22, 2), (11, 3), (11, 4)])
def test_existing_key_approval_requires_server_and_admin_access(product_client, product, ssh_peer, server_id, role):
    UserGroups.update(user_role_id=role).where(UserGroups.user_id == product.admin.user_id).execute()
    response = product_client.post(f'/api/server/{server_id}/ssh-host-key', json={})
    assert response.status_code in (403, 404), response.text
    assert not ssh_peer.probes


@pytest.mark.parametrize('case', ['role', 'group', 'credentials', 'csrf'])
def test_permissions_are_checked_before_network_access(product_client, product, ssh_peer, case):
    payload = body()
    headers = {}
    if case in ('role', 'group'):
        UserGroups.update(user_role_id=3 if case == 'role' else 2).where(UserGroups.user_id == product.admin.user_id).execute()
        if case == 'group':
            payload['group_id'] = 2
    elif case == 'credentials':
        Cred.create(id=12, name='Private SSH', username='other', group_id=2)
        payload['cred_id'] = 12
    else:
        headers['X-CSRF-TOKEN'] = ''
    response = product_client.post('/api/server', json=payload, headers=headers)
    assert response.status_code == (404 if case == 'group' else 401 if case == 'csrf' else 403), response.text
    assert ssh_peer.probes == ssh_peer.scans == []


def test_existing_server_key_rotation_is_explicit(product_client, product, ssh_peer):
    url = f'/server/{product.server.server_id}/ssh-host-key'
    review = challenge(product_client, {}, url)
    assert Server.get_by_id(11).ssh_host_key is None
    response = product_client.post(url, json={'ssh_host_key_confirmation': review['confirmation']})
    assert response.status_code == 200, response.text
    assert product_client.post(url, json={}).status_code == 200
    ssh_peer.key = ssh_peer.replacement
    review = challenge(product_client, {}, url)
    assert review['host_key']['changed']
    assert Server.get_by_id(11).ssh_host_key != ssh_peer.replacement
    assert product_client.post(url, json={'ssh_host_key_confirmation': review['confirmation']}).status_code == 200
    assert Server.get_by_id(11).ssh_host_key == ssh_peer.replacement


def test_existing_approval_does_not_cross_registration_lifetimes(product_client, product, ssh_peer):
    url = '/api/server/11/ssh-host-key'
    review = challenge(product_client, {}, url)
    Server.update(registration_key='recreated-server').where(Server.server_id == 11).execute()
    response = product_client.post(url, json={'ssh_host_key_confirmation': review['confirmation']})
    assert response.status_code == 409
    assert Server.get_by_id(11).ssh_host_key is None


def test_concurrent_confirmation_cannot_replace_another_approved_key(product_client, ssh_peer, monkeypatch):
    url = '/api/server/11/ssh-host-key'
    review = challenge(product_client, {}, url)

    def concurrent_change(*args):
        Server.update(ssh_host_key=ssh_peer.replacement).where(Server.server_id == 11).execute()
        return ssh_peer.key

    monkeypatch.setattr(host_keys, 'probe', concurrent_change)
    response = product_client.post(url, json={'ssh_host_key_confirmation': review['confirmation']})
    assert response.status_code == 409
    assert Server.get_by_id(11).ssh_host_key == ssh_peer.replacement


def test_changing_ssh_port_requires_review_before_update(product_client, product, ssh_peer):
    payload = dict(body(), ip=product.server.ip)
    response = product_client.put('/api/server/11', json=payload)
    assert response.status_code == 409, response.text
    assert Server.get_by_id(11).port == 22
    payload['ssh_host_key_confirmation'] = response.json['confirmation']
    response = product_client.put('/api/server/11', json=payload)
    assert response.status_code == 201, response.text
    assert Server.get_by_id(11).port == 2222
    assert Server.get_by_id(11).ssh_host_key == ssh_peer.key


def test_migration_retains_legacy_servers_children_and_approved_keys():
    migration = importlib.import_module('app.modules.db.migrations.20261114000000_ssh_host_keys')
    database = SqliteDatabase(':memory:', pragmas={'foreign_keys': 1})
    with database, database.bind_ctx([Server], bind_refs=False, bind_backrefs=False):
        database.execute_sql('CREATE TABLE servers (id INTEGER PRIMARY KEY, hostname TEXT)')
        database.execute_sql('CREATE TABLE child (server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE)')
        database.execute_sql("INSERT INTO servers VALUES (1, 'Legacy')")
        database.execute_sql('INSERT INTO child VALUES (1)')
        migration.up()
        assert database.execute_sql('SELECT ssh_host_key FROM servers').fetchone() == (None,)
        database.execute_sql("UPDATE servers SET ssh_host_key='approved-public-key'")
        migration.up()
        assert database.execute_sql('SELECT ssh_host_key FROM servers').fetchone() == ('approved-public-key',)
        assert database.execute_sql('SELECT server_id FROM child').fetchall() == [(1,)]
