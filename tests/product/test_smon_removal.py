from importlib import import_module
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.common.time import utc_now
from app.modules.db.db_model import Alerts, RoxyTool, Setting, WorkerState
from app.modules.integrations.service_events import WorkerHeartbeat


def test_fresh_installation_has_no_smon(product):
    assert not any(name.startswith('smon') for name in product.db.get_tables())
    assert not RoxyTool.select().where(RoxyTool.name == 'roxy-wi-smon').exists()
    assert not Setting.select().where(Setting.section == 'smon').exists()
    assert RoxyTool.select().where(RoxyTool.name == 'roxy-wi-checker').exists()


def test_upgrade_removes_smon_and_preserves_checker(product):
    database = product.db
    database.execute_sql('CREATE TABLE smon (id INTEGER PRIMARY KEY)')
    database.execute_sql('CREATE TABLE smon_status_pages (id INTEGER PRIMARY KEY)')
    for table in ('smon_history', 'smon_tcp_check', 'smon_http_check', 'smon_ping_check',
                  'smon_dns_check', 'smon_agents', 'smon_status_page_checks'):
        database.execute_sql(
            f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, smon_id INTEGER REFERENCES smon(id))'
        )
    database.execute_sql('INSERT INTO smon VALUES (1)')
    database.execute_sql('INSERT INTO smon_history VALUES (1, 1)')
    RoxyTool.create(name='roxy-wi-smon', current_version='1', new_version='1', is_roxy=1, desc='')
    for group in (1, 2):
        Setting.create(param='master_port', section='smon', value='5100', group_id=group, desc='')
    for service in ('smon', 'checker'):
        WorkerState.create(worker_id=service, service=service, last_heartbeat=utc_now(), expires_at=utc_now())
        Alerts.create(message=service, service='SMON' if service == 'smon' else 'Checker',
                      level='info', ip=product.server.ip, port=0)
    settings_before = Setting.select().where(Setting.section != 'smon').count()
    migration = import_module('app.modules.db.migrations.20261103000000_remove_smon')
    migration.up()
    migration.up()
    assert not any(name.startswith('smon') for name in database.get_tables())
    assert not Setting.select().where(Setting.section == 'smon').exists()
    assert Setting.select().count() == settings_before
    assert not RoxyTool.select().where(RoxyTool.name == 'roxy-wi-smon').exists()
    assert list(WorkerState.select(WorkerState.service).tuples()) == [('checker',)]
    assert list(Alerts.select(Alerts.service).tuples()) == [('Checker',)]
    assert product.server.get_by_id(product.server.server_id).ip == product.server.ip


@pytest.mark.parametrize('path', ['/smon', '/smon/check', '/smon/status-page',
                                 '/smon/agent', '/smon/history/statuses/1'])
def test_retired_endpoints_return_not_found(product_client, path):
    assert product_client.get(path).status_code == 404


@pytest.mark.parametrize('with_alert', [False, True])
def test_checker_history_renders_without_smon(product_client, product, with_alert):
    if with_alert:
        Alerts.create(message='HAProxy is UP', level='info', ip=product.server.ip,
                      port=0, user_group=1, service='Checker')
    response = product_client.get('/checker/history')
    assert response.status_code == 200
    assert '/smon' not in response.text
    if with_alert:
        assert 'HAProxy is UP' in response.text
        assert 'id="alerts_table"' in response.text


def test_smon_heartbeats_are_rejected():
    with pytest.raises(ValidationError, match='unsupported worker service'):
        WorkerHeartbeat(event_id=uuid4(), type='worker.heartbeat', source='smon',
                        worker_id='removed', service='smon', heartbeat_at=utc_now())
