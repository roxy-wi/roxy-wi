"""Worker generations, instance summaries and retained diagnostics use real storage."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module

import pytest

from app.modules.common.time import utc_now
from app.modules.db.db_model import WorkerRun, WorkerState
from app.modules.db.service_event import (
    prune_worker_states, record_worker_heartbeat, worker_instances, worker_summary,
)
from app.modules.tools.diagnostics import service_diagnostics


SERVICES = ('checker', 'metrics', 'portscanner', 'socket', 'automation',
            'roxy-wi-web', 'roxy-wi-scheduler', 'roxy-wi-service-events', 'roxy-wi-operations')


def heartbeat(worker_id, *, service='metrics', instance='one', start=None, at=None,
              status='running', groups=None, assignments=1):
    now = utc_now()
    at = at or now
    return dict(worker_id=worker_id, service=service, instance_id=instance, hostname='shared-host',
                status=status, started_at=start or now - timedelta(minutes=1), heartbeat_at=at,
                expires_at=at + timedelta(seconds=30), version='9.2.0',
                group_ids=groups if groups is not None else [1], active_assignments=assignments)


@pytest.mark.parametrize('service', SERVICES)
@pytest.mark.parametrize('reuse_id', [False, True])
def test_restarts_keep_one_instance_and_previous_run(product, service, reuse_id):
    now = utc_now()
    old = heartbeat('before', service=service, start=now - timedelta(hours=2),
                    at=now - timedelta(hours=1), status='stopped', assignments=12)
    new = heartbeat('before' if reuse_id else 'after', service=service, start=now - timedelta(minutes=1))
    record_worker_heartbeat(old)
    record_worker_heartbeat(new)
    record_worker_heartbeat(new)  # delivery retry
    summary = worker_summary()[service]
    assert summary['total'] == summary['active'] == 1
    assert summary['stopped'] == summary['stale'] == summary['degraded'] == 0
    assert summary['assignments'] == 1
    item, = worker_instances(service, history_limit=20).values()
    assert item['current'].started_at == new['started_at']
    assert item['history_count'] == 1
    assert item['history'][0].started_at == old['started_at']
    assert item['history'][0].status == 'stopped'


@pytest.mark.parametrize('reuse_id', [False, True])
def test_late_old_shutdown_updates_history_without_stopping_new_run(product, reuse_id):
    now = utc_now()
    old = heartbeat('before', start=now - timedelta(hours=2), at=now - timedelta(hours=1))
    new = heartbeat('before' if reuse_id else 'after', start=now - timedelta(minutes=1))
    record_worker_heartbeat(old)
    record_worker_heartbeat(new)
    old.update(status='stopped', heartbeat_at=now + timedelta(seconds=1), expires_at=now)
    record_worker_heartbeat(old)
    record_worker_heartbeat(old)
    item, = worker_instances('metrics', history_limit=20).values()
    assert item['current'].started_at == new['started_at']
    assert item['current'].status == 'running'
    assert item['history_count'] == 1
    assert item['history'][0].status == 'stopped'
    assert worker_summary()['metrics']['active'] == 1


def test_new_stopped_run_is_not_hidden_by_old_healthy_run(product):
    now = utc_now()
    record_worker_heartbeat(heartbeat('old', start=now - timedelta(hours=1), at=now - timedelta(minutes=2)))
    record_worker_heartbeat(heartbeat('new', start=now - timedelta(minutes=1), status='stopped'))
    assert worker_summary()['metrics']['stopped'] == 1
    assert worker_summary()['metrics']['active'] == 0


def test_subsecond_restarts_and_repeated_heartbeats_preserve_generation(product):
    now = utc_now().replace(microsecond=0) - timedelta(minutes=1)
    old = heartbeat('fixed', start=now.replace(microsecond=123456), status='stopped')
    new = heartbeat('fixed', start=now.replace(microsecond=654321))
    record_worker_heartbeat(old)
    record_worker_heartbeat(new)
    record_worker_heartbeat(new)
    item, = worker_instances('metrics', history_limit=20).values()
    assert item['current'].started_at == new['started_at']
    assert item['history_count'] == 1
    assert item['history'][0].started_at == old['started_at']


def test_live_overlap_is_visible_but_does_not_duplicate_instance(product):
    now = utc_now()
    record_worker_heartbeat(heartbeat('old', start=now - timedelta(hours=1)))
    record_worker_heartbeat(heartbeat('new', start=now - timedelta(minutes=1)))
    summary = worker_summary()['metrics']
    assert summary['total'] == summary['active'] == summary['degraded'] == 1
    worker, = service_diagnostics('roxy-wi-metrics')['workers']
    assert worker['overlap_count'] == 1
    assert worker['history'][0]['status'] == 'running'


@pytest.mark.parametrize('old_status,expected', [('running', 'running'), ('degraded', 'degraded')])
def test_web_processes_share_one_instance_without_false_overlap(product, old_status, expected):
    now = utc_now()
    record_worker_heartbeat(heartbeat('web', service='roxy-wi-web', start=now - timedelta(hours=1), status=old_status))
    record_worker_heartbeat(heartbeat('web', service='roxy-wi-web', start=now - timedelta(minutes=1)))
    worker, = service_diagnostics('roxy-wi-web')['workers']
    assert worker['status'] == expected
    assert worker['overlap_count'] == 0
    assert worker['history_count'] == 0
    assert worker['parallel_count'] == len(worker['parallel']) == 1
    assert worker['parallel'][0]['status'] == old_status
    summary = worker_summary()['roxy-wi-web']
    assert summary['total'] == summary['active'] == 1
    assert summary['degraded'] == int(expected == 'degraded')


def test_exited_web_child_moves_to_history_without_stopping_instance(product):
    now = utc_now()
    old = heartbeat('web', service='roxy-wi-web', start=now - timedelta(hours=1))
    new = heartbeat('web', service='roxy-wi-web', start=now - timedelta(minutes=1))
    record_worker_heartbeat(old)
    record_worker_heartbeat(new)
    record_worker_heartbeat(dict(new, status='stopped'))
    worker, = service_diagnostics('roxy-wi-web')['workers']
    assert worker['status'] == 'running'
    assert worker['started'] == old['started_at'].isoformat() + 'Z'
    assert worker['history_count'] == 1
    assert worker['history'][0]['status'] == 'stopped'
    assert worker['parallel_count'] == 0


def test_same_host_different_instances_and_missing_identity_are_not_merged(product):
    for worker, instance in [('a', 'one'), ('b', 'two'), ('c', None), ('d', None)]:
        record_worker_heartbeat(heartbeat(worker, instance=instance))
    record_worker_heartbeat(heartbeat('other-service', service='checker', instance='one'))
    assert worker_summary()['metrics']['total'] == 4
    assert worker_summary()['checker']['total'] == 1


@pytest.mark.parametrize('service', ['smon', 'keep_alive'])
def test_excluded_services_keep_existing_behavior(product, service):
    record_worker_heartbeat(heartbeat('old', service=service, status='stopped'))
    record_worker_heartbeat(heartbeat('new', service=service))
    summary = worker_summary()[service]
    assert summary['total'] == 2
    assert summary['stopped'] == summary['active'] == 1
    assert WorkerRun.select().count() == 0


def test_group_access_uses_current_run_not_historical_membership(product):
    now = utc_now()
    record_worker_heartbeat(heartbeat('old', start=now - timedelta(hours=1),
                                     at=now - timedelta(minutes=5), groups=[2]))
    record_worker_heartbeat(heartbeat('new', groups=[3]))
    assert 'metrics' not in worker_summary(group_id=2)
    assert worker_summary(group_id=3)['metrics']['total'] == 1


def test_history_limit_does_not_hide_other_instances_or_inflate_summary(product, monkeypatch):
    monkeypatch.setattr('app.modules.tools.diagnostics.MAX_HISTORY', 2)
    now = utc_now()
    for number in range(110):
        record_worker_heartbeat(heartbeat(str(number), start=now - timedelta(hours=number + 1),
                                         at=now - timedelta(minutes=number + 1), status='stopped'))
    record_worker_heartbeat(heartbeat('current'))
    record_worker_heartbeat(heartbeat('second-instance', instance='two'))
    data = service_diagnostics('roxy-wi-metrics')
    assert len(data['workers']) == 2
    worker = next(row for row in data['workers'] if row['instance'] == 'one')
    assert worker['id'] == 'current'
    assert worker['history_count'] == 110
    assert worker['history_limited']
    assert len(worker['history']) == 2
    assert worker_summary()['metrics']['total'] == 2


def test_reused_id_archives_expire_with_existing_retention(product):
    now = utc_now()
    old = heartbeat('fixed', start=now - timedelta(days=10), at=now - timedelta(days=9), status='stopped')
    record_worker_heartbeat(old)
    record_worker_heartbeat(heartbeat('fixed'))
    assert WorkerRun.select().count() == 1
    assert prune_worker_states() == 1
    assert WorkerRun.select().count() == 0
    assert WorkerState.get_by_id('fixed').status == 'running'


def test_concurrent_generations_keep_newest_and_one_history_record(product):
    now = utc_now()
    payloads = [heartbeat('fixed', start=now - timedelta(hours=2), status='stopped'),
                heartbeat('fixed', start=now - timedelta(minutes=1))]

    def publish(payload):
        with product.db.connection_context():
            record_worker_heartbeat(payload)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(publish, payloads * 4))
    assert WorkerState.get_by_id('fixed').started_at == payloads[1]['started_at']
    assert WorkerRun.select().count() == 1


def test_history_migration_is_idempotent_and_preserves_current_workers(product, monkeypatch):
    record_worker_heartbeat(heartbeat('existing'))
    migration = import_module('app.modules.db.migrations.20261019000000_worker_run_history')
    monkeypatch.setattr(migration, 'connect', lambda: product.db)
    product.db.drop_tables([WorkerRun])
    migration.up()
    migration.up()
    assert WorkerState.get_by_id('existing').instance_id == 'one'
    assert WorkerRun.select().count() == 0
