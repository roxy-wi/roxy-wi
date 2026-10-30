"""Reports and queued probes belong to a server registration, not a reusable ID."""
import importlib
from threading import Thread

import pytest
from peewee import SqliteDatabase

from app.modules.db import server as server_sql
from app.modules.db.db_model import InstallationTasks, OperationalAssessment, Server
from app.modules.operations.queue import serialize_operation_payload
from app.modules.roxywi.exception import RoxywiResourceNotFound
from app.modules.service import proxy_assessments as diagnostic
from tests.product.test_proxy_diagnostics import diagnostic_host, finish, queue


def test_generic_nonproxy_assessment_serialization_keeps_its_own_subject(product):
    row = OperationalAssessment.create(group_id=1, user_id=product.admin.user_id,
        kind='served-tls', subject='123', result=serialize_operation_payload({'scope': 'monitor history'}))
    assert diagnostic.public(row)['report'] == {'scope': 'monitor history'}


def test_history_rechecks_registration_after_an_independent_committed_replacement(
        product_client, registered_proxy, diagnostic_host, monkeypatch):
    first = queue(product_client, registered_proxy.server_id)
    finish(first)
    finish(queue(product_client, registered_proxy.server_id))
    database = Server._meta.database
    original = diagnostic.public
    calls = []
    errors = []
    replacement = []
    def replace_on_other_connection():
        try:replacement.append(replace_registration(registered_proxy))
        except Exception as error:errors.append(error)
        finally:database.close()
    def public_with_concurrent_replacement(row):
        if not calls:
            calls.append(True)
            thread = Thread(target=replace_on_other_connection, daemon=True)
            thread.start();thread.join(timeout=5)
            assert not thread.is_alive() and not errors
        return original(row)
    monkeypatch.setattr(diagnostic, 'public', public_with_concurrent_replacement)
    def forbidden_decrypt(_value):
        pytest.fail('A committed replacement registration must be seen before report decryption')
    monkeypatch.setattr(diagnostic, 'unseal', forbidden_decrypt)
    response = product_client.get('/insights/api/diagnostics', query_string=dict(
        service='haproxy', server_id=registered_proxy.server_id))
    assert response.status_code == 404, response.text
    assert len(replacement) == 1 and history(product_client, replacement[0]) == []


@pytest.fixture
def registered_proxy(product):
    values = {key: value for key, value in product.server.__data__.items()
              if key not in ('server_id', 'registration_key', 'registration_uuid')}
    values.update(hostname='Synthetic registration target', ip='192.0.2.33')
    # The highest SQLite primary key will be naturally reused after deletion.
    created = Server.create(**values)
    return Server.get_by_id(created.server_id)


def replace_registration(server, *, same_ip=True):
    values = {key: value for key, value in server.__data__.items()
              if key not in ('server_id', 'registration_key', 'registration_uuid')}
    if not same_ip:
        values['ip'] = '192.0.2.199'
    assert server_sql.delete_server(server.server_id)
    if isinstance(Server._meta.database, SqliteDatabase):
        replacement = Server.create(**values)
    else:
        # Exercise the same numeric-ID replacement on monotonic MySQL as well.
        replacement = Server.create(server_id=server.server_id, **values)
    assert replacement.server_id == server.server_id
    assert (replacement.ip == server.ip) is same_ip
    return Server.get_by_id(replacement.server_id)


def history(client, server):
    response = client.get('/insights/api/diagnostics', query_string=dict(
        service='haproxy', server_id=server.server_id))
    assert response.status_code == 200, response.text
    return response.json['data']


@pytest.mark.parametrize('same_ip', [True, False])
def test_reused_server_id_cannot_inherit_completed_history_or_direct_report(
        product_client, registered_proxy, diagnostic_host, same_ip):
    response = queue(product_client, registered_proxy.server_id)
    finish(response)
    old_id = response.json['id']
    assert [row['id'] for row in history(product_client, registered_proxy)] == [old_id]
    assert product_client.get(f'/insights/api/assessments/{old_id}').status_code == 200
    encrypted = OperationalAssessment.get_by_id(old_id).result

    replacement = replace_registration(registered_proxy, same_ip=same_ip)
    assert history(product_client, replacement) == []
    assert product_client.get(f'/insights/api/assessments/{old_id}').status_code == 404
    # Preserve historical evidence; do not relabel or delete it as a shortcut.
    assert OperationalAssessment.get_by_id(old_id).result == encrypted

    fresh = queue(product_client, replacement.server_id)
    finish(fresh)
    assert [row['id'] for row in history(product_client, replacement)] == [fresh.json['id']]


@pytest.mark.parametrize('same_ip', [True, False])
def test_queued_work_cannot_probe_a_replacement_registration(
        product_client, registered_proxy, diagnostic_host, same_ip):
    response = queue(product_client, registered_proxy.server_id)
    assert response.status_code == 202, response.text
    task = InstallationTasks.get_by_id(response.json['task_id'])
    replacement = replace_registration(registered_proxy, same_ip=same_ip)

    assert diagnostic.execute(task) == 'failed'
    assert diagnostic_host.discoveries == [] and diagnostic_host.calls == []
    assert OperationalAssessment.get_by_id(response.json['id']).result == ''
    assert history(product_client, replacement) == []
    assert product_client.get(f'/insights/api/assessments/{response.json["id"]}').status_code == 404


def test_previous_registration_queue_does_not_block_a_fresh_registration(
        product_client, registered_proxy, diagnostic_host):
    old = queue(product_client, registered_proxy.server_id)
    assert old.status_code == 202
    replacement = replace_registration(registered_proxy)
    fresh = queue(product_client, replacement.server_id)
    assert fresh.status_code == 202, fresh.text
    assert fresh.json['id'] != old.json['id']
    assert [row['id'] for row in history(product_client, replacement)] == [fresh.json['id']]


def test_worker_discards_report_if_registration_changes_during_inspection(
        product_client, registered_proxy, diagnostic_host, monkeypatch):
    response = queue(product_client, registered_proxy.server_id)
    assert response.status_code == 202
    inspect = diagnostic.diagnostics

    def inspect_then_replace(server, body, heartbeat=lambda: None):
        report = inspect(server, body, heartbeat)
        replace_registration(registered_proxy)
        return report

    monkeypatch.setattr(diagnostic, 'diagnostics', inspect_then_replace)
    assert diagnostic.execute(InstallationTasks.get_by_id(response.json['task_id'])) == 'failed'
    assert OperationalAssessment.get_by_id(response.json['id']).result == ''
    assert product_client.get(f'/insights/api/assessments/{response.json["id"]}').status_code == 404


def test_stale_row_object_cannot_decrypt_a_previous_registration_report(
        product_client, registered_proxy, diagnostic_host, monkeypatch):
    response = queue(product_client, registered_proxy.server_id)
    finish(response)
    stale = OperationalAssessment.get_by_id(response.json['id'])
    replace_registration(registered_proxy)

    def forbidden_decrypt(_value):
        pytest.fail('Previous-registration report was decrypted before binding was checked')

    monkeypatch.setattr(diagnostic, 'unseal', forbidden_decrypt)
    with pytest.raises(RoxywiResourceNotFound):
        diagnostic.public(stale)


def legacy_assessment(server, user_id, *, completed):
    # Intentionally omit the assessment registration field, as an upgrade does
    # for historical rows. Matching current IP/runtime is not proof of origin.
    row = OperationalAssessment.create(group_id=1, user_id=user_id,
        kind='proxy-diagnostics', subject=f'haproxy:{server.server_id}',
        result=serialize_operation_payload(dict(summary='Legacy synthetic report')) if completed else '')
    identity = diagnostic.identity(server, 'haproxy')
    identity.pop('registration_key', None)
    task = InstallationTasks.create(service_name='Legacy synthetic assessment', group_id=1,
        user_id=user_id, server_ids=[server.server_id], operation_type='proxy-assessment',
        status='completed' if completed else 'created', operation_payload=serialize_operation_payload(dict(
            assessment_id=row.id, kind='diagnostics',
            request=dict(service='haproxy', server_id=server.server_id, url='https://example.test/'),
            identity=identity)))
    row.task_id = task.id
    row.save()
    return row, task


def test_unbound_legacy_report_is_not_claimed_by_current_same_ip_registration(
        product_client, product, registered_proxy, diagnostic_host):
    row, _task = legacy_assessment(registered_proxy, product.admin.user_id, completed=True)
    encrypted = row.result
    assert history(product_client, registered_proxy) == []
    assert product_client.get(f'/insights/api/assessments/{row.id}').status_code == 404
    assert OperationalAssessment.get_by_id(row.id).result == encrypted


def test_unbound_legacy_queued_identity_cannot_be_upgraded_from_current_ip(
        product_client, product, registered_proxy, diagnostic_host):
    row, task = legacy_assessment(registered_proxy, product.admin.user_id, completed=False)
    assert diagnostic.execute(task) == 'failed'
    assert diagnostic_host.discoveries == [] and diagnostic_host.calls == []
    assert OperationalAssessment.get_by_id(row.id).result == ''


def test_registration_migration_removes_legacy_report_but_preserves_operation_history(
        product, registered_proxy, diagnostic_host):
    row, task = legacy_assessment(registered_proxy, product.admin.user_id, completed=False)
    migration = importlib.import_module('app.modules.db.migrations.20261030010000_proxy_registration_identity')
    migration.up()
    assert OperationalAssessment.get_or_none(OperationalAssessment.id == row.id) is None
    assert InstallationTasks.get_by_id(task.id).status == 'created'
    assert diagnostic.execute(task) == 'failed'
    assert diagnostic_host.discoveries == [] and diagnostic_host.calls == []
