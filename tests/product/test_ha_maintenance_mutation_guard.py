"""Real mutation APIs share the durable reservation and worker lock."""
from contextlib import contextmanager
import json

import pytest

from tests.product.test_ha_maintenance import (
    readiness_cluster, maintenance_cluster, keepalived_maintenance,
    ka_create, ka_step, approve,
    create as pm_create, step as pm_step,
)
from app.modules.db.db_model import HaCluster, HaClusterRouter, HaClusterSlave, HaClusterVip, HaMaintenancePlan, InstallationTasks, PacemakerCluster, Server
from app.modules.roxywi.class_models import HAClusterRequest
from app.modules.roxywi.exception import RoxywiConflictError
from app.modules.service import ha_cluster, ha_maintenance as maintenance


def cluster_body(name='Updated VRRP cluster'):
    return dict(name=name, description='Updated fixture', syn_flood=False,
                services={}, reconfigure=False)


def vip_body():
    return dict(vip='192.0.2.101', virt_server=False,
                servers=[dict(id=11, eth='eth0', master=True), dict(id=33, eth='eth0', master=False)])


def secondary_vip(state):
    router = HaClusterRouter.create(cluster_id=state.cluster.id, default=0)
    return HaClusterVip.create(cluster_id=state.cluster.id, router_id=router.id, vip='192.0.2.101')


@pytest.mark.parametrize('status,task_status', [
    ('ready', None), ('draining', None), ('unknown', None), ('resuming', None),
    ('return-reviewed', None), ('reviewed', 'queued'), ('reviewed', 'running'),
])
def test_real_cluster_and_vip_mutations_refuse_all_reservations(
        product_client, keepalived_maintenance, status, task_status):
    state = keepalived_maintenance
    vip = secondary_vip(state)
    row = ka_create(product_client, state)
    row.status = status
    if task_status:
        task = InstallationTasks.create(service_name='HA maintenance', group_id=1, status=task_status)
        row.active_task_id = task.id
    row.save()
    operations = [
        ('put', f'/api/ha/cluster/{state.cluster.id}', cluster_body()),
        ('delete', f'/api/ha/cluster/{state.cluster.id}', None),
        ('post', f'/api/ha/cluster/{state.cluster.id}/vip', vip_body()),
        ('put', f'/api/ha/cluster/{state.cluster.id}/vip/{vip.id}', vip_body()),
        ('delete', f'/api/ha/cluster/{state.cluster.id}/vip/{vip.id}', None),
    ]
    for method, path, body in operations:
        response = getattr(product_client, method)(path, json=body)
        assert response.status_code == 409, (method, path, response.text)
        assert 'maintenance' in response.text
    assert HaCluster.get_by_id(state.cluster.id).name == 'product-vrrp'
    assert HaClusterVip.get_by_id(vip.id).vip == '192.0.2.101'
    assert HaClusterSlave.select().where(HaClusterSlave.cluster_id == state.cluster.id).count() == 2
    # Reading the actual API remains available while a reservation is held.
    assert product_client.get(f'/api/ha/cluster/{state.cluster.id}/vips').status_code == 200


def test_actual_delete_after_verified_drain_is_blocked_until_approved_return(
        product_client, keepalived_maintenance, maintenance_cluster, app):
    state = keepalived_maintenance
    row = ka_step(product_client, ka_create(product_client, state), 'review')
    approve(app, row, maintenance_cluster.reviewer)
    row = ka_step(product_client, row, 'drain')
    assert row.status == 'ready'
    response = product_client.delete(f'/api/ha/cluster/{state.cluster.id}')
    assert response.status_code == 409, response.text
    assert HaCluster.get_by_id(state.cluster.id)
    assert product_client.put(f'/api/ha/cluster/{state.cluster.id}', json=cluster_body()).status_code == 409
    row = ka_step(product_client, row, 'review-return')
    approve(app, row, maintenance_cluster.reviewer)
    row = ka_step(product_client, row, 'resume')
    assert row.status == 'completed'
    response = product_client.put(f'/api/ha/cluster/{state.cluster.id}', json=cluster_body())
    assert response.status_code == 201, response.text
    assert 'Updated VRRP cluster' in HaCluster.get_by_id(state.cluster.id).name
    response = product_client.delete(f'/api/ha/cluster/{state.cluster.id}')
    assert response.status_code == 204, response.text
    assert not HaCluster.select().where(HaCluster.id == state.cluster.id).exists()


def test_direct_service_cannot_bypass_reservation(product_client, keepalived_maintenance):
    row = ka_create(product_client, keepalived_maintenance)
    row.status = 'unknown'; row.save()
    with pytest.raises(RoxywiConflictError):
        ha_cluster.update_cluster(HAClusterRequest(**cluster_body()), row.cluster_id, row.group_id)
    with pytest.raises(RoxywiConflictError):
        ha_cluster.delete_cluster(row.cluster_id)


def test_reservation_is_rechecked_inside_the_worker_lock(product_client, keepalived_maintenance, monkeypatch):
    row = ka_create(product_client, keepalived_maintenance)
    acquired = []
    @contextmanager
    def acquire(path, **kwargs):
        acquired.append(path)
        # Model the maintenance enqueue winning the race before this writer
        # obtains the shared lock. An earlier request-level check saw idle.
        HaMaintenancePlan.update(status='ready').where(HaMaintenancePlan.id == row.id).execute()
        yield
    monkeypatch.setattr('app.modules.service.ha_mutation.file_lock', acquire)
    with pytest.raises(RoxywiConflictError):
        ha_cluster.delete_cluster(row.cluster_id)
    assert acquired == [maintenance.path_lock(row)]
    assert HaCluster.get_by_id(row.cluster_id)


def test_other_group_reservation_cannot_be_bypassed_by_global_admin(product_client, keepalived_maintenance):
    row = ka_create(product_client, keepalived_maintenance)
    HaCluster.update(group_id=2).where(HaCluster.id == row.cluster_id).execute()
    row.group_id = 2; row.status = 'ready'; row.save()
    response = product_client.delete(f'/api/ha/cluster/{row.cluster_id}')
    assert response.status_code == 409, response.text
    assert HaCluster.get_by_id(row.cluster_id)


def test_reconfigure_cannot_enqueue_installation_while_reserved(product_client, keepalived_maintenance, monkeypatch):
    row = ka_create(product_client, keepalived_maintenance)
    row.status = 'ready'; row.save()
    calls = []
    monkeypatch.setattr('app.views.ha.views.service_mod.install_service', lambda *args, **kwargs: calls.append(args))
    body = dict(cluster_body(), reconfigure=True)
    response = product_client.put(f'/api/ha/cluster/{row.cluster_id}', json=body)
    assert response.status_code == 409, response.text
    assert calls == []


def test_reserved_member_cannot_be_deleted_or_reidentified(product_client, keepalived_maintenance):
    from app.modules.db import server as server_sql
    from app.modules.server import server as servers
    from app.modules.db.db_model import Server
    row = ka_create(product_client, keepalived_maintenance)
    row.status = 'ready'; row.save()
    with pytest.raises(RoxywiConflictError):
        server_sql.update_server('Changed host', '192.0.2.99', 1, 0, 1, 0, 11, 11, 22, 'Changed', 0, 0)
    with pytest.raises(RoxywiConflictError):
        server_sql.delete_server(11)
    with pytest.raises(RoxywiConflictError):
        servers.delete_server(11)
    assert Server.get_by_id(11).ip == '192.0.2.11'


def test_reserved_member_blocks_config_save_install_and_service_actions(
        product_client, keepalived_maintenance, monkeypatch):
    from app.modules.config import config
    from app.modules.service import action, installation
    row = ka_create(product_client, keepalived_maintenance)
    row.status = 'unknown'; row.save()
    commands = []
    monkeypatch.setattr('app.modules.server.server.ssh_command', lambda *a, **kw: commands.append(a))
    with pytest.raises(RoxywiConflictError):
        config.upload_and_restart('192.0.2.11', '/nonexistent/candidate', 'save', 'keepalived')
    with pytest.raises(RoxywiConflictError):
        action.service_action('192.0.2.11', 'start', 'keepalived')
    body = HAClusterRequest(**dict(cluster_body(), servers=vip_body()['servers']))
    with pytest.raises(RoxywiConflictError):
        installation.install_service('keepalived', body, row.cluster_id)
    # An install queued before drain must recheck when the worker reaches Ansible.
    task = InstallationTasks.create(service_name='Keepalived', group_id=1)
    installation.run_installations({}, ['192.0.2.11'], 'keepalived', task.id)
    assert InstallationTasks.get_by_id(task.id).status == 'failed'
    assert 'maintenance' in InstallationTasks.get_by_id(task.id).error
    assert commands == []


def test_locked_members_cannot_be_imported_into_another_cluster(product_client, keepalived_maintenance):
    row = ka_create(product_client, keepalived_maintenance)
    row.status = 'ready'; row.save()
    response = product_client.post('/api/ha/cluster', json=dict(cluster_body('Imported cluster'), servers=vip_body()['servers']))
    assert response.status_code == 409, response.text
    assert HaCluster.select().count() == 1


def test_reserved_member_service_identity_and_auto_restart_cannot_change(
        product_client, keepalived_maintenance):
    from app.modules.db import service as service_sql
    row = ka_create(product_client, keepalived_maintenance)
    row.status = 'ready'; row.save()
    with pytest.raises(RoxywiConflictError):
        service_sql.insert_or_update_service_setting(11, 'keepalived', 'container_name', 'other-instance')
    with pytest.raises(RoxywiConflictError):
        service_sql.update_hapwi_server(11, 1, 0, 1, 'keepalived')
    response = product_client.post('/service/settings/keepalived', data=dict(
        serverSettingsSave='11', serverSettingsDockerized='1', serverSettingsRestart='1',
        container_engine='docker', container_owner='root', container_name='other-instance'))
    assert response.status_code == 409, response.text
    assert service_sql.select_service_setting(11, 'keepalived', 'container_name') == '0'


def test_non_global_admin_cannot_probe_or_mutate_other_groups_reservation(
        product_client, keepalived_maintenance, product):
    from app.modules.db.db_model import User, UserGroups
    row = ka_create(product_client, keepalived_maintenance)
    HaCluster.update(group_id=2).where(HaCluster.id == row.cluster_id).execute()
    row.group_id = 2; row.status = 'ready'; row.save()
    User.update(role_id='2').where(User.user_id == product.admin.user_id).execute()
    UserGroups.update(user_role_id=2).where(UserGroups.user_id == product.admin.user_id).execute()
    response = product_client.delete(f'/api/ha/cluster/{row.cluster_id}')
    assert response.status_code == 404, response.text
    assert 'maintenance' not in response.text
    assert HaCluster.get_by_id(row.cluster_id)


def test_nested_mutation_refuses_lock_order_inversion_before_waiting(
        product_client, keepalived_maintenance, monkeypatch):
    from app.modules.service import ha_mutation
    lower = keepalived_maintenance.cluster
    higher = HaCluster.create(name='Higher ID', group_id=1, syn_flood=0, description='Fixture')
    assert higher.id > lower.id
    with ha_mutation.mutation(higher.id):
        @contextmanager
        def unexpected_lock(path):
            pytest.fail('Nested mutation tried to wait for a lower cluster lock')
            yield
        monkeypatch.setattr(ha_mutation, 'file_lock', unexpected_lock)
        with pytest.raises(RoxywiConflictError, match='retry'):
            with ha_mutation.mutation(lower.id):
                pytest.fail('Out-of-order mutation was permitted')


def test_copied_context_in_another_thread_acquires_its_own_lock(
        product_client, keepalived_maintenance):
    from contextvars import copy_context
    from threading import Thread
    from app.modules.service import ha_mutation
    ident = keepalived_maintenance.cluster.id
    entered, errors = [], []
    def worker():
        try:
            with ha_mutation.mutation(ident):
                entered.append(True)
        except RoxywiConflictError as error:
            errors.append(error)
        finally:
            HaCluster._meta.database.close()
    with ha_mutation.mutation(ident):
        context = copy_context()
        thread = Thread(target=lambda: context.run(worker), daemon=True)
        thread.start(); thread.join(timeout=2)
        assert not thread.is_alive()
        assert not entered and len(errors) == 1
    # Reusing the saved context after release must obtain a fresh real lease.
    thread = Thread(target=lambda: context.run(worker), daemon=True)
    thread.start(); thread.join(timeout=2)
    assert not thread.is_alive() and entered == [True]
    assert len(errors) == 1



def member_body(server_id=11, **changes):
    server = Server.get_by_id(server_id)
    body = dict(hostname=server.hostname, ip=server.ip, cred_id=server.cred_id,
                group_id=int(server.group_id), enabled=True, type_ip=False, port=server.port)
    return dict(body, **changes)


def test_pacemaker_disable_after_drain_is_rejected_and_reviewed_return_remains_usable(
        product_client, maintenance_cluster, app):
    row = pm_step(product_client, pm_create(product_client, maintenance_cluster), 'review')
    approve(app, row, maintenance_cluster.reviewer)
    row = pm_step(product_client, row, 'drain')
    assert row.status == 'ready'
    response = product_client.put('/server/11', json=member_body(enabled=False))
    assert response.status_code == 409, response.text
    assert Server.get_by_id(11).enabled
    row = pm_step(product_client, row, 'review-return')
    approve(app, row, maintenance_cluster.reviewer)
    row = pm_step(product_client, row, 'resume')
    assert row.status == 'completed'
    assert 'node_maintenance' not in json.loads(
        PacemakerCluster.get_by_id(row.cluster_id).corosync_settings)
    response = product_client.put('/server/11', json=member_body(description='After approved return'))
    assert response.status_code == 201, response.text
    assert 'After approved return' in Server.get_by_id(11).description


@pytest.mark.parametrize('server_id', [11, 33])
@pytest.mark.parametrize('changes', [dict(enabled=False), dict(hostname='Replaced member'),
    dict(ip='192.0.2.91'), dict(port=2222), dict(cred_id=22), dict(type_ip=True), dict(group_id=2)])
def test_pacemaker_reserved_member_identity_updates_are_blocked_at_authenticated_api(
        product_client, maintenance_cluster, server_id, changes):
    row = pm_create(product_client, maintenance_cluster)
    row.status = 'ready'; row.save()
    before = member_body(server_id)
    response = product_client.put(f'/server/{server_id}', json=member_body(server_id, **changes))
    assert response.status_code == 409, response.text
    assert member_body(server_id) == before


@pytest.mark.parametrize('server_id', [11, 33])
def test_pacemaker_reserved_member_deletion_is_blocked_before_any_cleanup(
        product_client, maintenance_cluster, server_id, monkeypatch):
    row = pm_create(product_client, maintenance_cluster)
    row.status = 'ready'; row.save()
    calls = []
    monkeypatch.setattr('app.modules.db.service_command.stop_checker_assignments_for_server',
                        lambda *_: calls.append('cleanup'))
    response = product_client.delete(f'/server/{server_id}')
    assert response.status_code == 409, response.text
    assert Server.get_by_id(server_id) and calls == []


@pytest.mark.parametrize('status,queued', [('draining',False), ('ready',False), ('unknown',False),
    ('resuming',False), ('return-reviewed',False), ('reviewed',True)])
def test_pacemaker_direct_server_writes_obey_reservation_states(
        product_client, maintenance_cluster, status, queued):
    from app.modules.db import server as server_sql
    row = pm_create(product_client, maintenance_cluster)
    row.status = status
    if queued:
        task = InstallationTasks.create(service_name='HA maintenance', group_id=1, status='queued')
        row.active_task_id = task.id
    row.save()
    with pytest.raises(RoxywiConflictError):
        server_sql.update_server('Changed', '192.0.2.99', 1, 0, 0, 0, 11, 11, 22, '', 0, 0)
    with pytest.raises(RoxywiConflictError):
        server_sql.delete_server(11)
    assert Server.get_by_id(11).enabled and Server.get_by_id(11).ip == '192.0.2.11'


def test_pacemaker_member_write_cannot_bypass_an_existing_maintenance_lock(
        product_client, maintenance_cluster):
    from app.modules.pacemaker import service
    with service.locked(maintenance_cluster.cluster):
        response = product_client.put('/server/11', json=member_body(enabled=False))
    assert response.status_code == 409, response.text
    assert Server.get_by_id(11).enabled


def test_pacemaker_member_writer_holds_the_lock_against_maintenance_enqueue(
        product_client, maintenance_cluster):
    from app.modules.service import ha_mutation
    row = pm_create(product_client, maintenance_cluster)
    with ha_mutation.mutation(server_ids=[11]):
        assert PacemakerCluster.get_by_id(row.cluster_id).lock_token
        response = product_client.post(f'/ha/api/maintenance/{row.id}/review', json={})
        assert response.status_code == 409, response.text
        assert HaMaintenancePlan.get_by_id(row.id).active_task_id is None
    assert PacemakerCluster.get_by_id(row.cluster_id).lock_token is None


def test_pacemaker_reservation_is_rechecked_after_acquiring_the_real_lock(
        product_client, maintenance_cluster, monkeypatch):
    from app.modules.pacemaker import service
    row = pm_create(product_client, maintenance_cluster)
    original = service.locked
    @contextmanager
    def acquire(cluster, **kwargs):
        with original(cluster, **kwargs) as token:
            HaMaintenancePlan.update(status='ready').where(HaMaintenancePlan.id == row.id).execute()
            yield token
    monkeypatch.setattr(service, 'locked', acquire)
    response = product_client.put('/server/11', json=member_body(enabled=False))
    assert response.status_code == 409, response.text
    assert Server.get_by_id(11).enabled
    assert PacemakerCluster.get_by_id(row.cluster_id).lock_token is None


def test_pacemaker_nested_server_guard_keeps_the_original_lock(
        product_client, maintenance_cluster):
    from app.modules.db import server as server_sql
    from app.modules.service import ha_mutation
    with ha_mutation.mutation(server_ids=[11]):
        token = PacemakerCluster.get_by_id(maintenance_cluster.cluster.id).lock_token
        server_sql.update_server('Updated', '192.0.2.11', 1, 0, 1, 0, 11, 11, 22, '', 0, 0)
        assert PacemakerCluster.get_by_id(maintenance_cluster.cluster.id).lock_token == token
    assert Server.get_by_id(11).hostname == 'Updated'
    assert PacemakerCluster.get_by_id(maintenance_cluster.cluster.id).lock_token is None


def test_copied_pacemaker_lock_context_cannot_authorize_another_thread(
        product_client, maintenance_cluster):
    from contextvars import copy_context
    from threading import Thread
    from app.modules.service import ha_mutation
    errors, writes = [], []
    def worker():
        try:
            with ha_mutation.mutation(server_ids=[11]):
                writes.append('unauthorized competing write')
        except RoxywiConflictError as error:
            errors.append(error)
        finally:
            PacemakerCluster._meta.database.close()
    with ha_mutation.mutation(server_ids=[11]):
        context = copy_context()
        thread = Thread(target=lambda: context.run(worker), daemon=True)
        thread.start(); thread.join(timeout=2)
        assert not thread.is_alive()
        assert not writes and len(errors) == 1
        assert PacemakerCluster.get_by_id(maintenance_cluster.cluster.id).lock_token
    assert PacemakerCluster.get_by_id(maintenance_cluster.cluster.id).lock_token is None


def test_pacemaker_member_ids_are_not_lost_when_passed_as_an_iterator(
        product_client, maintenance_cluster):
    from app.modules.service import ha_mutation
    row = pm_create(product_client, maintenance_cluster)
    row.status = 'ready'; row.save()
    with pytest.raises(RoxywiConflictError):
        with ha_mutation.mutation(server_ids=iter([11])):
            pytest.fail('The iterator bypassed Pacemaker membership discovery')


def test_closed_same_thread_context_cannot_reuse_an_expired_pacemaker_lease(
        product_client, maintenance_cluster):
    from contextvars import copy_context
    from app.modules.service import ha_mutation
    from app.modules.pacemaker import service
    with ha_mutation.mutation(server_ids=[11]):
        saved = copy_context()
    with service.locked(maintenance_cluster.cluster):
        response = saved.run(lambda: product_client.put('/server/11', json=member_body(enabled=False)))
        assert response.status_code == 409, response.text
        assert Server.get_by_id(11).enabled


def test_concurrent_membership_commit_cannot_hide_a_new_reserved_member(
        product_client, maintenance_cluster):
    from threading import Thread
    from app.modules.service.ha_topology import topology_lock
    Server.create(server_id=44, hostname='New member', ip='192.0.2.44', group_id=1, cred_id=11)
    row = pm_create(product_client, maintenance_cluster)
    responses = []
    def disable():
        try:
            responses.append(product_client.put('/server/44', json=member_body(44, enabled=False)).status_code)
        finally:
            Server._meta.database.close()
    # The topology writer and identity writer run on separate real DB connections
    # and contend for the same nonblocking process lock before membership reads.
    with topology_lock():
        thread = Thread(target=disable, daemon=True)
        thread.start(); thread.join(timeout=2)
        assert not thread.is_alive() and responses == [409]
        members = json.loads(maintenance_cluster.cluster.servers)
        members.append(dict(server_id=44, name='three', address='192.0.2.44', nodeid=3))
        PacemakerCluster.update(servers=json.dumps(members)).where(PacemakerCluster.id == row.cluster_id).execute()
        HaMaintenancePlan.update(status='ready').where(HaMaintenancePlan.id == row.id).execute()
    response = product_client.put('/server/44', json=member_body(44, enabled=False))
    assert response.status_code == 409, response.text
    assert Server.get_by_id(44).enabled


def test_real_registration_cannot_race_a_server_identity_writer(product_client, maintenance_cluster):
    from threading import Thread
    from app.modules.service import ha_mutation
    from app.modules.pacemaker import service
    from app.modules.pacemaker.schemas import ClusterCreate
    from app.modules.roxywi.exception import RoxywiInputError
    for ident in [44, 55]:
        Server.create(server_id=ident, hostname=f'New node {ident}', ip=f'192.0.2.{ident}', group_id=1, cred_id=11)
    body = ClusterCreate(name='new-registration', members=[
        dict(server_id=ident, name=f'new{ident}', address=f'192.0.2.{ident}', nodeid=i)
        for i, ident in enumerate([44, 55], 1)])
    errors, created = [], []
    def register():
        try:
            created.append(service.register(body, 1))
        except RoxywiConflictError as error:
            errors.append(error)
        finally:
            PacemakerCluster._meta.database.close()
    with ha_mutation.mutation(server_ids=[44]):
        thread = Thread(target=register, daemon=True)
        thread.start(); thread.join(timeout=2)
        assert not thread.is_alive() and len(errors) == 1 and not created
        Server.update(enabled=0).where(Server.server_id == 44).execute()
    with pytest.raises(RoxywiInputError, match='enabled physical'):
        service.register(body, 1)
    assert not PacemakerCluster.select().where(PacemakerCluster.name == body.name).exists()


@pytest.mark.parametrize("operation", ["server", "enqueue"])
def test_busy_keepalived_worker_does_not_hold_up_unrelated_topology_writes(
        product_client, keepalived_maintenance, operation):
    from threading import Thread
    from app.modules.common.file_lock import file_lock
    from app.modules.service.ha_topology import topology_lock
    row = ka_create(product_client, keepalived_maintenance)
    responses = []
    def mutate():
        try:
            response = (product_client.put('/server/11', json=member_body(enabled=False))
                        if operation == 'server' else product_client.post(f'/ha/api/maintenance/{row.id}/review', json={}))
            responses.append(response.status_code)
        finally:
            Server._meta.database.close()
    # Exercise the lock-contention boundary even before the worker's durable
    # active/ready state is available to the preflight read.
    thread = None
    try:
        with file_lock(maintenance.path_lock(row)):
            thread = Thread(target=mutate, daemon=True)
            thread.start(); thread.join(timeout=2)
            assert not thread.is_alive() and responses == [409]
            with topology_lock():
                assert Server.get_by_id(11).enabled
    finally:
        if thread is not None:
            thread.join(timeout=2)


def test_bootstrap_settings_save_preserves_the_live_cluster_token(
        product_client, maintenance_cluster, monkeypatch):
    from app.modules.pacemaker import bootstrap, install_log, service

    loaded = PacemakerCluster.get_by_id(maintenance_cluster.cluster.id)

    def run(remote, source, node, stage, record, **kwargs):
        if stage == 'Preflight':
            return node
        if stage == 'Packages and configuration':
            return json.dumps({'fence_pve_repaired': False})
        return ''

    monkeypatch.setattr(install_log, 'run', run)
    monkeypatch.setattr(service, 'wait_ready', lambda *_: None)
    events = []
    original = service.event

    def event(cluster, user_id, action, status):
        if action == 'bootstrap':
            token = PacemakerCluster.get_by_id(cluster.id).lock_token
            assert token, 'A settings-only save cleared the active lock token'
            events.append((status, token))
        return original(cluster, user_id, action, status)

    monkeypatch.setattr(service, 'event', event)
    bootstrap.provision(loaded, 1, syn_flood=True, fence_pve=True)

    assert [status for status, _token in events] == ['started', 'completed']
    assert events[0][1] == events[1][1]
    saved = PacemakerCluster.get_by_id(loaded.id)
    settings = json.loads(saved.corosync_settings)
    assert settings['syn_flood'] is True
    assert settings['fence_pve'] is True
    assert saved.lock_token is None
