import json
from types import SimpleNamespace

import pytest

from app.modules.db.db_model import InstallationTasks, PacemakerCluster, Server
from app.modules.operations.queue import deserialize_operation_payload, serialize_operation_payload
from app.modules.pacemaker import operations, qdevice, monitor
from app.modules.pacemaker.quorum import details
from app.modules.roxywi.exception import RoxywiConflictError


@pytest.fixture
def witness(monkeypatch):
    server = Server.create(hostname='test-witness', ip='192.0.2.230', group_id='1')
    account = operations.User.get_by_id(1)
    monkeypatch.setattr(operations.User, 'get_or_none', lambda *_args: account)
    monkeypatch.setattr(operations.user_sql, 'select_user_services', lambda _id: '5')
    monkeypatch.setattr(operations.user_sql, 'get_user_role_in_group', lambda *_args: 1)
    yield server
    for task in InstallationTasks.select().where(InstallationTasks.service_name == 'Corosync witness: test-witness'):
        task.delete_instance()
    server.delete_instance()


def test_witness_has_its_own_durable_job_without_a_cluster(witness, monkeypatch):
    calls = []
    monkeypatch.setattr(qdevice, 'install_witness', lambda *args: calls.append(args))
    task = operations.enqueue_witness(witness.server_id, 1, 1)
    assert 'cluster_id' not in deserialize_operation_payload(task.operation_payload)
    with pytest.raises(RoxywiConflictError):
        operations.enqueue_witness(witness.server_id, 1, 1)
    assert operations.execute(task) == 'completed'
    assert calls == [(witness.server_id, 1)]


@pytest.mark.parametrize('reason', ['identity', 'service', 'role', 'started'])
def test_witness_rechecks_identity_permissions_and_replay(witness, monkeypatch, reason):
    task = operations.enqueue_witness(witness.server_id, 1, 1)
    if reason == 'identity':
        Server.update(ip='192.0.2.231').where(Server.server_id == witness.server_id).execute()
    elif reason == 'service':
        monkeypatch.setattr(operations.user_sql, 'select_user_services', lambda _id: '')
    elif reason == 'role':
        monkeypatch.setattr(operations.user_sql, 'get_user_role_in_group', lambda *_args: 4)
    else:
        payload = deserialize_operation_payload(task.operation_payload)
        payload['started'] = True
        task.operation_payload = serialize_operation_payload(payload)
        task.save()
    monkeypatch.setattr(qdevice, 'install_witness', lambda *_args: pytest.fail('An invalid job must never reach SSH'))
    assert operations.execute(task) == 'failed'


def test_witness_cannot_be_a_registered_cluster_member(witness, monkeypatch):
    monkeypatch.setattr(PacemakerCluster, 'select', lambda: [SimpleNamespace(servers=json.dumps([{'server_id': witness.server_id}]))])
    with pytest.raises(ValueError, match='outside every registered cluster'):
        qdevice.witness_server(witness.server_id, 1)


def test_witness_initialization_and_status_use_the_existing_witness_protocol(witness, monkeypatch):
    calls = []
    class Remote:
        def __init__(self, server):
            assert server.server_id == witness.server_id
        def run(self, args, **kwargs):
            calls.append((args, kwargs))
            if args[-1] == qdevice.WITNESS_STATUS:
                return json.dumps({'active': True, 'version': '3.0', 'ca_fingerprint': 'existing-ca'})
            assert args[-1] == qdevice.WITNESS
            assert json.loads(kwargs['data']) == {'action': 'init', 'docker': False}
            return 'existing-ca-certificate'
    monkeypatch.setattr(qdevice, 'Remote', Remote)
    assert qdevice.install_witness(witness.server_id, 1)['ca_fingerprint'] == 'existing-ca'
    assert len(calls) == 2


def test_quorum_status_and_loss_of_witness_vote():
    available = details('Flags: Quorate Qdevice\n 0 1 Qdevice\n')
    assert available == {'configured': True, 'votes': 1, 'two_node': False}
    assert details('Flags: Quorate 2Node\n')['configured'] is False
    missing = details('Flags: Quorate Qdevice\n 0 0 Qdevice\n')
    state = {'quorate': True, 'nodes': [], 'resources': [], 'failures': 0, 'quorum_details': missing}
    assert monitor.health(state) == 'witness-unavailable'
    state['quorum_details'] = available
    assert monitor.health(state) == 'healthy'
    with pytest.raises(ValueError):
        details('Unsupported output')


def test_witness_api_is_group_scoped_and_operator_only(witness, client, authenticated):
    response = client.post('/pacemaker/api/witness/install', headers=authenticated[1], json={'server_id': witness.server_id})
    assert response.status_code == 202
    task_id = response.json['task_id']
    assert client.get(f'/pacemaker/api/witness/tasks/{task_id}', headers=authenticated[1]).status_code == 200
    authenticated[0]['group_id'] = 2
    assert client.get(f'/pacemaker/api/witness/tasks/{task_id}', headers=authenticated[1]).status_code == 404
    authenticated[0]['role'] = 4
    assert client.post('/pacemaker/api/witness/install', headers=authenticated[1], json={'server_id': witness.server_id}).status_code == 403
    assert client.get(f'/pacemaker/api/witness/{witness.server_id}', headers=authenticated[1]).status_code == 403


@pytest.mark.parametrize('initialized', [False, True])
def test_rpm_witness_initializes_nss_once_and_preserves_existing_ca(tmp_path, monkeypatch, capsys, initialized):
    import io
    import os
    import pwd
    import subprocess
    import sys
    from app.modules.pacemaker.platforms import SOURCE
    database = tmp_path / 'nssdb'
    certificate = database / 'qnetd-cacert.crt'
    if initialized:
        database.mkdir()
        certificate.write_bytes(b'existing-lab-ca')
    calls, owners = [], []
    def run(args, **kwargs):
        calls.append(args)
        if args[:2] == ['corosync-qnetd-certutil', '-i']:
            database.mkdir()
            certificate.write_bytes(b'new-lab-ca')
        return SimpleNamespace(stdout=pwd.getpwuid(os.getuid()).pw_name + '\n',
                               returncode=1 if 'is-active' in args else 0)
    monkeypatch.setattr(subprocess, 'run', run)
    monkeypatch.setattr(os, 'chown', lambda *args: owners.append(args))
    monkeypatch.setattr(sys, 'stdin', io.StringIO('{"action":"init"}'))
    source = qdevice.WITNESS[len(SOURCE):].replace('/etc/corosync/qnetd/nssdb', str(database)).replace('/run/lock/roxywi-qnetd.lock', str(tmp_path / 'witness.lock'))
    source = source.replace('state = container_state()', 'state = None')
    roles = []
    exec(source, {'install_packages': lambda role: roles.append(role)})
    assert roles == ['witness']
    assert (['corosync-qnetd-certutil', '-i'] in calls) is not initialized
    assert bool(owners) is not initialized
    assert certificate.read_bytes() == (b'existing-lab-ca' if initialized else b'new-lab-ca')
    assert ['systemctl', 'enable', '--now', 'corosync-qnetd'] in calls


@pytest.mark.parametrize('docker', [False, True])
def test_witness_install_api_preserves_selected_deployment(witness, client, authenticated, docker):
    response = client.post('/pacemaker/api/witness/install', headers=authenticated[1],
                           json={'server_id': witness.server_id, 'docker': docker})
    assert response.status_code == 202
    task = InstallationTasks.get_by_id(response.json['task_id'])
    assert deserialize_operation_payload(task.operation_payload)['docker'] is docker


@pytest.mark.parametrize('docker', ['false', 'true', 1, {}, []])
def test_witness_install_rejects_ambiguous_deployment(witness, client, authenticated, docker):
    response = client.post('/pacemaker/api/witness/install', headers=authenticated[1],
                           json={'server_id': witness.server_id, 'docker': docker})
    assert response.status_code == 400
