"""Optional services use the existing Ansible outbox and worker, without a second runner."""
import json
from types import SimpleNamespace

import pytest

from app.modules.db.db_model import InstallationTasks, Server, UserGroups, WorkerState, HaCluster, HaClusterRouter, HaClusterVip, HaClusterVirt, RoxyTool
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.operations.worker import claim_operation, execute_operation
from app.modules.roxywi import common
from app.modules.roxywi.class_models import ToolInstallRequest
from app.modules.service import installation
from app.modules.tools import common as tools


@pytest.fixture
def pipeline(product, app, monkeypatch):
    calls = []
    for component, latest in dict(checker='5.1.0', metrics='4.0.1', portscanner='2.0.1', socket='2.0.1').items():
        RoxyTool.update(new_version=latest).where(RoxyTool.name == 'roxy-wi-' + component).execute()
    monkeypatch.setattr(tools, 'supports_local_tool_install', lambda: True)
    monkeypatch.setattr(tools, 'return_ssh_keys_path', lambda _: {'host_key': {'key': 'approved'}})
    monkeypatch.setattr(tools.RabbitConnectionSettings, 'load', lambda: SimpleNamespace(
        host='mq.internal', port=5672, username='worker', password='TOP-SECRET', vhost='/roxy'))
    def ansible(inventory, addresses, role):
        assert role == 'roxywi_service'
        address, variables = next(iter(inventory['server']['hosts'].items()))
        payload = variables['roxywi_install']
        server_id = Server.get(Server.ip == address).server_id if addresses else None
        if not addresses:
            assert address == 'localhost' and variables['ansible_connection'] == 'local' and variables['ansible_become']
        calls.append((server_id, payload['stage'], payload))
        engine = 'docker' if server_id else 'native'
        return {'artifact_data': {'roxywi_service': dict(version='5.1.0', state='active', engine=engine,
            installed=True, hostname='target', shared_database=False)}}
    monkeypatch.setattr(installation, 'run_ansible', ansible)
    monkeypatch.setattr(installation, 'run_ansible_locally', lambda inv, role: ansible(inv, [], role))
    def facts(engine):
        return json.dumps(dict(version='5.1.0', state='active', engine=engine, installed=True))
    original_run = tools.subprocess.run
    def local_read(arguments, **kwargs):
        if arguments[:3] == ['sudo', '-n', 'python3']:
            assert kwargs['timeout'] == 7
            return SimpleNamespace(returncode=0, stdout=facts('native'))
        return original_run(arguments, **kwargs)
    monkeypatch.setattr(tools.subprocess, 'run', local_read)
    monkeypatch.setattr(tools.server_mod, 'ssh_command', lambda *args, **kwargs: facts('docker'))
    def run(task_id):
        task = InstallationTasks.get_by_id(task_id)
        assert claim_operation(task.operation_id, task.id)[0]
        with app.app_context():
            return execute_operation(task.operation_id, task.id)
    return SimpleNamespace(calls=calls, run=run)


def install(client, *, json):
    component = json.get('component', 'checker')
    if component not in ('checker', 'metrics', 'portscanner', 'socket', 'keep_alive'):
        component = 'checker'
    return client.post('/admin/tools/update/roxy-wi-' + component, json=json)


def status(client, task_id):
    return client.get('/install/task-status/' + str(task_id)).json


@pytest.mark.parametrize('component', ['checker', 'metrics', 'portscanner', 'socket', 'keep_alive'])
def test_local_install_uses_existing_queue_and_only_records_final_status(product_client, pipeline, component):
    response = install(product_client, json=dict(component=component))
    assert response.status_code == 202, response.text
    task = InstallationTasks.get_by_id(response.json['tasks_ids'][0])
    assert task.server_ids == [] and task.operation_id and task.operation_type == 'ansible'
    assert task.status == 'created' and task.operation_payload.startswith('fernet:')
    assert 'TOP-SECRET' not in task.operation_payload
    payload = deserialize_operation_payload(task.operation_payload)
    assert payload['run_locally'] is True and 'steps' not in payload
    assert pipeline.run(task.id) == 'completed'
    assert [call[1] for call in pipeline.calls] == ['install']
    assert status(product_client, task.id)['status'] == 'completed'
    assert 'TOP-SECRET' not in json.dumps(status(product_client, task.id))


def test_duplicate_request_does_not_create_another_installation(product_client, pipeline):
    body = dict(component='checker', server_id=11)
    response = install(product_client, json=body)
    assert response.status_code == 202
    assert not pipeline.calls
    assert install(product_client, json=body).status_code == 409
    assert install(product_client, json=dict(component='checker')).status_code == 409
    assert InstallationTasks.select().count() == 1
    assert pipeline.run(response.json['tasks_ids'][0]) == 'completed'
    assert pipeline.calls[0][0] == 11
    assert install(product_client, json=body).status_code == 202


@pytest.mark.parametrize('change', [dict(server_id=999), dict(component='keep_alive', server_id=11),
    dict(component='keep_alive', engine='docker'), dict(component='keep_alive', engine='podman'),
    dict(engine='shell'), dict(image='any/image:tag'), dict(start=False), dict(enabled=False),
    dict(rabbit_host='other'), dict(server_id='11'), dict(host='example.com'), dict(password='arbitrary'),
    dict(component='httpd'), dict(socket_port=0), dict(database_url='sqlite:///elsewhere'),
    dict(database_url='mysql://user:pass@host/db\nINJECT=x'), dict(engine='docker', version='latest')])
def test_invalid_options_never_create_a_task(product_client, pipeline, change):
    response = install(product_client, json={'component': 'checker', **change})
    assert response.status_code in (400, 404), response.text
    assert not pipeline.calls and not InstallationTasks.select().exists()


@pytest.mark.parametrize('engine', ['docker', 'podman'])
@pytest.mark.parametrize('component', ['checker', 'metrics', 'portscanner', 'socket'])
def test_container_selection_uses_fixed_repository_and_saved_settings(product_client, pipeline, engine, component):
    response = install(product_client, json=dict(component=component, engine=engine, server_id=11))
    assert response.status_code == 202, response.text
    assert pipeline.run(response.json['tasks_ids'][0]) == 'completed'
    payload = pipeline.calls[-1][2]
    latest = RoxyTool.get(RoxyTool.name == 'roxy-wi-' + component).new_version
    assert payload['image'] == f'ghcr.io/roxy-wi/roxy-wi-{component}:{latest}'
    assert payload['environment'][component.upper() + '_RABBITMQ_HOST'] == 'mq.internal'
    assert payload['environment'][component.upper() + '_RABBITMQ_PASSWORD'] == 'TOP-SECRET'


def test_version_check_updates_both_dialog_and_installation(product_client, pipeline, monkeypatch):
    from app import jobs
    from bs4 import BeautifulSoup
    monkeypatch.setattr(jobs.roxy, 'check_new_version', lambda _: '5.2.9')
    jobs.update_new_versions()
    page = BeautifulSoup(product_client.get('/admin').text, 'html.parser')
    options = json.loads(page.find(id='tool-install-options').text)
    assert options['versions']['checker'] == ['5.2.9']
    assert 'keep_alive' not in options['versions'] and 'prometheus-exporter' not in options['versions']
    assert install(product_client, json=dict(component='checker', engine='docker', version='5.1.0')).status_code == 400
    response = install(product_client, json=dict(component='checker', engine='docker', version='5.2.9'))
    assert response.status_code == 202
    assert pipeline.run(response.json['tasks_ids'][0]) == 'completed'
    assert pipeline.calls[-1][2]['image'] == 'ghcr.io/roxy-wi/roxy-wi-checker:5.2.9'


def test_unknown_latest_version_does_not_use_seeded_current_version(product_client, pipeline):
    RoxyTool.update(new_version='0', current_version='5.0.0').where(RoxyTool.name == 'roxy-wi-checker').execute()
    response = install(product_client, json=dict(component='checker', engine='docker'))
    assert response.status_code == 400 and response.json['error_code'] == 'version_unavailable'
    assert not InstallationTasks.select().exists()
    assert install(product_client, json=dict(component='checker')).status_code == 202


def test_installation_requires_the_existing_service_record(product_client, pipeline):
    RoxyTool.delete().where(RoxyTool.name == 'roxy-wi-checker').execute()
    assert 'checker' not in tools.tool_container_versions()
    assert install(product_client, json=dict(component='checker')).status_code == 400
    assert not InstallationTasks.select().exists()


def test_inspection_returns_existing_runtime_without_rabbitmq_override(product_client, pipeline, monkeypatch):
    monkeypatch.setattr(tools.RabbitConnectionSettings, 'load', lambda: SimpleNamespace(host='127.0.0.1'))
    response = product_client.post('/admin/tools/install/check', json=dict(component='checker', server_id=11))
    assert response.status_code == 200, response.text
    assert response.json['engine'] == 'docker' and response.json['installed'] is True
    assert response.json['version'] == '5.1.0'
    assert not pipeline.calls  # Read-only UI inspection must not launch Ansible.
    assert not InstallationTasks.select().exists()
    response = install(product_client, json=dict(component='checker', server_id=11))
    assert response.status_code == 400 and response.json['error_code'] == 'rabbit_remote_host'


def test_incomplete_inspection_is_not_success(product_client, pipeline, monkeypatch):
    monkeypatch.setattr(tools.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout='{}'))
    response = product_client.post('/admin/tools/install/check', json=dict(component='checker'))
    assert response.status_code == 400 and response.json['error_code'] == 'command_failed'


def test_inspection_timeout_is_a_bounded_error(product_client, pipeline, monkeypatch):
    def timeout(*args, **kwargs):
        raise tools.subprocess.TimeoutExpired('read status', 7)
    monkeypatch.setattr(tools.subprocess, 'run', timeout)
    response = product_client.post('/admin/tools/install/check', json=dict(component='checker'))
    assert response.status_code == 400 and response.json == {'error_code': 'command_failed'}
    assert not pipeline.calls


def test_inspection_uses_one_bounded_existing_ssh_connection(product_client, pipeline, monkeypatch):
    calls = []
    def read(address, command, **kwargs):
        calls.append((address, command, kwargs))
        return json.dumps(dict(engine='podman', installed=True, version='4.0.1', state='active'))
    monkeypatch.setattr(tools.server_mod, 'ssh_command', read)
    response = product_client.post('/admin/tools/install/check', json=dict(component='metrics', server_id=11))
    assert response.status_code == 200 and response.json['engine'] == 'podman'
    assert len(calls) == 1
    assert calls[0][2]['timeout'] == 6 and calls[0][2]['connect_timeout'] == 2
    assert 'TOP-SECRET' not in calls[0][1]
    assert not pipeline.calls


def test_vips_are_excluded_from_options_and_rejected_by_api(product_client, product, pipeline):
    Server.create(server_id=33, hostname='VIP', ip='192.0.2.33', group_id='1', type_ip=1)
    legacy = Server.create(server_id=44, hostname='legacy', ip='192.0.2.44', group_id='1', type_ip=0)
    cluster = HaCluster.create(name='Test', group_id=1, description='')
    router = HaClusterRouter.create(cluster_id=cluster.id, vrid=1)
    vip = HaClusterVip.create(cluster_id=cluster.id, router_id=router.id, vip='192.0.2.44')
    HaClusterVirt.create(cluster_id=cluster.id, vip_id=vip.id, virt_id=legacy.server_id)
    from bs4 import BeautifulSoup
    page = BeautifulSoup(product_client.get('/admin').text, 'html.parser')
    options = json.loads(page.find(id='tool-install-options').text)
    assert {s['id'] for s in options['servers']} == {11, 22}
    assert options['versions']['checker'] == ['5.1.0']
    assert 'images' not in options and 'rabbit_host' not in options
    for server_id in (33, 44):
        assert install(product_client, json=dict(component='checker', server_id=server_id)).status_code == 400
    assert not pipeline.calls


def test_socket_passes_public_key_only(app, product, pipeline, monkeypatch):
    monkeypatch.setitem(app.config, 'JWT_ALGORITHM', 'RS256')
    monkeypatch.setitem(app.config, 'JWT_PUBLIC_KEY', 'public-key')
    monkeypatch.setitem(app.config, 'JWT_PRIVATE_KEY', 'PRIVATE-MUST-STAY')
    with app.test_request_context():
        inv, _ = tools.tool_inventory(ToolInstallRequest(component='socket', engine='podman'))
    payload = inv['server']['hosts']['localhost']['roxywi_install']
    assert payload['public_key'] == 'public-key'
    assert 'SOCKET_JWT_SECRET' not in payload['environment']
    assert 'PRIVATE-MUST-STAY' not in json.dumps(payload)


def test_success_does_not_wait_for_heartbeat_or_add_callbacks(product_client, pipeline):
    response = install(product_client, json=dict(component='socket'))
    task = InstallationTasks.get_by_id(response.json['tasks_ids'][0])
    payload = deserialize_operation_payload(task.operation_payload)
    assert payload['success_action'] is None
    assert not WorkerState.select().exists()
    assert pipeline.run(task.id) == 'completed'
    assert status(product_client, task.id)['status'] == 'completed'


def test_preexisting_worker_status_uses_the_existing_diagnostics(product_client, product, pipeline, monkeypatch):
    from datetime import timedelta
    from app.modules.common.time import utc_now
    monkeypatch.setattr(tools, 'update_cur_tool_versions', lambda: None)
    monkeypatch.setattr(tools, 'is_tool_active', lambda _: 'inactive')
    WorkerState.create(worker_id='manual-install', service='checker', instance_id='original-instance',
                       hostname='old-host', version='5.1.0', status='running',
                       last_heartbeat=utc_now(), expires_at=utc_now() + timedelta(minutes=1))
    response = product_client.get('/admin/tools')
    assert response.status_code == 200
    from bs4 import BeautifulSoup
    row = BeautifulSoup(response.text, 'html.parser').find(id='roxy-wi-checker')
    assert 'Running' in row.text and '5.1.0' in row.text
    diagnostics = product_client.get('/admin/tools/roxy-wi-checker/diagnostics')
    assert diagnostics.status_code == 200
    assert 'old-host' in diagnostics.text and 'original-instance' in diagnostics.text


def test_shared_database_guard_is_passed_to_ansible(product_client, pipeline, monkeypatch):
    monkeypatch.setattr(tools.service_event, 'worker_instances', lambda _: {
        'old': dict(status='running', current=SimpleNamespace(hostname='old-host'))})
    response = install(product_client, json=dict(component='checker'))
    assert response.status_code == 202
    payload = deserialize_operation_payload(InstallationTasks.get_by_id(response.json['tasks_ids'][0]).operation_payload)
    assert payload['inventory']['server']['hosts']['localhost']['roxywi_install']['worker_hosts'] == ['old-host']


def test_failed_ansible_task_shows_error_and_allows_retry(product_client, pipeline, monkeypatch):
    def fail(*_):
        raise RuntimeError('roxywi_error:package_version')
    monkeypatch.setattr(installation, 'run_ansible_locally', fail)
    response = install(product_client, json=dict(component='checker'))
    assert pipeline.run(response.json['tasks_ids'][0]) == 'failed'
    assert status(product_client, response.json['tasks_ids'][0])['error_code'] == 'package_version'
    assert install(product_client, json=dict(component='checker')).status_code == 202


def test_ssh_trust_is_required(product_client, pipeline, monkeypatch):
    monkeypatch.setattr(tools, 'return_ssh_keys_path', lambda _: {})
    response = install(product_client, json=dict(component='socket', server_id=11))
    assert response.status_code == 400 and response.json['error_code'] == 'ssh_unconfirmed'


def test_expired_subscription_and_viewer_cannot_install(product_client, product, pipeline, monkeypatch):
    monkeypatch.setattr(common, 'return_user_subscription', lambda: dict(user_status=0, user_plan='user'))
    assert install(product_client, json=dict(component='checker')).status_code == 403
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    assert install(product_client, json=dict(component='checker')).status_code == 403


def test_existing_task_status_is_scoped_without_exposing_inventory(product_client, product, pipeline):
    response = install(product_client, json=dict(component='checker'))
    task_id = response.json['tasks_ids'][0]
    result = status(product_client, task_id)
    assert result['status'] == 'created'
    assert 'steps' not in result and 'inventory' not in result
    assert 'TOP-SECRET' not in json.dumps(result)
    InstallationTasks.update(group_id=2).where(InstallationTasks.id == task_id).execute()
    assert product_client.get('/install/task-status/' + str(task_id)).status_code == 404


def test_legacy_update_request_uses_ansible_with_local_defaults(product_client, pipeline):
    response = product_client.post('/admin/tools/update/roxy-wi-keep_alive')
    assert response.status_code == 202
    assert pipeline.run(response.json['tasks_ids'][0]) == 'completed'
    assert pipeline.calls[-1][:2] == (None, 'install')


def test_update_url_and_body_must_match(product_client, pipeline):
    response = product_client.post('/admin/tools/update/roxy-wi-socket', json={'component': 'checker'})
    assert response.status_code == 400
    assert not InstallationTasks.select().exists()


def test_package_update_error_reaches_client(product_client, product, monkeypatch):
    monkeypatch.setattr(tools.server_mod, 'subprocess_execute_with_rc', lambda _: dict(
        rc=1, output=[], error='Error: Unable to find a match: roxy-wi-prometheus-exporter'))
    response = product_client.post('/admin/tools/update/roxy-wi-prometheus-exporter')
    assert response.status_code == 502
    assert response.json['error'] == 'Error: Unable to find a match: roxy-wi-prometheus-exporter'


def test_overview_does_not_request_removed_stylesheet(product_client, product):
    response = product_client.get('/overview')
    assert response.status_code == 200
    assert 'new-style.css' not in response.text
