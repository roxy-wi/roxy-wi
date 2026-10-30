"""Installation failures keep useful diagnostics without exposing task secrets."""
import json
import subprocess
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.modules.db.db_model import InstallationTasks
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.pacemaker import bootstrap, install_log, operations, service
from app.modules.pacemaker.platforms import SOURCE
from app.modules.pacemaker.remote import RemoteError
from app.modules.roxywi.exception import RoxywiPublicError
from tests.unit.pacemaker.test_pacemaker import cluster


class ScriptRemote:
    """Run the stdlib-only installation protocol without an SSH host."""

    def run(self, argv, *, on_stdout, **kwargs):
        result = subprocess.run([sys.executable, *argv[1:]], capture_output=True, text=True)
        for offset in range(0, len(result.stdout), 7):
            on_stdout(result.stdout[offset:offset + 7])
        if result.returncode:
            raise RemoteError(f'Cluster command failed (exit {result.returncode}); inspect the node journal')
        return result.stdout


def test_remote_protocol_keeps_fragmented_logs_separate_from_result():
    entries = []
    result = install_log.run(ScriptRemote(), SOURCE + "\ninstallation_message('Проверка репозиториев')\nprint('{\"ok\":true}')",
                             'node-1', 'Repositories', lambda *entry: entries.append(entry))
    assert json.loads(result) == {'ok': True}
    assert entries[1] == ('node-1', 'Repositories', 'info', 'Проверка репозиториев')
    assert entries[-1][-1] == 'Completed'


@pytest.mark.parametrize('exit_code', [0, 1])
def test_ssh_stream_decodes_split_utf8_without_exposing_stderr(monkeypatch, exit_code):
    from app.modules.pacemaker import remote
    from app.modules.server import ssh

    expected = 'Проверка репозиториев\n'

    class Channel:
        def __init__(self):
            self.chunks = [bytes([value]) for value in expected.encode()]
            self.errors = [b'password=PrivateRemoteError']
            self.closed = False

        def settimeout(self, _timeout): pass
        def exec_command(self, _command): pass
        def shutdown_write(self): pass
        def recv_ready(self): return bool(self.chunks)
        def recv_stderr_ready(self): return bool(self.errors)
        def recv(self, _size): return self.chunks.pop(0)
        def recv_stderr(self, _size): return self.errors.pop(0)
        def exit_status_ready(self): return not self.chunks
        def recv_exit_status(self): return exit_code
        def close(self): self.closed = True

    channel = Channel()
    transport = SimpleNamespace(open_session=lambda **kwargs: channel)
    connection = SimpleNamespace(ssh=SimpleNamespace(get_transport=lambda: transport))
    monkeypatch.setattr(ssh, 'ssh_connect', lambda *args, **kwargs: nullcontext(connection))
    monkeypatch.setattr(remote.select, 'select', lambda *args: None)
    received = []
    target = remote.Remote(SimpleNamespace(ip='192.0.2.1'))
    if exit_code:
        with pytest.raises(RemoteError) as error:
            target.run(['python3', '-c', 'pass'], on_stdout=received.append)
        assert 'PrivateRemoteError' not in str(error.value)
    else:
        assert target.run(['python3', '-c', 'pass'], on_stdout=received.append) == expected
    assert ''.join(received) == expected and channel.closed


def test_package_failure_preserves_output_and_exit_code():
    entries = []
    source = SOURCE + '\ninstallation_command(' + repr([
        sys.executable, '-c', "import sys; print('Error: Unable to find a match: pacemaker resource-agents', file=sys.stderr); sys.exit(7)"
    ]) + ')\n'
    with pytest.raises(RoxywiPublicError, match='node-1 during Packages'):
        install_log.run(ScriptRemote(), source, 'node-1', 'Packages', lambda *entry: entries.append(entry))
    messages = '\n'.join(entry[-1] for entry in entries)
    assert 'Unable to find a match: pacemaker resource-agents' in messages
    assert 'exit 7' in messages
    assert entries[-1][2] == 'error'


def test_package_timeout_keeps_partial_output():
    entries = []
    source = SOURCE + '\ninstallation_command(' + repr([
        sys.executable, '-c', "import time; print('Downloading packages', flush=True); time.sleep(5)"
    ]) + ', timeout=0.3)\n'
    with pytest.raises(RoxywiPublicError, match='installation log'):
        install_log.run(ScriptRemote(), source, 'node-1', 'Packages', lambda *entry: entries.append(entry))
    messages = '\n'.join(entry[-1] for entry in entries)
    assert 'Downloading packages' in messages and 'timed out' in messages


def test_task_log_is_encrypted_redacted_and_available_after_completion(cluster, client, authenticated):
    task = operations.enqueue(cluster, 1, 'bootstrap')
    payload = deserialize_operation_payload(task.operation_payload)
    record = install_log.recorder(task, payload)
    record('node-1', 'Repositories', 'error',
           'https://user:RepositoryPassword@example.test/repo?token=QuerySecret\npassword=OtherSecret\n'
           '-----BEGIN PRIVATE KEY-----\nPrivateMaterial\n-----END PRIVATE KEY-----\nPackages unavailable: pacemaker')
    InstallationTasks.update(status='failed', error='Open the installation log').where(InstallationTasks.id == task.id).execute()
    stored = InstallationTasks.get_by_id(task.id).operation_payload
    assert 'Packages unavailable' not in stored
    response = client.get(f'/pacemaker/api/{cluster.id}/tasks/{task.id}', headers=authenticated[1])
    assert response.status_code == 200
    data = response.json['data']
    assert data['log'][-1]['stage'] == 'Repositories'
    assert 'Packages unavailable: pacemaker' in data['log'][-1]['message']
    for secret in ('RepositoryPassword', 'QuerySecret', 'OtherSecret', 'PrivateMaterial'):
        assert secret not in response.text
    history = client.get(f'/pacemaker/api/{cluster.id}/history', headers=authenticated[1]).json
    assert history['installations'][0]['id'] == task.id
    authenticated[0]['role'] = 4
    assert 'log' not in client.get(f'/pacemaker/api/{cluster.id}/tasks/{task.id}', headers=authenticated[1]).json['data']
    assert client.get(f'/pacemaker/api/{cluster.id}/history', headers=authenticated[1]).json['installations'] == []
    authenticated[0]['group_id'] = 2
    assert client.get(f'/pacemaker/api/{cluster.id}/tasks/{task.id}', headers=authenticated[1]).status_code == 404


def test_log_limit_keeps_recent_errors_and_marks_truncation(cluster):
    task = operations.enqueue(cluster, 1, 'bootstrap')
    payload = deserialize_operation_payload(task.operation_payload)
    record = install_log.recorder(task, payload)
    for number in range(20):
        record('node-1', 'Packages', 'info', str(number) + ':' + 'x' * 15900)
    record('node-1', 'Packages', 'error', 'Final package error')
    saved = deserialize_operation_payload(InstallationTasks.get_by_id(task.id).operation_payload)
    assert saved['installation_log_truncated'] is True
    assert saved['installation_log'][-1]['message'] == 'Final package error'
    assert len(json.dumps(saved['installation_log']).encode()) <= install_log.MAX_LOG_BYTES


def test_every_node_repository_check_finishes_before_packages_are_installed(cluster, monkeypatch):
    calls = []
    members = service.members(cluster)

    def run(remote, source, node, stage, record, **kwargs):
        calls.append((node, stage))
        if stage == 'Preflight':
            return node
        if stage == 'Repositories' and node == members[1][0].name:
            raise RoxywiPublicError('High Availability repository unavailable')
        return ''

    monkeypatch.setattr(install_log, 'run', run)
    with pytest.raises(RoxywiPublicError, match='repository unavailable'):
        bootstrap.provision(cluster, 1)
    assert calls == [(member.name, stage) for member, _server in members for stage in ('Preflight', 'Repositories')]


def test_no_service_starts_until_all_nodes_are_prepared(cluster, monkeypatch):
    calls = []

    def run(remote, source, node, stage, record, **kwargs):
        calls.append(stage)
        if stage == 'Preflight':
            return node
        if stage == 'Packages and configuration':
            return json.dumps({'fence_pve_repaired': False})
        return ''

    monkeypatch.setattr(install_log, 'run', run)
    monkeypatch.setattr(service, 'wait_ready', lambda _cluster: None)
    bootstrap.provision(cluster, 1)
    assert calls == ['Preflight', 'Repositories'] * 2 + ['Packages and configuration'] * 2 + ['Start services'] * 2
