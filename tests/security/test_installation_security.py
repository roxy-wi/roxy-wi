import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import g

from app.modules.db.db_model import InstallationTasks
from app.modules.roxywi.class_models import HAClusterRequest, HAClusterService, ServerInstall, ServiceInstall
from app.modules.roxywi.exception import RoxywiGroupMismatch
from app.modules.service import installation
from app.views.ha.views import HAView


def _service_install(*server_ids: int) -> ServiceInstall:
    return ServiceInstall(
        servers=[ServerInstall(id=server_id, master=False) for server_id in server_ids],
        services={'haproxy': HAClusterService(enabled=True, docker=False)},
        checker=False,
        metrics=False,
        auto_start=False,
        syn_flood=False,
        docker=False,
    )


@pytest.mark.security
def test_installation_authorizes_every_server_from_request_body(app, monkeypatch):
    servers = {
        10: SimpleNamespace(server_id=10, ip='192.0.2.10', group_id=7),
        20: SimpleNamespace(server_id=20, ip='198.51.100.20', group_id=9),
    }
    generator_called = False

    def generate_inventory(*args, **kwargs):
        nonlocal generator_called
        generator_called = True
        return {}, []

    monkeypatch.setattr(installation.server_sql, 'get_server', lambda server_id: servers[server_id])
    monkeypatch.setattr(installation, 'generate_haproxy_inv', generate_inventory)

    with app.test_request_context('/install/haproxy/10'):
        g.user_params = {'group_id': 7, 'role': 2}
        with pytest.raises(RoxywiGroupMismatch):
            installation.install_service('haproxy', _service_install(10, 20))

    assert generator_called is False


@pytest.mark.security
def test_service_activation_is_serialized_for_the_operations_worker(app, monkeypatch):
    captured = {}

    monkeypatch.setattr(
        installation.server_sql,
        'get_server',
        lambda server_id: SimpleNamespace(server_id=server_id, ip='192.0.2.10', group_id=7),
    )
    monkeypatch.setattr(
        installation,
        'generate_haproxy_inv',
        lambda json_data, service: ({'server': {'hosts': {'192.0.2.10': {}}}}, ['192.0.2.10']),
    )
    def start_task(inv, server_ips, ansible_role, service_name, success_action=None):
        captured['success_action'] = success_action
        return 123

    monkeypatch.setattr(installation, 'run_ansible_thread', start_task)

    with app.test_request_context('/install/haproxy/10'):
        g.user_params = {'group_id': 7, 'role': 2}
        assert installation.install_service('haproxy', _service_install(10)) == 123

    assert captured['success_action']['type'] == 'service-installed'
    assert captured['success_action']['server_ips'] == ['192.0.2.10']
    assert captured['success_action']['service'] == 'haproxy'


@pytest.mark.security
def test_failed_installation_task_is_not_overwritten_as_completed(monkeypatch):
    task = InstallationTasks.create(service_name='Failed test installation', server_ids=[])
    callback_called = False

    def success_callback():
        nonlocal callback_called
        callback_called = True

    monkeypatch.setattr(
        installation,
        'run_ansible',
        lambda inv, server_ips, service: {'failures': {'192.0.2.10': 1}, 'dark': {}},
    )
    monkeypatch.setattr(installation.roxywi_common, 'logging', lambda *args, **kwargs: None)

    try:
        installation.run_installations({}, ['192.0.2.10'], 'haproxy', task.id, success_callback)
        stored_task = InstallationTasks.get_by_id(task.id)
        assert stored_task.status == 'failed'
        assert stored_task.error == 'Installation failed (failed hosts: 192.0.2.10)'
        assert 'Apache' not in stored_task.error
        assert callback_called is False
    finally:
        task.delete_instance()


@pytest.mark.security
def test_successful_installation_activates_service_before_completing_task(monkeypatch):
    task = InstallationTasks.create(service_name='Successful test installation', server_ids=[])
    statuses_during_callback = []

    monkeypatch.setattr(
        installation,
        'run_ansible',
        lambda inv, server_ips, service: {'failures': {}, 'dark': {}},
    )

    def success_callback():
        statuses_during_callback.append(InstallationTasks.get_by_id(task.id).status)

    try:
        installation.run_installations({}, ['192.0.2.10'], 'haproxy', task.id, success_callback)
        stored_task = InstallationTasks.get_by_id(task.id)
        assert statuses_during_callback == ['running']
        assert stored_task.status == 'completed'
        assert stored_task.error is None
    finally:
        task.delete_instance()


@pytest.mark.security
def test_ansible_inventory_is_private_unique_and_removed_after_runner_error(tmp_path, monkeypatch):
    private_data_dir = tmp_path / 'ansible'
    inventory_dir = private_data_dir / 'inventory'
    observed = {}
    stopped_agents = []

    monkeypatch.setattr(installation, 'ANSIBLE_PRIVATE_DATA_DIR', str(private_data_dir))
    monkeypatch.setattr(installation, 'ANSIBLE_INVENTORY_DIR', str(inventory_dir))
    monkeypatch.setattr(installation, '_install_ansible_collections', lambda: None)
    monkeypatch.setattr(installation.sql, 'get_setting', lambda setting: None)
    monkeypatch.setattr(
        installation,
        'return_ssh_keys_path',
        lambda server_ip: {
            'enabled': False,
            'key': '',
            'password': 'temporary-secret',
            'user': 'deploy',
            'port': 22,
        },
    )
    monkeypatch.setattr(
        installation.server_mod,
        'start_ssh_agent',
        lambda: {'pid': 100, 'socket': '/tmp/test-agent.sock'},
    )
    monkeypatch.setattr(
        installation.server_mod,
        'stop_ssh_agent',
        lambda agent: stopped_agents.append(agent),
    )

    class FailingRunner:
        @staticmethod
        def run(**kwargs):
            inventory_path = Path(kwargs['inventory'])
            observed['path'] = inventory_path
            observed['data'] = json.loads(inventory_path.read_text(encoding='utf-8'))
            observed['mode'] = stat.S_IMODE(inventory_path.stat().st_mode)
            observed['local_temp'] = kwargs['envvars']['ANSIBLE_LOCAL_TEMP']
            observed['control_path'] = kwargs['envvars']['ANSIBLE_SSH_CONTROL_PATH_DIR']
            raise RuntimeError('runner failed')

    monkeypatch.setattr(installation, '_ansible_runner', lambda: FailingRunner)
    inventory = {'server': {'hosts': {'192.0.2.10': {'DOCKER': False}}}}

    with pytest.raises(RuntimeError, match='runner failed'):
        installation.run_ansible(inventory, ['192.0.2.10'], 'haproxy')

    assert observed['data']['server']['hosts']['192.0.2.10']['ansible_password'] == 'temporary-secret'
    if os.name == 'posix':
        assert observed['mode'] == 0o600
        assert stat.S_IMODE(inventory_dir.stat().st_mode) == 0o700
    assert observed['path'].name.startswith('roxywi-inventory-')
    assert observed['local_temp'] == str(private_data_dir / 'tmp')
    assert observed['control_path'] == str(private_data_dir / 'cp')
    assert not observed['path'].exists()
    assert list(inventory_dir.iterdir()) == []
    assert stopped_agents == [{'pid': 100, 'socket': '/tmp/test-agent.sock'}]


@pytest.mark.security
def test_ansible_runner_failure_is_saved_as_a_specific_task_error(tmp_path, monkeypatch):
    private_data_dir = tmp_path / 'ansible'
    inventory_dir = private_data_dir / 'inventory'

    monkeypatch.setattr(installation, 'ANSIBLE_PRIVATE_DATA_DIR', str(private_data_dir))
    monkeypatch.setattr(installation, 'ANSIBLE_INVENTORY_DIR', str(inventory_dir))
    monkeypatch.setattr(installation, '_install_ansible_collections', lambda: None)
    monkeypatch.setattr(installation, '_install_ansible_roles', lambda role: None)
    monkeypatch.setattr(installation.sql, 'get_setting', lambda setting: None)
    monkeypatch.setattr(
        installation,
        'return_ssh_keys_path',
        lambda server_ip: {
            'enabled': False,
            'key': '',
            'password': 'temporary-secret',
            'user': 'deploy',
            'port': 22,
        },
    )
    monkeypatch.setattr(
        installation.server_mod,
        'start_ssh_agent',
        lambda: {'pid': 100, 'socket': '/tmp/test-agent.sock'},
    )
    monkeypatch.setattr(installation.server_mod, 'stop_ssh_agent', lambda agent: None)

    class FailedResult:
        rc = 2
        status = 'failed'
        stats = {'failures': {'192.0.2.10': 1}, 'dark': {}}

    class FailedRunner:
        @staticmethod
        def run(**kwargs):
            kwargs['event_handler']({
                'event': 'runner_on_failed',
                'event_data': {
                    'host': '192.0.2.10',
                    'task': 'Install HAProxy package',
                    'res': {'msg': 'No package matching haproxy is available'},
                },
            })
            return FailedResult()

    monkeypatch.setattr(installation, '_ansible_runner', lambda: FailedRunner)
    inventory = {'server': {'hosts': {'192.0.2.10': {'DOCKER': False}}}}

    with pytest.raises(RuntimeError) as error:
        installation.run_ansible(inventory, ['192.0.2.10'], 'haproxy')

    message = str(error.value)
    assert message == 'No package matching haproxy is available'
    assert 'Apache' not in message


@pytest.mark.security
def test_ansible_internal_error_returns_only_the_useful_message():
    failures = []
    output_lines = []
    installation._capture_ansible_failure(
        failures,
        output_lines,
        {
            'event': 'verbose',
            'stdout': "ERROR! Unexpected Exception: [Errno 30] Read-only file system: '/usr/share/httpd/.ansible/tmp'",
        },
    )

    assert installation._ansible_runner_error(failures, output_lines) == (
        "[Errno 30] Read-only file system: '/usr/share/httpd/.ansible/tmp'"
    )


@pytest.mark.security
def test_ansible_uses_writable_runtime_temp_directory(tmp_path, monkeypatch):
    temp_directory = tmp_path / 'ansible' / 'tmp'
    control_path_directory = tmp_path / 'ansible' / 'cp'
    monkeypatch.setattr(installation, 'ANSIBLE_PRIVATE_DATA_DIR', str(tmp_path / 'ansible'))

    runtime_environment = installation._prepare_ansible_runtime_dirs()

    assert runtime_environment == {
        'ANSIBLE_LOCAL_TEMP': str(temp_directory),
        'ANSIBLE_SSH_CONTROL_PATH_DIR': str(control_path_directory),
    }
    assert temp_directory.is_dir()
    assert control_path_directory.is_dir()
    if os.name == 'posix':
        assert stat.S_IMODE(temp_directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(control_path_directory.stat().st_mode) == 0o700


@pytest.mark.security
def test_galaxy_role_is_downloaded_to_persistent_runtime_directory(tmp_path, monkeypatch):
    private_data_dir = tmp_path / 'ansible'
    roles_dir = private_data_dir / 'roles'
    commands = []

    monkeypatch.setattr(installation, 'ANSIBLE_PRIVATE_DATA_DIR', str(private_data_dir))
    monkeypatch.setattr(installation, 'ANSIBLE_ROLES_DIR', str(roles_dir))
    monkeypatch.setattr(installation, 'ANSIBLE_ROLE_SEARCH_PATHS', (str(roles_dir),))
    monkeypatch.setattr(installation, '_galaxy_environment', lambda: {'TEST': '1'})
    monkeypatch.setattr(
        installation.subprocess,
        'run',
        lambda command, **kwargs: commands.append((command, kwargs)) or SimpleNamespace(returncode=0),
    )

    installation._install_ansible_roles('nginx')

    assert roles_dir.is_dir()
    assert commands == [(
        [
            'ansible-galaxy', 'role', 'install', 'nginxinc.nginx,0.24.3', '-f',
            '--roles-path', str(roles_dir),
        ],
        {'env': {'TEST': '1'}, 'check': False},
    )]


@pytest.mark.security
def test_galaxy_dependencies_can_be_found_in_read_only_fallbacks(tmp_path, monkeypatch):
    bundled_roles = tmp_path / 'bundled-roles'
    bundled_collections = tmp_path / 'bundled-collections'
    (bundled_roles / 'nginxinc.nginx').mkdir(parents=True)
    (bundled_collections / 'ansible_collections' / 'community' / 'general').mkdir(parents=True)

    monkeypatch.setattr(installation, 'ANSIBLE_ROLE_SEARCH_PATHS', (str(bundled_roles),))
    monkeypatch.setattr(installation, 'ANSIBLE_COLLECTION_SEARCH_PATHS', (str(bundled_collections),))
    monkeypatch.setattr(
        installation.subprocess,
        'run',
        lambda *_args, **_kwargs: pytest.fail('ansible-galaxy should not be called'),
    )

    assert installation._role_is_installed('nginxinc.nginx') is True
    assert installation._collection_is_installed('community.general') is True
    installation._install_ansible_roles('nginx')


@pytest.mark.security
def test_secure_inventory_uses_a_unique_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(installation, 'ANSIBLE_INVENTORY_DIR', str(tmp_path))
    first = installation._create_secure_inventory({'server': {'hosts': {}}})
    second = installation._create_secure_inventory({'server': {'hosts': {}}})

    try:
        assert first != second
    finally:
        installation._remove_inventory(first)
        installation._remove_inventory(second)


@pytest.mark.security
def test_inventory_cleanup_refuses_paths_outside_inventory_directory(tmp_path, monkeypatch):
    inventory_directory = tmp_path / 'inventory'
    inventory_directory.mkdir()
    outside_inventory = tmp_path / 'roxywi-inventory-outside.json'
    outside_inventory.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(installation, 'ANSIBLE_INVENTORY_DIR', str(inventory_directory))
    monkeypatch.setattr(installation.roxywi_common, 'logging', lambda *_args, **_kwargs: None)

    installation._remove_inventory(str(outside_inventory))

    assert outside_inventory.exists()


@pytest.mark.security
def test_ansible_playbook_rejects_unapproved_role_names():
    assert installation._ansible_playbook('haproxy').endswith('/roles/haproxy.yml')
    with pytest.raises(ValueError, match='Unsupported Ansible role'):
        installation._ansible_playbook('../../tmp/attacker')


def test_ha_cluster_installation_returns_flat_task_ids(app, monkeypatch):
    task_ids = iter((101, 102))
    calls = []

    def install_service(service, body, cluster_id=None):
        calls.append((service, cluster_id))
        return next(task_ids)

    monkeypatch.setattr('app.views.ha.views.service_mod.install_service', install_service)
    body = HAClusterRequest(
        name='test-cluster',
        return_master=True,
        syn_flood=True,
        use_src=True,
        virt_server=True,
        reconfigure=False,
        services={
            'haproxy': HAClusterService(enabled=True, docker=False),
            'nginx': HAClusterService(enabled=False, docker=False),
        },
    )

    with app.test_request_context('/ha/cluster/42'):
        response, status = HAView._install_service(body, 42)

    assert status == 202
    assert response.get_json() == {'status': 'accepted', 'tasks_ids': [101, 102]}
    assert calls == [('keepalived', 42), ('haproxy', None)]
