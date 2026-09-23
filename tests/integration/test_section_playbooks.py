import os
from pathlib import Path

import pytest

from app.modules.roxywi.class_models import (
    HaproxyConfigRequest,
    HaproxyUserListRequest,
    NginxProxyPassRequest,
    NginxUpstreamRequest,
)
from app.modules.service import installation


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Ansible requires a POSIX control node')
ROLES_DIR = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles'


@pytest.fixture
def section_runtime(tmp_path, monkeypatch):
    private = tmp_path / 'ansible'
    monkeypatch.setattr(installation, 'ANSIBLE_PRIVATE_DATA_DIR', str(private))
    monkeypatch.setattr(installation, 'ANSIBLE_INVENTORY_DIR', str(private / 'inventory'))
    monkeypatch.setattr(installation, 'ANSIBLE_ROLE_SEARCH_PATHS', (str(ROLES_DIR),))
    monkeypatch.setattr(installation, '_ANSIBLE_PLAYBOOKS', {
        f'{service}_section': str(ROLES_DIR / f'{service}_section.yml')
        for service in ('nginx', 'haproxy')
    })
    monkeypatch.setattr(installation.sql, 'get_setting', lambda name: {
        'cert_path': '/etc/ssl', 'haproxy_dir': '/etc/haproxy', 'nginx_dir': '/etc/nginx',
    }.get(name))
    return private


@pytest.mark.security
@pytest.mark.parametrize('expression', [
    "{{ lookup('pipe', 'touch MARKER') }}",
    "{% if lookup('pipe', 'touch MARKER') %}value{% endif %}",
    '{{ 31337 + 1 }}',
    '$host literal header',
])
def test_section_inventory_strings_are_literal_after_loading(expression, section_runtime, tmp_path):
    marker = tmp_path / 'lookup-must-not-run'
    expression = expression.replace('MARKER', str(marker))
    config = NginxProxyPassRequest(
        name='example.com', port=8080, security={},
        locations=[{'upstream': 'test_backend', 'headers': [
            {'action': 'add_header', 'name': 'X-Test', 'value': expression},
        ]}],
    )
    rendered = installation.generate_section_preview(config.model_dump(mode='json'), 'nginx')
    assert not marker.exists()
    assert expression in rendered
    assert list((section_runtime / 'inventory').iterdir()) == []


@pytest.mark.parametrize('service, config, expected', [
    pytest.param(
        'haproxy',
        HaproxyConfigRequest(
            name='test_plain_listener', type='listen', mode='http', ssl=None,
            binds=[{'ip': '', 'port': 18080}],
            backend_servers=[{
                'server': '192.0.2.12', 'port': 8080, 'port_check': 8080,
                'send_proxy': False, 'backup': False,
            }],
        ),
        ('listen test_plain_listener', 'bind :18080', 'mode http',
         'server 192.0.2.12 192.0.2.12:8080 port 8080'),
        id='haproxy-listener-without-ssl',
    ),
    pytest.param(
        'haproxy',
        HaproxyUserListRequest(
            name='test_users', type='userlist', userlist_groups=['readers'],
            userlist_users=[{'user': 'alice', 'password': 'test-password', 'group': 'readers'}],
        ),
        ('userlist test_users', 'user alice insecure-password test-password groups readers'),
        id='haproxy-userlist',
    ),
    pytest.param(
        'nginx',
        NginxUpstreamRequest(
            name='test_backend', balance='least_conn',
            backend_servers=[{'server': '192.0.2.10', 'port': 8080, 'max_fails': 3, 'fail_timeout': 10}],
        ),
        ('upstream test_backend', 'least_conn;', 'server 192.0.2.10:8080'),
        id='nginx-upstream',
    ),
    pytest.param(
        'nginx',
        NginxProxyPassRequest(
            name='example.com', port=8080, security={},
            locations=[{'upstream': 'test_backend', 'headers': []}],
        ),
        ('server_name example.com', 'listen 8080;', 'proxy_pass http://test_backend;'),
        id='nginx-proxy-pass',
    ),
])
def test_real_section_generation_without_sudo(service, config, expected, tmp_path, monkeypatch):
    private_data_dir = tmp_path / 'ansible'
    inventory_dir = private_data_dir / 'inventory'
    monkeypatch.setattr(installation, 'ANSIBLE_PRIVATE_DATA_DIR', str(private_data_dir))
    monkeypatch.setattr(installation, 'ANSIBLE_INVENTORY_DIR', str(inventory_dir))
    monkeypatch.setattr(installation, 'ANSIBLE_ROLE_SEARCH_PATHS', (str(ROLES_DIR),))
    monkeypatch.setattr(installation, '_ANSIBLE_PLAYBOOKS', {
        f'{service}_section': str(ROLES_DIR / f'{service}_section.yml'),
    })
    monkeypatch.setattr(installation.sql, 'get_setting', lambda name: {
        'cert_path': '/etc/ssl', 'haproxy_dir': '/etc/haproxy', 'nginx_dir': '/etc/nginx',
    }.get(name))
    prepare_environment = installation._prepare_ansible_runtime_dirs

    def environment_without_system_python():
        environment = prepare_environment()
        environment['ANSIBLE_PYTHON_INTERPRETER'] = str(tmp_path / 'system-python-must-not-be-used')
        return environment

    monkeypatch.setattr(installation, '_prepare_ansible_runtime_dirs', environment_without_system_python)
    # The play must override inherited become settings. No sudo executable is
    # available to it, even when the CI host has passwordless sudo installed.
    monkeypatch.setenv('ANSIBLE_BECOME', 'true')
    monkeypatch.setenv('ANSIBLE_BECOME_EXE', str(tmp_path / 'sudo-must-not-be-called'))
    monkeypatch.setenv('ANSIBLE_BECOME_USER', 'root')

    rendered = installation.generate_section_preview(config.model_dump(mode='json'), service)

    for snippet in expected:
        assert snippet in rendered
    assert list(inventory_dir.iterdir()) == []
    assert not list((private_data_dir / 'tmp').glob('roxywi-*-section-*'))
