"""Regression coverage for generated Keepalived failover and failback policy."""

from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, StrictUndefined
import pytest
import yaml

from app.modules.service import installation
from app.modules.db.db_model import HaClusterRouter


ROLE_DIR = (
    Path(__file__).resolve().parents[3]
    / 'app/scripts/ansible/roles/keepalived'
)
MASTER = '192.0.2.11'
BACKUP = '192.0.2.12'


@pytest.fixture
def render_config():
    """Render with Ansible's whitespace settings and real template variables."""
    environment = Environment(
        loader=FileSystemLoader(str(ROLE_DIR / 'templates')),
        undefined=StrictUndefined,
        trim_blocks=True,
    )
    template = environment.get_template('keepalived.conf.j2')

    def render(host, routers, *, haproxy=True, nginx=False, checks=None):
        variables = {} if checks is None else {'KEEPALIVED_PROXY_CHECKS': checks}
        return template.render(
            ansible_host=host, routers=routers, HAPROXY=haproxy, NGINX=nginx,
            **variables,
        )

    return render


def router(return_master, *, vip='192.0.2.100', master=MASTER, vrid=1):
    """Use integer flags, as returned by the cluster inventory's SQL queries."""
    return {
        'vip': vip,
        'vrid': vrid,
        'return_master': return_master,
        'use_src': 0,
        MASTER: {'master': int(master == MASTER), 'eth': 'eth0'},
        BACKUP: {'master': int(master == BACKUP), 'eth': 'eth0'},
    }


def instance_lines(config, router_id):
    """Read one instance without mixing policies from neighbouring VIPs."""
    instances = re.split(r'(?m)^vrrp_instance ', config)[1:]
    instance = next(value for value in instances if value.startswith(f'VI_{router_id} {{'))
    return [line.strip() for line in instance.splitlines() if line.strip()]


@pytest.mark.parametrize('return_master', (0, 1))
@pytest.mark.parametrize('host', (MASTER, BACKUP))
@pytest.mark.parametrize('haproxy,nginx', ((True, False), (False, True), (True, True)))
def test_proxy_failure_forces_fault_even_without_preemption(
    render_config, return_master, host, haproxy, nginx,
):
    config = render_config(
        host, {'1': router(return_master)}, haproxy=haproxy, nginx=nginx,
    )
    scripts = dict(re.findall(r'vrrp_script (\w+) \{([^{}]*)\}', config))
    tracked = re.search(r'track_script \{([^{}]*)\}', config).group(1).split()
    expected = {
        f'chk_{service}' for service, enabled in (
            ('haproxy', haproxy), ('nginx', nginx),
        ) if enabled
    }

    assert set(scripts) == expected
    assert set(tracked) == expected
    for script in scripts.values():
        lines = [line.strip() for line in script.splitlines()]
        # Weight zero withdraws the VIP instead of merely lowering priority.
        assert 'weight 0' in lines
        # Do not acquire the VIP before the first successful service check.
        assert 'init_fail' in lines


@pytest.mark.parametrize('return_master', (False, True, 0, 1))
@pytest.mark.parametrize('host', (MASTER, BACKUP))
def test_return_master_controls_preemption(render_config, return_master, host):
    lines = instance_lines(render_config(host, {'1': router(return_master)}), '1')

    if return_master:
        assert 'nopreempt' not in lines
        assert f'state {"MASTER" if host == MASTER else "BACKUP"}' in lines
    else:
        # Keepalived ignores nopreempt when the initial state is MASTER.
        assert 'nopreempt' in lines
        assert 'state BACKUP' in lines
        assert 'state MASTER' not in lines
    priority = next(int(line.split()[1]) for line in lines if line.startswith('priority '))
    if host == MASTER:
        assert priority > 101
    else:
        assert priority == 101
    assert 'interface eth0' in lines
    assert 'virtual_router_id 1' in lines
    assert '192.0.2.100' in lines


@pytest.mark.parametrize('host', (MASTER, BACKUP))
def test_failback_policy_is_per_vip(render_config, host):
    config = render_config(host, {
        '1': router(0),
        '2': router(1, vip='192.0.2.101', master=BACKUP, vrid=2),
    })
    sticky = instance_lines(config, '1')
    returning = instance_lines(config, '2')

    assert 'nopreempt' in sticky
    assert 'state BACKUP' in sticky
    assert 'nopreempt' not in returning
    assert f'state {"MASTER" if host == BACKUP else "BACKUP"}' in returning
    assert '192.0.2.100' in sticky
    assert '192.0.2.101' in returning
    for lines in (sticky, returning):
        tracked = re.search(r'track_script \{([^{}]*)\}', '\n'.join(lines))
        assert tracked.group(1).split() == ['chk_haproxy']


def test_cluster_without_proxy_has_no_health_check_dependency(render_config):
    config = render_config(
        MASTER, {'1': router(0)}, haproxy=False, nginx=False,
    )

    assert 'vrrp_script ' not in config
    assert re.search(r'track_script \{\s*\}', config)
    assert 'nopreempt' in instance_lines(config, '1')


@pytest.fixture
def generate_inventory(monkeypatch):
    """Exercise the real inventory builder without reading a production DB."""
    settings = {
        'keepalived_path_logs': '/var/log/keepalived',
        'haproxy_container_name': 'edge-proxy',
        'nginx_container_name': 'edge-web',
    }
    monkeypatch.setattr(installation.sql, 'get_setting', settings.__getitem__)
    registered_router = HaClusterRouter(id=1000, vrid=42)
    monkeypatch.setattr(installation.ha_sql, 'select_cluster_vips', lambda _: [
        SimpleNamespace(router_id=registered_router, vip='192.0.2.100', return_master=0, use_src=0),
    ])
    monkeypatch.setattr(installation.ha_sql, 'select_cluster_slaves_for_inv', lambda _: [
        SimpleNamespace(server_id=SimpleNamespace(ip=host), master=int(index == 1), eth='eth0')
        for index, host in enumerate((MASTER, BACKUP), start=1)
    ])
    monkeypatch.setattr(
        installation.server_sql, 'get_server',
        lambda server_id: SimpleNamespace(ip={1: MASTER, 2: BACKUP}[server_id]),
    )

    def generate(service, options, *, container_name=None, vrid=42):
        registered_router.vrid = vrid
        if container_name is not None:
            settings[f'{service}_container_name'] = container_name
        services = {
            name: {'enabled': False} for name in ('haproxy', 'nginx', 'apache')
        }
        services[service] = {'enabled': True, **options}
        return installation.generate_kp_inv({
            'cluster_id': 1, 'syn_flood': False, 'services': services,
            'servers': [{'id': 1}, {'id': 2}],
        }, 'keepalived')

    return generate


@pytest.mark.parametrize('vrid', (1, 42, 255))
def test_inventory_uses_stored_vrid_without_renaming_instance(
    generate_inventory, render_config, vrid,
):
    inventory, _addresses = generate_inventory('haproxy', {'docker': False}, vrid=vrid)
    for address, host in inventory['server']['hosts'].items():
        assert host['routers']['1000']['vrid'] == vrid
        config = render_config(address, host['routers'])
        assert f'virtual_router_id {vrid}' in instance_lines(config, '1000')
        assert 'virtual_router_id 1000' not in config


@pytest.mark.parametrize('vrid', (None, 0, 256, -1, '42', True))
def test_inventory_rejects_unassigned_or_invalid_vrid(generate_inventory, vrid):
    with pytest.raises(ValueError, match='valid VRID'):
        generate_inventory('haproxy', {'docker': False}, vrid=vrid)


@pytest.mark.parametrize('service,name', (('haproxy', 'edge-proxy'), ('nginx', 'edge-web')))
@pytest.mark.parametrize('options,engine', (
    ({'docker': False}, 'native'),
    ({'docker': True}, 'docker'),
    ({'docker': True, 'container_engine': 'native'}, 'native'),
    ({'docker': False, 'container_engine': 'podman'}, 'podman'),
))
def test_health_check_matches_proxy_installation(
    generate_inventory, render_config, service, name, options, engine,
):
    inventory, addresses = generate_inventory(service, options)
    assert addresses == [MASTER, BACKUP]
    for address, host in inventory['server']['hosts'].items():
        checks = host['KEEPALIVED_PROXY_CHECKS']
        assert set(checks) == {service}
        config = render_config(
            address, host['routers'], haproxy=host['HAPROXY'],
            nginx=host['NGINX'], checks=checks,
        )
        assert 'weight 0' in config and 'init_fail' in config
        if engine == 'native':
            assert f'script "systemctl is-active --quiet {service}"' in config
            assert 'roxy-wi-check-container' not in config
            assert 'user root' not in config
        else:
            expected = f'/etc/keepalived/roxy-wi-check-container {engine} {name}'
            assert f'script "{expected}"' in config
            assert 'user root' in config
            assert 'systemctl is-active' not in config


@pytest.mark.parametrize('name', ('bad;id', 'two words', '--all', 'proxy"', 'proxy\nname'))
def test_container_name_cannot_inject_health_check_arguments(generate_inventory, name):
    with pytest.raises(ValueError, match='Invalid container name'):
        generate_inventory('haproxy', {'docker': True}, container_name=name)


@pytest.fixture(scope='module')
def shell():
    executable = shutil.which('sh')
    if executable:
        return executable
    git_bash = Path('C:/Program Files/Git/bin/bash.exe')
    if git_bash.is_file():
        return str(git_bash)
    pytest.skip('A POSIX shell is required to execute the deployed health check')


@pytest.mark.parametrize('engine', ('docker', 'podman'))
@pytest.mark.parametrize('state,inspect_status,healthy', (
    ('true false false', 0, True),
    ('false false false', 0, False),
    ('true true false', 0, False),
    ('true false true', 0, False),
    ('', 0, False),
    ('unexpected', 0, False),
    ('true false false', 1, False),
))
def test_container_health_check_rejects_unavailable_proxy(
    shell, engine, state, inspect_status, healthy,
):
    # Execute the deployed shell script, replacing only the engine executable.
    wrapper = '''
docker() {
    printf '%s\\n' "$@" >&2
    printf '%s\\n' "$state"
    return "$inspect_status"
}
podman() { docker "$@"; }
helper=$1; engine=$2; state=$3; inspect_status=$4
set -- "$engine" edge-proxy
. "$helper"
'''
    result = subprocess.run(
        [shell, '-c', wrapper, 'health-check', str(ROLE_DIR / 'files/check-container.sh'),
         engine, state, str(inspect_status)],
        capture_output=True, text=True, timeout=10,
    )

    assert (result.returncode == 0) is healthy, result.stderr
    assert result.stderr.splitlines() == [
        'container', 'inspect', '--format',
        '{{.State.Running}} {{.State.Paused}} {{.State.Restarting}}', 'edge-proxy',
    ]


@pytest.mark.parametrize('arguments', ([], ['docker'], ['sh', 'edge-proxy']))
def test_container_health_check_rejects_invalid_invocation(shell, arguments):
    result = subprocess.run(
        [shell, str(ROLE_DIR / 'files/check-container.sh'), *arguments],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 2
    assert result.stderr


def test_container_health_check_is_installed_before_configuration():
    deployment = yaml.safe_load((ROLE_DIR / 'tasks/deploy.yml').read_text(encoding='utf-8'))
    tasks = next(task['block'] for task in deployment if 'rescue' in task)
    helper = next(
        task for task in tasks
        if task.get('copy', {}).get('src') == 'check-container.sh'
    )
    config = next(
        task for task in tasks
        if task.get('template', {}).get('src') == 'keepalived.conf.j2'
    )

    assert tasks.index(helper) < tasks.index(config)
    assert helper['copy']['dest'] == '/etc/keepalived/roxy-wi-check-container'
    assert helper['copy']['owner'] == helper['copy']['group'] == 'root'
    assert helper['copy']['mode'] == '0755'
    condition = Environment(undefined=StrictUndefined).compile_expression(helper['when'])
    assert condition() is False
    for engine in ('native', 'docker', 'podman'):
        assert condition(KEEPALIVED_PROXY_CHECKS={
            'haproxy': {'engine': engine},
        }) is (engine != 'native')
