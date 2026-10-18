import json
from pathlib import Path
import shlex
from types import SimpleNamespace

from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment
import pytest
import yaml

from app.modules.config import candidate, haproxy_files
from app.modules.service import installation


@pytest.fixture
def startup(monkeypatch):
    root = '/srv/proxy'
    main = "/srv/main configs/proxy's main.cfg"
    state = SimpleNamespace(root=root, main=main, docker=False, calls=[], error='',
                            sources=[{'kind': 'file', 'path': main, 'runtime_path': main}], files=[main])
    settings = {'haproxy_dir': root, 'haproxy_config_path': main, 'haproxy_container_name': 'proxy-custom',
                'nginx_dir': '/srv/web-configs', 'nginx_config_path': "/srv/main configs/web's main.conf",
                'nginx_container_name': 'web-custom'}
    monkeypatch.setattr(installation.sql, 'get_setting', lambda name: settings[name])
    monkeypatch.setattr(installation.server_sql, 'get_server_by_ip', lambda ip: SimpleNamespace(server_id=11))
    monkeypatch.setattr(installation.service_sql, 'select_service_setting', lambda *args: '1' if state.docker else '0')
    monkeypatch.setattr(installation.service_common, 'get_correct_service_name', lambda *args: 'proxy-custom.service')
    # Installation must inspect actual startup, independently of the editor toggle.
    monkeypatch.setattr(haproxy_files, 'multiple_files_enabled', lambda *args: False)

    def ssh(ip, command, **kwargs):
        assert ip == '192.0.2.11' and kwargs['rc'] == 1
        state.calls.append(shlex.split(command))
        return json.dumps(dict(state='error' if state.error else ('ready' if len(state.sources) > 1 else 'single'),
                               code=state.error or 'ready', sources=state.sources, files=state.files, verified_running=True))

    monkeypatch.setattr(installation.server_mod, 'ssh_command', ssh)
    return state


@pytest.mark.parametrize('docker', [False, True])
@pytest.mark.parametrize('multiple', [False, True])
def test_waf_installation_uses_configured_main_and_all_actual_startup_sources(startup, docker, multiple):
    startup.docker = docker
    if multiple:
        startup.sources.append({'kind': 'directory', 'path': startup.root + '/conf.d', 'runtime_path': '/config/conf.d'})
        startup.files.append(startup.root + '/conf.d/app.cfg')
    inventory, servers = installation.generate_waf_inv('192.0.2.11', 'haproxy')
    host = inventory['server']['hosts']['192.0.2.11']
    command = host['HAPROXY_CONFIG_COMMAND']
    spec = json.loads(command[-1])
    assert servers == ['192.0.2.11']
    assert host['SERVICE_PATH'] == startup.root
    assert host['HAPROXY_CONFIG_PATH'] == spec['target'] == spec['main'] == startup.main
    assert spec['root'] == startup.root
    assert spec['sources'] == [source['path'] for source in startup.sources]
    assert spec['container'] == ('proxy-custom' if docker else '')
    assert spec['service'] == 'haproxy' and spec['action'] == 'save'
    assert not spec['candidate'] and not spec['action_command']
    assert command == shlex.split(candidate.candidate_command(
        'haproxy', startup.main, '', 'save', main=startup.main, root=startup.root,
        sources=spec['sources'], container=spec['container']))
    assert len(startup.calls) == 1
    assert startup.calls[0][-4:] == [
        'docker' if docker else 'systemd', 'proxy-custom' if docker else 'proxy-custom.service',
        startup.root, startup.main,
    ]


@pytest.mark.parametrize('error', ['startup_changed', 'permission_denied', 'source_missing'])
def test_waf_installation_refuses_to_guess_sources_when_discovery_fails(startup, error):
    startup.error = error
    with pytest.raises(ValueError, match=error):
        installation.generate_waf_inv('192.0.2.11', 'haproxy')


def test_nginx_installation_does_not_inspect_haproxy(startup):
    inventory, servers = installation.generate_waf_inv('192.0.2.11', 'nginx')
    host = inventory['server']['hosts']['192.0.2.11']
    assert host['SERVICE_PATH'] == '/srv/web-configs'
    spec = json.loads(host['NGINX_CONFIG_COMMAND'][-1])
    assert spec['service'] == 'nginx' and spec['action'] == 'reload'
    assert spec['main'] == spec['target'] == host['NGINX_CONFIG_PATH'] == "/srv/main configs/web's main.conf"
    assert spec['root'] == '/srv/web-configs/waf'
    assert shlex.split(spec['action_command']) == ['sudo', 'systemctl', 'reload', 'proxy-custom.service']
    assert servers == ['192.0.2.11'] and not startup.calls


def test_nginx_container_installation_does_not_modify_the_host(startup):
    startup.docker = True
    with pytest.raises(ValueError, match='container image'):
        installation.generate_waf_inv('192.0.2.11', 'nginx')
    assert not startup.calls


@pytest.mark.parametrize('path', ["/srv/web's", '/srv/règles', '/srv/web*', '/srv/web\tfiles', '/srv/web configs', '/srv/web(1)'])
def test_nginx_install_rejects_directories_unsupported_by_modsecurity(startup, monkeypatch, path):
    monkeypatch.setattr(installation.common, 'get_waf_directory', lambda service: path + '/waf')
    with pytest.raises(ValueError, match='ModSecurity requires nginx_dir'):
        installation.generate_waf_inv('192.0.2.11', 'nginx')
    assert not startup.calls


@pytest.mark.parametrize('service,role,operation', [('haproxy', 'waf', 'save'), ('nginx', 'waf_nginx', 'apply')])
def test_role_supplies_candidate_and_checksum_to_the_existing_transaction(startup, service, role, operation):
    inventory, _ = installation.generate_waf_inv('192.0.2.11', service)
    host = inventory['server']['hosts']['192.0.2.11']
    role = Path(__file__).resolve().parents[3] / f'app/scripts/ansible/roles/{role}/tasks/{service}_config.yml'
    tasks = yaml.safe_load(role.read_text(encoding='utf-8'))[0]['block']
    task = next(task for task in tasks if 'ansible.builtin.command' in task)
    environment = NativeEnvironment(undefined=StrictUndefined)
    environment.filters.update(from_json=json.loads, to_json=json.dumps,
                               combine=lambda value, update: {**value, **update})
    rendered = environment.from_string(task['ansible.builtin.command']['argv']).render(
        **host, **{f'waf_{service}_candidate': {'path': '/tmp/private candidate.cfg'},
                   f'waf_{service}_original': {'stat': {'checksum': 'a' * 64}}},
    )
    command = host[f'{service.upper()}_CONFIG_COMMAND']
    assert rendered[:-1] == command[:-1]
    spec = json.loads(rendered[-1])
    assert spec == {**json.loads(command[-1]),
                   'candidate': '/tmp/private candidate.cfg', 'expected_sha256': 'a' * 64}
    failed = environment.compile_expression(task['failed_when'])
    assert not failed(**{f'waf_{service}_{operation}': {'rc': 0, 'stdout': '{"status":"ok"}'}})
    assert failed(**{f'waf_{service}_{operation}': {'rc': 0, 'stdout': '{"status":"failed","code":"validation_failed"}'}})
    assert failed(**{f'waf_{service}_{operation}': {'rc': 1, 'stdout': ''}})
