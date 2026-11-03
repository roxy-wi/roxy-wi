"""Preserve per-node runtime selection and group authorization after Lists migration."""
import json
import shlex

import pytest
from flask import g

from app.modules.config import add
from app.modules.db.db_model import ServiceSetting, Server, Setting
from app.modules.service import haproxy_lists as lists, haproxy_targets
from app.modules.service.haproxy_list_models import ListIdentity
from tests.fixtures.haproxy_lists import list_hosts


def test_existing_list_gui_uses_each_nodes_selected_runtime_and_preserves_quoted_paths(product, app, monkeypatch, list_hosts):
    peer = Server.create(server_id=33, hostname='Native peer', ip='192.0.2.33', group_id='1', cred_id=11, haproxy=1)
    list_hosts.add(peer, loaded=False)
    for name, value in dict(dockerized='1', container_engine='podman', container_owner='root', container_name='managed-proxy').items():
        ServiceSetting.create(server_id=11, service='haproxy', setting=name, value=value)
    Setting.update(value='/srv/proxy config').where(Setting.param == 'haproxy_dir').execute()
    monkeypatch.setattr(haproxy_targets.server_sql, 'is_master', lambda _: [(peer.ip, peer.hostname)])
    calls, requests = [], []
    original = lists.Remote.run
    def remote(self, argv, **kwargs):
        requests.append((self.server.ip, json.loads(kwargs['data'])))
        return original(self, argv, **kwargs)
    monkeypatch.setattr(lists.Remote, 'run', remote)
    monkeypatch.setattr(add.server_mod, 'ssh_command', lambda ip, command, **kwargs: calls.append((ip, command, kwargs)) or '')
    with app.test_request_context():
        g.user_params = dict(user_id=product.admin.user_id, group_id=1, role=1)
        assert 'error:' not in add.save_bwlist('source.lst', '192.0.2.0/24\n', 'black', '1', product.server.ip, 'reload')
    writes = [(ip, data) for ip, data in requests if data['operation'] == 'save']
    assert len(writes) == 2 and all(data['root'] == '/srv/proxy config' for _, data in writes)
    assert writes[0][1]['runtime']['engine'] == 'podman'
    assert writes[0][1]['container'] == 'managed-proxy'
    assert 'container' not in writes[1][1]
    applied = [(ip, command) for ip, command, kwargs in calls if kwargs.get('error_context') == 'Cannot apply HAProxy list']
    envelope = json.loads(shlex.split(applied[0][1].removesuffix(' > /dev/null'))[-1])
    assert envelope['runtime'] == dict(engine='podman', owner='root', unit='')
    assert envelope['action'] == 'haproxy-reload'
    assert applied[1][0] == peer.ip and 'systemctl reload' in applied[1][1]


def test_cross_group_slave_is_rejected_before_local_or_remote_list_write(product, app, monkeypatch, list_hosts):
    monkeypatch.setattr(haproxy_targets.server_sql, 'is_master', lambda _: [(product.other.ip, 'Foreign')])
    with app.test_request_context():
        g.user_params = dict(user_id=product.admin.user_id, group_id=1, role=1)
        with pytest.raises(Exception):
            add.save_bwlist('source.lst', '192.0.2.0/24\n', 'black', '1', product.server.ip, 'reload')
    assert not list_hosts.calls
    assert not lists.local_path(1, ListIdentity(name='source.lst', color='black')).exists()


def test_global_admin_may_explicitly_select_another_group_but_protected_operator_cannot_write(product, app, list_hosts):
    list_hosts.add(product.other, loaded=False)
    with app.test_request_context():
        g.user_params = dict(user_id=product.admin.user_id, group_id=1, role=1)
        assert 'success:' in add.save_bwlist('source.lst', '192.0.2.0/24\n', 'black', '2', product.other.ip, 'save')
    assert lists.local_path(2, ListIdentity(name='source.lst', color='black')).exists()
    list_hosts.calls.clear()
    Server.update(protected=1).where(Server.server_id == 11).execute()
    with app.test_request_context():
        g.user_params = dict(user_id=product.admin.user_id, group_id=1, role=3)
        with pytest.raises(Exception):
            add.save_bwlist('source.lst', '192.0.2.0/24\n', 'black', '1', product.server.ip, 'save')
    assert not list_hosts.calls
