from datetime import datetime, timedelta, timezone

import pytest
from peewee import MySQLDatabase

from app.modules.db import db_model as models
from app.modules.operations.queue import serialize_operation_payload
from app.modules.service import certificate_operations as operations, certificates


def history_task(product, index, *, servers=None, group_id=1, status='completed'):
    servers = servers if servers is not None else [product.server.server_id, 12]
    started = datetime(2026, 10, 20, 12, tzinfo=timezone.utc) + timedelta(minutes=index)
    payload = dict(name=f'certificate-{index:03}.pem', phase='commit', server_id=servers[0],
                   destination={'path': '/etc/haproxy/certificates.list', 'kind': 'crt_list'} if index % 2 else None,
                   bundle={'key': 'PRIVATE KEY MUST NEVER BE EXPOSED'},
                   targets={str(server): dict(address=f'192.0.2.{server}', status='applied' if status == 'completed' else 'pending',
                                              settings={'secret': 'INTERNAL SETTINGS'}) for server in servers})
    if status == 'failed':
        payload['error_code'] = 'remote_failed'
        payload['targets'][str(servers[-1])].update(status='failed', error_code='remote_failed')
    return models.InstallationTasks.create(service_name='HAProxy certificates', operation_type='certificate',
        server_ids=servers, group_id=group_id, user_id=product.admin.user_id, status=status,
        operation_payload=serialize_operation_payload(payload), start_date=started.astimezone().replace(tzinfo=None),
        finish_date=(started + timedelta(seconds=12)).replace(tzinfo=None))


def test_all_history_is_paged_after_server_and_group_filtering(product_client, product, monkeypatch):
    tasks = [history_task(product, index) for index in range(53)]
    # Newer activity on other servers must not hide older operations on this server.
    for index in range(60):
        history_task(product, index, servers=[111])
    history_task(product, 999, group_id=2)
    history_task(product, 1000).delete_instance()
    models.InstallationTasks.create(service_name='Other operation', server_ids=[11], group_id=1, operation_type='service')
    monkeypatch.setattr(certificates, 'remote', lambda *args: pytest.fail('History must not contact managed servers'))
    seen = []
    for page in range(1, 7):
        response = product_client.get(f'/service/haproxy/certificates/11/history?page={page}')
        assert response.status_code == 200, response.text
        data = response.json
        assert (data['page'], data['pages'], data['total'], data['per_page']) == (page, 6, 53, 10)
        assert len(data['operations']) == (10 if page < 6 else 3)
        seen.extend(item['id'] for item in data['operations'])
        for secret in ('PRIVATE KEY', 'INTERNAL SETTINGS', 'bundle', 'operation_payload'):
            assert secret not in response.text
    assert seen == [task.id for task in reversed(tasks)]
    item = data['operations'][-1]
    assert item['name'] == 'certificate-000.pem'
    assert item['started_at'] == '2026-10-20T12:00:00Z'
    assert item['finished_at'] == '2026-10-20T12:00:12Z'
    assert item['action'] == 'update'
    assert {target['server_id'] for target in item['targets']} == {11, 12}
    data = product_client.get('/service/haproxy/certificates/11/history?page=99&per_page=25').json
    assert (data['page'], data['pages'], len(data['operations'])) == (3, 3, 3)
    assert product_client.get('/service/haproxy/certificates/22/history').status_code == 404
    assert product_client.get('/service/haproxy/certificates/999/history').status_code == 404


def test_history_on_slave_includes_master_operations_and_failure(product_client, product):
    models.Server.create(server_id=12, hostname='Slave', ip='192.0.2.12', group_id='1', master=11, haproxy=1)
    task = history_task(product, 1, status='failed')
    data = product_client.get('/service/haproxy/certificates/12/history').json
    item = data['operations'][0]
    assert item['id'] == task.id and item['retryable']
    assert item['action'] == 'upload_apply'
    assert item['error_code'] == 'remote_failed'
    assert item['targets'][-1]['error_code'] == 'remote_failed'


def test_empty_history_and_service_access(product_client, product):
    response = product_client.get('/service/haproxy/certificates/11/history')
    assert response.json == dict(operations=[], page=1, pages=1, total=0, per_page=10)
    models.User.update(user_services='2 3').where(models.User.user_id == product.admin.user_id).execute()
    assert product_client.get('/service/haproxy/certificates/11/history').status_code == 403


@pytest.mark.parametrize('query', ['page=0', 'page=-1', 'page=no', 'per_page=0', 'per_page=51', 'per_page=no'])
def test_history_rejects_invalid_pagination(product_client, product, query):
    assert product_client.get('/service/haproxy/certificates/11/history?' + query).status_code == 400


def test_mysql_history_filters_json_numeric_server_before_pagination(monkeypatch):
    monkeypatch.setattr(models.InstallationTasks._meta, 'database', MySQLDatabase('history-test'))
    sql, params = operations.server_tasks(11, 1).paginate(2, 10).sql()
    assert 'JSON_CONTAINS' in sql and 'LIMIT %s OFFSET %s' in sql
    assert params == [1, 'certificate', '11', 10, 10]
