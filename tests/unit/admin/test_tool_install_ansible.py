"""Optional services reuse the shared Ansible runner and protect worker settings."""
import base64
import configparser
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from jinja2 import Environment, StrictUndefined

from app.modules.service import installation


ROLE = Path(__file__).resolve().parents[3] / 'app/scripts/ansible/roles/roxywi_service'


def test_local_stage_uses_shared_runner_and_removes_private_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(installation, 'ANSIBLE_PRIVATE_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(installation, 'ANSIBLE_INVENTORY_DIR', str(tmp_path / 'inventory'))
    monkeypatch.setattr(installation.sql, 'get_setting', lambda _: '')
    def no_ssh():
        pytest.fail('Local installation must not start an SSH agent')
    monkeypatch.setattr(installation.server_mod, 'start_ssh_agent', no_ssh)
    observed = []
    def run(**kwargs):
        path = Path(kwargs['inventory'])
        variables = json.loads(path.read_text())['server']['hosts']['localhost']
        assert variables['ansible_connection'] == {'__ansible_unsafe': 'local'}
        assert variables['ansible_become'] is True
        assert variables['roxywi_install']['environment']['PASSWORD'] == {'__ansible_unsafe': 'secret'}
        assert kwargs['playbook'].endswith('/roles/roxywi_service.yml')
        assert kwargs['envvars']['ANSIBLE_REMOTE_TEMP'] == str(tmp_path / 'remote-tmp')
        observed.append(path)
        return SimpleNamespace(rc=0, stats={'failures': {}}, events=[{
            'event': 'playbook_on_stats',
            'event_data': {'artifact_data': {'roxywi_service': {'version': '5.1'}}},
        }])
    monkeypatch.setattr(installation, '_ansible_runner', lambda: SimpleNamespace(run=run))
    result = installation.run_ansible_locally({'server': {'hosts': {'localhost': {
        'ansible_connection': 'local', 'ansible_become': True,
        'roxywi_install': {'environment': {'PASSWORD': 'secret'}, 'stage': 'check'},
    }}}}, 'roxywi_service')
    assert result['artifact_data']['roxywi_service'] == {'version': '5.1'}
    assert len(observed) == 1 and not observed[0].exists()


def render_environment(values, previous=''):
    environment = Environment(undefined=StrictUndefined, trim_blocks=True)
    environment.filters['b64decode'] = lambda text: base64.b64decode(text).decode()
    environment.filters['to_json'] = json.dumps
    template = environment.from_string((ROLE / 'templates/environment.j2').read_text())
    return template.render(roxywi_install={'environment': values},
                           roxywi_service_db_key='CHECKER_DATABASE_URL',
                           roxywi_previous_env={'content': base64.b64encode(previous.encode()).decode()})


def test_environment_preserves_database_and_literal_credentials():
    secret = 'a$`b"c\\d{{ never_template_me }}'
    previous = 'CHECKER_DATABASE_URL="mysql://user:old-secret@db/checker"\nCHECKER_CUSTOM_SETTING=retained\n'
    rendered = render_environment({'CHECKER_RABBITMQ_PASSWORD': secret}, previous)
    values = dict(line.split('=', 1) for line in rendered.splitlines() if line)
    assert json.loads(values['CHECKER_RABBITMQ_PASSWORD']) == secret
    assert values['CHECKER_DATABASE_URL'] == '"mysql://user:old-secret@db/checker"'
    assert values['CHECKER_CUSTOM_SETTING'] == 'retained'


def test_explicit_database_replaces_previous_value_once():
    rendered = render_environment({'CHECKER_DATABASE_URL': 'mysql://new:secret@db/checker'},
                                  'CHECKER_DATABASE_URL="mysql://old:secret@db/checker"\n')
    assert rendered.count('CHECKER_DATABASE_URL=') == 1
    assert 'mysql://new:secret@db/checker' in rendered
    assert 'mysql://old:' not in rendered


def test_podman_env_file_retains_literal_quotes_spaces_and_dollar_signs():
    values = {'METRICS_RABBITMQ_PASSWORD': 'a "secret" $with%spaces\\and{{braces}}'}
    environment = Environment(undefined=StrictUndefined, trim_blocks=True)
    environment.filters['b64decode'] = lambda text: base64.b64decode(text).decode()
    environment.filters['from_json'] = json.loads
    template = environment.from_string((ROLE / 'templates/container_environment.j2').read_text())
    rendered = template.render(roxywi_saved_container_env={
        'content': base64.b64encode(json.dumps(values).encode()).decode(),
    })
    assert dict(line.split('=', 1) for line in rendered.splitlines()) == values


def test_quadlet_options_enable_boot_and_keep_each_section_in_one_fragment():
    tasks = yaml.safe_load((ROLE / 'tasks/container_podman_start.yml').read_text())
    options = next(task['containers.podman.podman_container'] for task in tasks
                   if 'containers.podman.podman_container' in task)
    config = configparser.ConfigParser(interpolation=None)
    environment = Environment(undefined=StrictUndefined)
    # podman_container parses each quadlet_options item independently, with
    # Container as its default section. Separate header/value items are invalid.
    for fragment in options['quadlet_options']:
        rendered = environment.from_string(fragment).render()
        config.read_string('[Container]\n' + rendered)
    assert not dict(config['Container'])
    assert config['Service']['Restart'] == 'on-failure'
    assert config['Install']['WantedBy'] == 'multi-user.target'
    assert 'env' not in options and options['env_file']


@pytest.mark.parametrize('engine,stage,expected', [
    ('native', 'install', []), ('docker', 'check', []),
    ('docker', 'install', [('community.docker:>=4.0.0,<5.0.0', 'community.general:>=9.0.0,<12.0.0')]),
    ('podman', 'install', [('containers.podman:>=1.21.2,<2.0.0',)]),
])
def test_runtime_prepares_only_required_collections(monkeypatch, engine, stage, expected):
    calls = []
    monkeypatch.setattr(installation, '_install_ansible_collections', calls.append)
    installation._prepare_service_collections({'server': {'hosts': {'localhost': {
        'roxywi_install': dict(engine=engine, stage=stage),
    }}}}, 'roxywi_service')
    assert calls == expected


@pytest.mark.parametrize('installed,compatible', [('4.8.1', True), ('5.0.0', False), ('3.13.0', False)])
def test_collection_version_must_support_the_pinned_ansible_core(tmp_path, monkeypatch, installed, compatible):
    path = tmp_path / 'ansible_collections/community/docker'
    path.mkdir(parents=True)
    (path / 'MANIFEST.json').write_text(json.dumps({'collection_info': {'version': installed}}))
    monkeypatch.setattr(installation, 'ANSIBLE_COLLECTION_SEARCH_PATHS', (str(tmp_path),))
    assert installation._collection_is_installed('community.docker:>=4.0.0,<5.0.0') is compatible


def test_playbook_owns_all_installation_steps_and_always_starts_services():
    tasks = yaml.safe_load((ROLE / 'tasks/install.yml').read_text())
    assert tasks[0]['loop'] == ['package', 'configure', 'start', 'verify']
    native = yaml.safe_load((ROLE / 'tasks/start.yml').read_text())[0]['ansible.builtin.systemd_service']
    assert native['enabled'] is True and native['state'] == 'restarted'
    docker = yaml.safe_load((ROLE / 'tasks/container_docker_start.yml').read_text())
    container = next(task['community.docker.docker_container'] for task in docker if 'community.docker.docker_container' in task)
    assert container['restart_policy'] == 'always' and container['state'] == 'started' and container['restart'] is True
    podman = yaml.safe_load((ROLE / 'tasks/container_podman_start.yml').read_text())
    service = next(task['ansible.builtin.systemd_service'] for task in podman if 'ansible.builtin.systemd_service' in task)
    assert service['state'] == 'restarted'


def test_existing_native_installation_is_upgraded_in_place():
    tasks = yaml.safe_load((ROLE / 'tasks/package.yml').read_text())
    for manager in ('apt', 'dnf'):
        options = next(task['ansible.builtin.' + manager] for task in tasks if 'ansible.builtin.' + manager in task)
        assert options['state'] == 'latest'
    apt = next(task['ansible.builtin.apt'] for task in tasks if 'ansible.builtin.apt' in task)
    assert apt['dpkg_options'] == 'force-confdef,force-confold'


@pytest.mark.parametrize('engine,hosts,existing,supplied,allowed', [
    ('native', [], '', '', True),
    ('native', ['target'], '', '', True),
    ('native', ['other'], '', '', False),
    ('native', ['other'], '"mysql://user:pass@db/checker"', '', True),
    ('docker', ['other'], 'sqlite:///local', '', False),
    ('docker', ['other'], 'mysql+pymysql://user:pass@db/checker', '', True),
    ('podman', ['other'], '', 'mysql://user:pass@db/checker', True),
    ('podman', ['other'], '', '', False),
])
def test_shared_database_guard_uses_effective_configuration(engine, hosts, existing, supplied, allowed):
    import re
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
    check = next(task['ansible.builtin.assert']['that'] for task in tasks
                 if task['name'] == 'Require shared storage before adding another worker host')
    environment = Environment(undefined=StrictUndefined)
    environment.filters['difference'] = lambda items, excluded: [item for item in items if item not in excluded]
    environment.tests['search'] = lambda value, pattern: re.search(pattern, value) is not None
    evaluate = environment.compile_expression(check)
    values = {'CHECKER_DATABASE_URL': supplied} if supplied else {}
    assert evaluate(roxywi_install=dict(worker_hosts=hosts, environment=values),
                    ansible_facts=dict(hostname='target'), roxywi_service_engine=engine,
                    roxywi_service_db_key='CHECKER_DATABASE_URL', roxywi_existing_database=existing,
                    roxywi_container_database=existing) is allowed
