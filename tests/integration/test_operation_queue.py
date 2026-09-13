import json
from datetime import timedelta
from uuid import uuid4

from app.modules.common.time import utc_now
from app.modules.db.db_model import InstallationTasks
from app.modules.operations import queue as operation_queue
from app.modules.operations.queue import OperationQueueSettings, deserialize_operation_payload
from app.modules.operations.worker import OperationWorker, claim_operation, execute_operation
from app.modules.service import installation


class RecordingChannel:
    def __init__(self):
        self.calls = []

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))

    def exchange_declare(self, **kwargs):
        self._record('exchange_declare', **kwargs)

    def queue_declare(self, **kwargs):
        self._record('queue_declare', **kwargs)

    def queue_bind(self, **kwargs):
        self._record('queue_bind', **kwargs)

    def basic_qos(self, **kwargs):
        self._record('basic_qos', **kwargs)

    def confirm_delivery(self):
        self._record('confirm_delivery')

    def basic_publish(self, **kwargs):
        self._record('basic_publish', **kwargs)
        return True


class RecordingConnection:
    def __init__(self, channel):
        self.recording_channel = channel
        self.is_open = True

    def channel(self):
        return self.recording_channel

    def close(self):
        self.is_open = False


def _settings(**kwargs):
    values = {
        'host': 'rabbitmq',
        'port': 5672,
        'vhost': '/',
        'username': 'roxy-wi',
        'password': 'secret',
    }
    values.update(kwargs)
    return OperationQueueSettings(**values)


def test_operation_topology_supports_quorum_queues():
    channel = RecordingChannel()
    operation_queue.declare_operation_topology(channel, _settings(queue_type='quorum'))

    declarations = [kwargs for name, kwargs in channel.calls if name == 'queue_declare']
    assert declarations[0]['queue'] == 'roxy-wi.operations'
    assert declarations[0]['arguments']['x-queue-type'] == 'quorum'
    assert declarations[1]['queue'] == 'roxy-wi.operations.dlq'


def test_operation_outbox_publishes_persistent_task(monkeypatch):
    channel = RecordingChannel()
    connection = RecordingConnection(channel)
    monkeypatch.setattr(operation_queue.pika, 'BlockingConnection', lambda _params: connection)
    task_id = operation_queue.create_ansible_task(
        service_name='Test operation',
        server_ids=[],
        user_id=None,
        group_id=None,
        inventory={'server': {'hosts': {}}},
        server_ips=[],
        ansible_role='haproxy',
    )

    try:
        assert operation_queue.publish_pending_operations(settings=_settings()) == 1
        task = InstallationTasks.get_by_id(task_id)
        assert task.status == 'published'
        published = [kwargs for name, kwargs in channel.calls if name == 'basic_publish']
        assert len(published) == 1
        assert published[0]['properties'].delivery_mode == 2
        assert json.loads(published[0]['body'])['task_id'] == task_id
    finally:
        InstallationTasks.delete_by_id(task_id)


def test_operation_payload_is_encrypted_at_rest():
    task_id = operation_queue.create_ansible_task(
        service_name='Secret operation',
        server_ids=[],
        user_id=None,
        group_id=None,
        inventory={'server': {'hosts': {'localhost': {'password': 'temporary-secret'}}}},
        server_ips=[],
        ansible_role='s3_backup',
        run_locally=True,
    )

    try:
        task = InstallationTasks.get_by_id(task_id)
        assert task.operation_payload.startswith('fernet:')
        assert 'temporary-secret' not in task.operation_payload
        assert deserialize_operation_payload(task.operation_payload)['inventory'][
            'server'
        ]['hosts']['localhost']['password'] == 'temporary-secret'
    finally:
        InstallationTasks.delete_by_id(task_id)


def test_ansible_workflow_runs_steps_sequentially(monkeypatch):
    calls = []
    task_id = operation_queue.create_ansible_workflow_task(
        service_name='Sequential workflow',
        server_ids=[],
        user_id=None,
        group_id=None,
        steps=[
            {
                'inventory': {'name': 'delete'},
                'server_ips': [],
                'ansible_role': 'letsencrypt',
                'run_locally': True,
            },
            {
                'inventory': {'name': 'install'},
                'server_ips': ['192.0.2.10'],
                'ansible_role': 'letsencrypt_standalone',
                'run_locally': False,
            },
        ],
    )
    task = InstallationTasks.get_by_id(task_id)
    monkeypatch.setattr(
        installation,
        'run_ansible_locally',
        lambda inventory, role: calls.append(('local', inventory['name'], role)) or {
            'failures': {}, 'dark': {},
        },
    )
    monkeypatch.setattr(
        installation,
        'run_ansible',
        lambda inventory, server_ips, role: calls.append(
            ('remote', inventory['name'], server_ips, role)
        ) or {'failures': {}, 'dark': {}},
    )

    try:
        assert claim_operation(task.operation_id, task.id) == (True, 'running')
        assert execute_operation(task.operation_id, task.id) == 'completed'
        assert calls == [
            ('local', 'delete', 'letsencrypt'),
            ('remote', 'install', ['192.0.2.10'], 'letsencrypt_standalone'),
        ]
    finally:
        InstallationTasks.delete_by_id(task_id)


def test_completed_redelivery_is_idempotent(monkeypatch):
    operation_id = str(uuid4())
    task = InstallationTasks.create(
        service_name='Completed operation',
        server_ids=[],
        operation_id=operation_id,
        operation_type='ansible',
        operation_payload='{}',
        status='completed',
    )
    called = False

    def run_installations(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(installation, 'run_installations', run_installations)
    try:
        assert execute_operation(operation_id, task.id) == 'completed'
        assert called is False
    finally:
        task.delete_instance()


def test_installation_is_queued_in_every_deployment_mode(app, monkeypatch):
    monkeypatch.setattr(
        installation.roxywi_common,
        'get_jwt_token_claims',
        lambda: {'user_id': None, 'group': None},
    )
    monkeypatch.setattr(
        installation.server_sql,
        'get_server_by_ip',
        lambda _server_ip: type('Server', (), {'server_id': 42})(),
    )
    for deployment_mode in ('package', 'compose', 'kubernetes'):
        monkeypatch.setenv('ROXYWI_DEPLOYMENT_MODE', deployment_mode)
        task_id = installation.run_ansible_thread(
            {'server': {'hosts': {'192.0.2.1': {}}}},
            ['192.0.2.1'],
            'haproxy',
            'HAProxy',
        )

        try:
            task = InstallationTasks.get_by_id(task_id)
            assert task.status == 'created'
            assert task.operation_type == 'ansible'
            assert task.operation_payload.startswith('fernet:')
            assert deserialize_operation_payload(task.operation_payload)['server_ips'] == ['192.0.2.1']
        finally:
            InstallationTasks.delete_by_id(task_id)


def test_operation_message_validation():
    operation_id = str(uuid4())
    assert OperationWorker._decode(
        json.dumps({'operation_id': operation_id, 'task_id': 10}).encode()
    ) == (operation_id, 10)


def test_operation_claim_is_atomic_and_duplicate_safe():
    operation_id = str(uuid4())
    task = InstallationTasks.create(
        service_name='Claim operation',
        server_ids=[],
        operation_id=operation_id,
        operation_type='ansible',
        operation_payload='{}',
        status='published',
    )
    try:
        assert claim_operation(operation_id, task.id) == (True, 'running')
        assert claim_operation(operation_id, task.id) == (False, 'running')
    finally:
        InstallationTasks.delete_by_id(task.id)


def test_stale_running_operation_returns_to_outbox(monkeypatch):
    monkeypatch.setenv('ROXYWI_OPERATIONS_LEASE_SECONDS', '60')
    task = InstallationTasks.create(
        service_name='Stale operation',
        server_ids=[],
        operation_id=str(uuid4()),
        operation_type='ansible',
        operation_payload='{}',
        status='running',
        updated_at=utc_now() - timedelta(minutes=2),
    )
    try:
        assert operation_queue.recover_stale_operations() == 1
        task = InstallationTasks.get_by_id(task.id)
        assert task.status == 'created'
        assert 'lease expired' in task.error
    finally:
        InstallationTasks.delete_by_id(task.id)
