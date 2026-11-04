"""Executor authorization uses the real assignment/server database."""
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest

from app.modules.db.db_model import Server, ServiceAssignment
from app.modules.db import service_command as command_sql
from app.modules.integrations import keepalived_probes as probes
from app.modules.integrations.keepalived_contract import KeepalivedProbeRequest, KeepalivedSnapshot
from app.modules.roxywi import common


@pytest.fixture
def assignment(product):
    Server.update(keepalived=1, keepalived_alert=1).where(Server.server_id == 11).execute()
    row = ServiceAssignment.create(assignment_id='keepalived:server-11', target_service='checker',
                                   service='keepalived', server_id=11, user_group=1, revision=2,
                                   desired_state='running', payload=json.dumps(dict(target=dict(
                                       server_id=11, service='keepalived', address=product.server.ip))))
    request = KeepalivedProbeRequest(request_id=uuid4(), assignment_id=row.assignment_id,
                                    revision=2, lease_epoch=3, group_id=1,
                                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=90))
    return row, request


def test_executor_returns_all_states_without_credentials(assignment, monkeypatch):
    monkeypatch.setattr(probes, 'collect', lambda server: KeepalivedSnapshot(service='UP', instances=[
        dict(name='one', state='MASTER'), dict(name='two', state='BACKUP')]))
    result = probes.execute_probe(assignment[1])
    assert len(result.snapshot.instances) == 2
    assert result.request_id == assignment[1].request_id
    assert result.lease_epoch == 3


@pytest.mark.parametrize('field,value', [('revision', 1), ('group_id', 2),
                                       ('assignment_id', 'keepalived:server-22')])
def test_wrong_assignment_scope_never_contacts_ssh(assignment, monkeypatch, field, value):
    monkeypatch.setattr(probes, 'collect', lambda server: pytest.fail('Untrusted SSH target'))
    result = probes.execute_probe(assignment[1].model_copy(update={field: value}))
    assert result.error == 'assignment_unavailable'


@pytest.mark.parametrize('changes', [dict(enabled=0), dict(keepalived_alert=0), dict(keepalived=0),
                                   dict(group_id='2'), dict(ip='192.0.2.99')])
def test_disabled_or_changed_server_never_contacts_ssh(assignment, monkeypatch, changes):
    Server.update(**changes).where(Server.server_id == 11).execute()
    monkeypatch.setattr(probes, 'collect', lambda server: pytest.fail('Disabled SSH target'))
    assert probes.execute_probe(assignment[1]).error == 'assignment_unavailable'


@pytest.mark.parametrize('seconds', [-1, 600])
def test_expired_or_unbounded_request_never_contacts_ssh(assignment, monkeypatch, seconds):
    monkeypatch.setattr(probes, 'collect', lambda server: pytest.fail('Expired SSH request'))
    request = assignment[1].model_copy(update={'expires_at': datetime.now(timezone.utc) + timedelta(seconds=seconds)})
    assert probes.execute_probe(request).error == 'expired'


def test_revision_change_during_probe_discards_result(assignment, monkeypatch):
    def collect(server):
        ServiceAssignment.update(revision=3).where(ServiceAssignment.assignment_id == assignment[0].assignment_id).execute()
        return KeepalivedSnapshot(service='UP', instances=[dict(name='one', state='MASTER')])
    monkeypatch.setattr(probes, 'collect', collect)
    assert probes.execute_probe(assignment[1]).error == 'assignment_unavailable'


def test_ssh_failure_is_not_down_and_does_not_leak_errors(assignment, monkeypatch):
    messages = []
    def collect(server):
        raise RuntimeError('password=DoNotLogThis')
    monkeypatch.setattr(probes, 'collect', collect)
    monkeypatch.setattr(probes.logger, 'warning', messages.append)
    result = probes.execute_probe(assignment[1])
    assert result.error == 'probe_failed' and result.snapshot is None
    assert 'DoNotLogThis' not in result.model_dump_json() + repr(messages)


@pytest.mark.parametrize('plan,active,allowed', [
    ('user', 1, True), ('company', 1, True), ('cloud', 1, True), ('support', 1, True),
    ('Trial', 1, False), ('free', 1, False), ('user', 0, False), ('support', 0, False),
    ('', 0, False),
])
def test_executor_requires_active_user_plan_or_higher(assignment, monkeypatch, plan, active, allowed):
    monkeypatch.setattr(common, 'return_user_subscription',
                        lambda: dict(user_status=active, user_plan=plan))
    calls = []
    def collect(server):
        calls.append(server.server_id)
        return KeepalivedSnapshot(service='UP', instances=[dict(name='one', state='BACKUP')])
    monkeypatch.setattr(probes, 'collect', collect)
    result = probes.execute_probe(assignment[1])
    assert calls == ([11] if allowed else [])
    assert (result.snapshot is not None) is allowed
    assert result.error == (None if allowed else 'assignment_unavailable')


def test_subscription_expiry_during_probe_discards_result(assignment, monkeypatch):
    subscription = dict(user_status=1, user_plan='user')
    monkeypatch.setattr(common, 'return_user_subscription', lambda: subscription)
    def collect(server):
        subscription['user_status'] = 0
        return KeepalivedSnapshot(service='UP', instances=[dict(name='one', state='BACKUP')])
    monkeypatch.setattr(probes, 'collect', collect)
    result = probes.execute_probe(assignment[1])
    assert result.snapshot is None and result.error == 'assignment_unavailable'


@pytest.mark.parametrize('plan,active,allowed', [
    ('user', 1, True), ('company', 1, True), ('cloud', 1, True), ('support', 1, True),
    ('Trial', 1, False), ('user', 0, False),
])
def test_keepalived_switch_checks_plan_and_always_allows_stop(product, product_client, monkeypatch, plan, active, allowed):
    Server.update(keepalived=1, keepalived_alert=0).where(Server.server_id == 11).execute()
    monkeypatch.setattr(common, 'return_user_subscription',
                        lambda: dict(user_status=active, user_plan=plan))
    data = dict(server_id=11, name='Product server', active='0', alert_en='1', metrics='0')
    response = product_client.post('/service/keepalived/tools/update', data=data)
    assert response.status_code == (200 if allowed else 403)
    assert Server.get_by_id(11).keepalived_alert == int(allowed)
    row = ServiceAssignment.get_or_none(ServiceAssignment.assignment_id == 'keepalived:server-11')
    if allowed:
        assert row.desired_state == 'running'
    else:
        assert row is None
    response = product_client.post('/service/keepalived/tools/update', data=dict(data, alert_en='0'))
    assert response.status_code == 200
    assert Server.get_by_id(11).keepalived_alert == 0
    assert ServiceAssignment.get_by_id('keepalived:server-11').desired_state == 'stopped'


def test_reconciliation_stops_keepalived_and_cannot_reenable_after_expiry(assignment, monkeypatch):
    subscription = dict(user_status=1, user_plan='user')
    monkeypatch.setattr(common, 'return_user_subscription', lambda: subscription)
    command_sql.queue_checker_assignment(11, 'keepalived', True)
    assert ServiceAssignment.get_by_id(assignment[0].assignment_id).desired_state == 'running'
    subscription['user_status'] = 0
    assert command_sql.reconcile_checker_assignments([Server.get_by_id(11)]) == 1
    assert ServiceAssignment.get_by_id(assignment[0].assignment_id).desired_state == 'stopped'
    command_sql.queue_checker_assignment(11, 'keepalived', True)
    assert ServiceAssignment.get_by_id(assignment[0].assignment_id).desired_state == 'stopped'
