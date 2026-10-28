"""Opt-in qualification against an existing disposable compatible Linux cluster.

Set ROXYWI_PACEMAKER_LIVE=1 and ROXYWI_PACEMAKER_LIVE_CONFIG to a private JSON
file containing name (roxy-lab-*), ssh_key, ssh_user, and members. Each member
contains name, ip (SSH), address (Corosync), and nodeid. No credentials are
embedded in the repository. These tests add/remove only a uniquely named Dummy
resource and refuse non-lab node/cluster names.
"""
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.db.db_model import Cred, Server
from app.modules.pacemaker import service, adoption
from app.modules.pacemaker.bootstrap import provision
from app.modules.pacemaker.editor import Edit, build
from app.modules.pacemaker.remote import RemoteError
from app.modules.pacemaker.schemas import ClusterCreate, Adoption
from app.modules.pacemaker.xml import configuration
from app.modules.roxywi.exception import RoxywiConflictError


pytestmark = pytest.mark.skipif(
    os.environ.get('ROXYWI_PACEMAKER_LIVE') != '1',
    reason='Requires explicitly enabled disposable lab cluster and private SSH config',
)


@pytest.fixture
def live_servers():
    config = json.loads(Path(os.environ['ROXYWI_PACEMAKER_LIVE_CONFIG']).read_text())
    if not config['name'].startswith('roxy-lab') or any(not member['name'].startswith('roxy-lab-') for member in config['members']):
        pytest.fail('Live tests require dedicated roxy-lab cluster/node names')
    from app.modules.server.ssh import crypt_password
    from app.modules.roxy_wi_tools import GetConfigVar
    Path(GetConfigVar().get_config_var('main', 'lib_path')).joinpath('keys').mkdir(parents=True, exist_ok=True)
    cred = Cred.create(name=f'pcmk-live-{uuid4().hex}', username=config.get('ssh_user', 'codex'), group_id=1,
                       private_key=crypt_password(Path(config['ssh_key']).read_text()).decode(), key_enabled=1)
    servers = []
    try:
        for member in config['members']:
            servers.append(Server.create(hostname=member['name'], ip=member['ip'], group_id='1', cred_id=cred.id))
        body = ClusterCreate(name=config['name'], members=[
            {'server_id': server.server_id, 'name': member['name'], 'address': member['address'], 'nodeid': member['nodeid']}
            for member, server in zip(config['members'], servers)
        ])
        yield body
    finally:
        for server in servers:
            server.delete_instance()
        cred.delete_instance()


@pytest.fixture
def live_cluster(live_servers):
    cluster = service.register(live_servers, 1)
    try:
        service.wait_ready(cluster)
        yield cluster
    finally:
        cluster.delete_instance(recursive=True)


def test_live_adoption_preserves_cib_and_corosync(live_servers):
    seed_id = live_servers.members[0].server_id
    found = adoption.discover(seed_id, 1)
    body = Adoption(name=found['name'], members=found['members'], seed_server_id=seed_id,
                    base_digest=found['base_digest'], topology_digest=found['topology_digest'])
    before = {member.server_id: adoption.inspect(adoption.server_for(member.server_id, 1)) for member in body.members}
    cluster = adoption.adopt(body, 1, 1)
    try:
        assert service.get_config(cluster)['digest'] == found['base_digest']
        assert json.loads(cluster.corosync_settings)['membership_managed'] is False
        for member in body.members:
            after = adoption.inspect(adoption.server_for(member.server_id, 1))
            assert after['base_digest'] == before[member.server_id]['base_digest']
            assert after['config'] == before[member.server_id]['config']
        assert service.status(cluster)['quorate']
    finally:
        cluster.delete_instance(recursive=True)


def test_live_bootstrap_refuses_to_overwrite_an_existing_cluster(live_cluster):
    before = service.get_config(live_cluster)['digest']
    with pytest.raises(RemoteError):
        provision(live_cluster, 1)
    assert service.get_config(live_cluster)['digest'] == before


def test_live_validation_patch_conflict_and_resource_cleanup(live_cluster):
    name = f'roxywi-smoke-{uuid4().hex[:10]}'
    current = service.get_config(live_cluster)
    candidate = build(current['xml'], Edit(base_digest=current['digest'], kind='resource', data={
        'id': name, 'agent': 'ocf:heartbeat:Dummy', 'parameters': {},
    }))
    first = service.draft(live_cluster, 1, candidate)
    second = service.draft(live_cluster, 1, candidate)
    service.validate_or_apply(live_cluster, first.id, 1)
    service.validate_or_apply(live_cluster, second.id, 1)
    try:
        service.validate_or_apply(live_cluster, first.id, 1, apply=True)
        with pytest.raises(RoxywiConflictError):
            service.validate_or_apply(live_cluster, second.id, 1, apply=True)
        deadline = time.monotonic() + 30
        active = False
        while time.monotonic() < deadline:
            active = any(resource['id'] == name and resource['active'] == 'true'
                         for resource in service.status(live_cluster)['resources'])
            if active:
                break
            time.sleep(1)
        assert active, 'The disposable Dummy resource did not start'
    finally:
        current = service.get_config(live_cluster)
        if configuration(current['xml']).find(f".//primitive[@id='{name}']") is not None:
            removal = build(current['xml'], Edit(base_digest=current['digest'], kind='delete', data={'id': name}))
            change = service.draft(live_cluster, 1, removal)
            service.validate_or_apply(live_cluster, change.id, 1)
            service.validate_or_apply(live_cluster, change.id, 1, apply=True)
