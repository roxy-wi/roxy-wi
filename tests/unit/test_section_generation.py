import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest
import yaml
from flask import g

from app.modules.common.common_classes import SupportClass
from app.modules.service import installation
from app.views.service.haproxy_section_views import HaproxySectionView
from app.views.service.nginx_section_views import NginxSectionView


ROLES_DIR = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles'
SERVICES = ('haproxy', 'nginx')


@pytest.fixture
def section_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(installation, 'ANSIBLE_PRIVATE_DATA_DIR', str(tmp_path / 'ansible'))
    monkeypatch.setattr(installation.sql, 'get_setting', lambda name: f'/settings/{name}')
    return tmp_path / 'ansible' / 'tmp'


@pytest.mark.parametrize('service', SERVICES)
def test_local_section_playbooks_disable_privilege_escalation_and_facts(service):
    play, = yaml.safe_load((ROLES_DIR / f'{service}_section.yml').read_text(encoding='utf-8'))

    assert play['hosts'] == 'localhost'
    assert play['connection'] == 'local'
    assert play['become'] is False
    assert 'become_method' not in play
    assert play['gather_facts'] is False
    assert play['vars']['ansible_python_interpreter'] == '{{ ansible_playbook_python }}'


def test_nginx_templates_do_not_require_root_ownership():
    tasks = yaml.safe_load((ROLES_DIR / 'nginx_section/tasks/main.yml').read_text(encoding='utf-8'))
    for task in tasks[0]['block']:
        assert 'owner' not in task['template']
        assert 'group' not in task['template']


@pytest.mark.parametrize('service', SERVICES)
@pytest.mark.parametrize('mode', ('package', 'compose', 'kubernetes'))
def test_preview_uses_private_runtime_files_and_cleans_up(service, mode, section_runtime, monkeypatch):
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_MODE', mode)
    generated_paths = []

    def run(inv, role):
        host = inv['server']['hosts']['localhost']
        path = Path(host['cfg'])
        generated_paths.append(path)
        assert role == f'{service}_section'
        assert host['config'] == {'name': 'preview'}
        assert host['action'] == 'create'
        assert host['cert_path'] == '/settings/cert_path'
        assert host['service_dir'] == f'/settings/{service}_dir'
        assert path.parent.parent == section_runtime
        assert path.read_text(encoding='utf-8') == ''
        if os.name == 'posix':
            assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        path.write_text('# Preview: проверка\n', encoding='utf-8')
        return {'failures': {}, 'dark': {}}

    monkeypatch.setattr(installation, 'run_ansible_locally', run)

    for _ in range(2):
        assert installation.generate_section_preview({'name': 'preview'}, service) == '# Preview: проверка\n'

    assert generated_paths[0] != generated_paths[1]
    assert all(not path.parent.exists() for path in generated_paths)
    assert list(section_runtime.iterdir()) == []


@pytest.mark.parametrize('service', SERVICES)
def test_parallel_previews_do_not_share_files(service, section_runtime, monkeypatch):
    barrier = Barrier(2, timeout=10)

    def run(inv, role):
        host = inv['server']['hosts']['localhost']
        Path(host['cfg']).write_text(host['config']['name'], encoding='utf-8')
        barrier.wait()
        return {'failures': {}, 'dark': {}}

    monkeypatch.setattr(installation, 'run_ansible_locally', run)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(installation.generate_section_preview, {'name': name}, service)
                   for name in ('first', 'second')]
        assert [future.result(timeout=15) for future in futures] == ['first', 'second']
    assert list(section_runtime.iterdir()) == []


@pytest.mark.parametrize('service', SERVICES)
@pytest.mark.parametrize('failure', ('inventory', 'runner', 'failed_host', 'unreachable_host', 'read'))
def test_preview_failures_propagate_and_remove_temporary_files(service, failure, section_runtime, monkeypatch):
    def run(inv, role):
        if failure == 'runner':
            raise RuntimeError('Cannot render the requested template')
        if failure == 'read':
            Path(inv['server']['hosts']['localhost']['cfg']).unlink()
        return {
            'failures': {'localhost': 1} if failure == 'failed_host' else {},
            'dark': {'localhost': 1} if failure == 'unreachable_host' else {},
        }

    def bad_inventory(*args):
        raise ValueError('Cannot create section inventory')

    monkeypatch.setattr(installation, 'run_ansible_locally', run)
    if failure == 'inventory':
        monkeypatch.setattr(installation, 'generate_section_inv', bad_inventory)
    expected = {
        'inventory': (ValueError, 'Cannot create section inventory'),
        'runner': (RuntimeError, 'Cannot render the requested template'),
        'failed_host': (RuntimeError, 'failed hosts: localhost'),
        'unreachable_host': (RuntimeError, 'unreachable hosts: localhost'),
        'read': (OSError, 'generated-config'),
    }
    error_type, message = expected[failure]
    with pytest.raises(error_type, match=message):
        installation.generate_section_preview({'name': 'preview'}, service)

    assert list(section_runtime.iterdir()) == []


@pytest.mark.parametrize('service, view', [('haproxy', HaproxySectionView), ('nginx', NginxSectionView)])
@pytest.mark.parametrize('failure', (False, True))
def test_preview_views_use_common_renderer_and_preserve_response_contract(service, view, failure, app, monkeypatch):
    def render(data, requested_service):
        assert requested_service == service
        assert data == {'name': 'preview'}
        if failure:
            raise RuntimeError('Template variable is undefined')
        return 'generated section\n'

    def no_save(*args, **kwargs):
        pytest.fail('A preview must not save or upload a configuration')

    monkeypatch.setattr(installation, 'generate_section_preview', render)
    monkeypatch.setattr(SupportClass, 'return_server_ip_or_id', lambda self, server_id: server_id)
    monkeypatch.setattr(installation.server_sql, 'get_server_with_group', lambda *args: SimpleNamespace(server_id=1))
    monkeypatch.setattr(view, '_edit_config', no_save)
    body = SimpleNamespace(model_dump=lambda **kwargs: {'name': 'preview'})

    with app.test_request_context('/'):
        g.user_params = {'group_id': 1}
        response, status = view().post(service, 'test', 1, body, SimpleNamespace(generate=True))

    if failure:
        assert status == 500
        assert 'Template variable is undefined' in response['error']
        assert 'Apache' not in response['error']
    else:
        assert status == 200
        assert response == {'data': 'generated section\n'}
