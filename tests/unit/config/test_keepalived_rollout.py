"""Check rollout ordering, failure propagation and evaluated recovery guards."""
from pathlib import Path

from jinja2 import Environment, StrictUndefined
from jinja2.nativetypes import NativeEnvironment
import pytest
import yaml


ROLE = Path(__file__).resolve().parents[3] / 'app/scripts/ansible/roles/keepalived'


def read_tasks(name):
    """Load the actual role instructions instead of duplicating their policies."""
    return yaml.safe_load((ROLE / 'tasks' / name).read_text(encoding='utf-8'))


def task_named(tasks, prefix):
    return next(task for task in tasks if task['name'].startswith(prefix))


@pytest.fixture
def evaluate():
    """Evaluate real task conditions; supply the small Ansible collection helpers."""
    environment = Environment(undefined=StrictUndefined)
    environment.tests['contains'] = lambda values, item: item in values
    environment.filters['extract'] = lambda key, values: values[key]

    def evaluate_condition(expression, **variables):
        return environment.compile_expression(expression)(**variables)

    return evaluate_condition


def test_actual_owners_are_updated_last_and_failures_stop_other_members():
    plays = yaml.safe_load(ROLE.with_suffix('.yml').read_text(encoding='utf-8'))
    assert len(plays) == 3
    preflight, standby, owners = plays
    assert preflight['hosts'] == 'all'
    assert standby['hosts'] == 'roxywi_keepalived_standbys'
    assert owners['hosts'] == 'roxywi_keepalived_owners'
    assert all(play['any_errors_fatal'] is True for play in plays)
    assert standby['serial'] == owners['serial'] == 1
    grouping = task_named(preflight['tasks'], 'Put actual standby')['group_by']['key']
    template = NativeEnvironment(undefined=StrictUndefined).from_string(grouping)
    assert template.render(keepalived_owned_vips=[]) == standby['hosts']
    assert template.render(keepalived_owned_vips=['192.0.2.100']) == owners['hosts']


@pytest.mark.parametrize('owners,valid', (
    ({'a': ['192.0.2.100'], 'b': []}, True),
    ({'a': [], 'b': ['192.0.2.100']}, True),
    ({'a': [], 'b': []}, False),
    ({'a': ['192.0.2.100'], 'b': ['192.0.2.100']}, False),
))
def test_observation_requires_one_owner_for_an_existing_vip(evaluate, owners, valid):
    task = task_named(read_tasks('observe.yml'), 'Require a single owner')
    assert evaluate(task['assert']['that'][0],
                    keepalived_live_owners=owners, item='192.0.2.100') is valid


@pytest.mark.parametrize('current,initial,valid', (
    ([], [], True), (['192.0.2.100'], [], False),
    ([], ['192.0.2.100'], True),
    (['192.0.2.100'], ['192.0.2.100'], True),
))
def test_failover_before_a_standby_update_stops_the_rollout(
    evaluate, current, initial, valid,
):
    task = task_named(read_tasks('deploy.yml'), 'Refuse to restart a standby')
    assert evaluate(
        task['assert']['that'][0], keepalived_owned_vips=initial,
        keepalived_live_owners={'node': current}, inventory_hostname='node',
    ) is valid


def test_validation_backup_and_explicit_failure_are_mandatory():
    tasks = read_tasks('deploy.yml')
    transaction = next(task for task in tasks if 'rescue' in task)
    candidate = task_named(transaction['block'], 'Validate the candidate')
    assert candidate['template']['validate'] == '/usr/sbin/keepalived --config-test -f %s'
    assert candidate['template']['backup'] is True
    assert candidate['no_log'] is True and candidate['diff'] is False
    assert not any(task.get('ignore_errors') or task.get('ignore_unreachable')
                   for task in tasks + transaction['block'] + transaction['rescue'])
    assert 'fail' in transaction['rescue'][-1]
    restore = transaction['rescue'][0]
    assert restore['include_tasks'] == 'rollback_file.yml'
    assert {item['path'] for item in restore['loop']} == {
        '/etc/keepalived/keepalived.conf', '/etc/keepalived/roxy-wi-check-container',
    }
    # Setup cannot restart Keepalived outside the protected transaction.
    assert not any(task.get('service', {}).get('name') == 'keepalived'
                   for task in read_tasks('main.yml'))


@pytest.mark.parametrize('changed,helper_changed,expected', (
    (False, False, 'started'), (True, False, 'restarted'),
    (False, True, 'restarted'), (True, True, 'restarted'),
))
def test_unchanged_config_does_not_restart_a_healthy_member(
    changed, helper_changed, expected,
):
    transaction = next(task for task in read_tasks('deploy.yml') if 'block' in task)
    service = task_named(transaction['block'], 'Start or restart')['service']
    state = NativeEnvironment(undefined=StrictUndefined).from_string(service['state'])
    assert state.render(keepalived_config_result={'changed': changed},
                        keepalived_helper_result={'changed': helper_changed}) == expected


@pytest.mark.parametrize('original,runtime_state,enabled', (
    ({'state': 'running', 'status': 'enabled'}, 'restarted', True),
    ({'state': 'stopped', 'status': 'disabled'}, 'stopped', False),
    ({}, 'stopped', False),
))
def test_rollback_preserves_prior_service_state(original, runtime_state, enabled):
    transaction = next(task for task in read_tasks('deploy.yml') if 'rescue' in task)
    service = task_named(transaction['rescue'], 'Restore the previous')['service']
    environment = NativeEnvironment(undefined=StrictUndefined)
    variables = {'keepalived_previous_service': original}
    assert environment.from_string(service['state']).render(**variables) == runtime_state
    assert environment.from_string(service['enabled']).render(**variables) is enabled


@pytest.mark.parametrize('changes,valid', (
    ({}, True), ({'checksum': 'another-edit'}, False),
    ({'islnk': True}, False), ({'isreg': False}, False), ({'exists': False}, False),
))
def test_rollback_cannot_clobber_concurrent_file_changes(evaluate, changes, valid):
    current = dict(exists=True, isreg=True, islnk=False, checksum='candidate')
    current.update(changes)
    task = task_named(read_tasks('rollback_file.yml')[0]['block'], 'Preserve concurrent')
    assert all(evaluate(
        expression, keepalived_rollback_current={'stat': current},
        keepalived_restore={'result': {'checksum': 'candidate'}},
    ) for expression in task['assert']['that']) is valid


@pytest.mark.parametrize('original,backup,action', (
    (True, True, 'copy'), (True, False, 'file'), (False, False, 'remove'),
))
def test_rollback_handles_replacement_metadata_only_and_new_install(
    evaluate, original, backup, action,
):
    tasks = read_tasks('rollback_file.yml')[0]['block']
    restore = {'original': {'exists': original}, 'result': {}}
    if backup:
        restore['result']['backup_file'] = '/private/backup'
    selected = []
    for prefix, name in (
        ('Restore the original', 'copy'), ('Restore original metadata', 'file'),
        ('Remove a newly created', 'remove'),
    ):
        task = task_named(tasks, prefix)
        conditions = task['when'] if isinstance(task['when'], list) else [task['when']]
        if all(evaluate(value, keepalived_restore=restore) for value in conditions):
            selected.append(name)
    assert selected == [action]


def test_new_cluster_can_start_keepalived_before_queued_proxy_install(evaluate):
    transaction = next(task for task in read_tasks('deploy.yml') if 'rescue' in task)
    task = task_named(transaction['block'], 'Require a working proxy')
    assert evaluate(task['when'], keepalived_required_vips=[]) is False
    assert evaluate(task['when'], keepalived_required_vips=['192.0.2.100']) is True
