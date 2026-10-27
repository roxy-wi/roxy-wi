"""Durable operations through the existing Operations queue."""
from uuid import uuid4

from app.modules.db.db_model import InstallationTasks, User, PacemakerCluster
from app.modules.db import user as user_sql
from app.modules.operations.queue import serialize_operation_payload, deserialize_operation_payload
from app.modules.common.time import utc_now
from app.modules.pacemaker import service
from app.modules.pacemaker.schemas import Action
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiPublicError


def enqueue(cluster, user_id, action, data=None):
    with service.locked(cluster), PacemakerCluster._meta.database.atomic():
        cluster = service.get_cluster(cluster.id, cluster.group_id)
        import json
        if json.loads(cluster.corosync_settings).get('witness_pending') and action!='monitor':
            raise RoxywiConflictError('Recover the unfinished witness trust change before changing the cluster')
        if json.loads(cluster.corosync_settings).get('transport_pending') and action not in ('transport-recover','monitor'):
            raise RoxywiConflictError('Recover the unfinished transport migration before changing the cluster')
        if cluster.active_task_id:
            active = InstallationTasks.get_or_none(InstallationTasks.id == cluster.active_task_id)
            if active and active.status not in ('failed', 'completed'):
                raise RoxywiConflictError('A cluster operation is already queued or running')
        service.members(cluster)
        identities = {str(member.server_id): {'ip': server.ip, 'port': server.port, 'cred_id': server.cred_id}
                      for member, server in service.members(cluster)}
        task = InstallationTasks.create(
            service_name=f'Pacemaker {cluster.name}: {action}',
            group_id=cluster.group_id, user_id=user_id, server_ids=[m.server_id for m, _s in service.members(cluster)],
            operation_id=str(uuid4()), operation_type='pacemaker', status='created', updated_at=utc_now(),
            operation_payload=serialize_operation_payload({'cluster_id': cluster.id, 'action': action,
                'data': data or {}, 'servers': identities}),
        )
        PacemakerCluster.update(active_task_id=task.id).where(PacemakerCluster.id == cluster.id).execute()
        service.event(cluster, user_id, action, 'queued')
        return task


def execute(task):
    payload = deserialize_operation_payload(task.operation_payload)
    if payload.get('action') in ('witness-install','witness-migrate','witness-recover','witness-lifecycle','witness-lifecycle-recover','witness-trust','witness-trust-recover'):
        return execute_witness(task, payload)
    try:
        cluster = service.get_cluster(payload['cluster_id'], task.group_id_id)
        actor = User.get_or_none(User.user_id == task.user_id_id)
        monitoring = payload['action'] == 'monitor' and cluster.monitor_enabled
        if not monitoring and (not actor or not actor.enabled or '5' not in user_sql.select_user_services(actor.user_id).split()):
            raise ValueError('Cluster permissions were revoked')
        if not monitoring and int(user_sql.get_user_role_in_group(actor.user_id, task.group_id_id)) > 3:
            raise ValueError('Operator permissions were revoked')
        identities = {str(member.server_id): {'ip': server.ip, 'port': server.port, 'cred_id': server.cred_id}
                      for member, server in service.members(cluster)}
        if payload.get('servers') != identities:
            raise ValueError('Server identity changed after the operation was queued')
        if payload.get('started'):
            if payload['action'] in ('validate', 'apply'):
                change = service.change_for(cluster, payload['data']['change_id'])
                change.status = 'unknown' if payload['action'] == 'apply' else 'failed'
                change.save()
            raise ValueError('Interrupted operation requires manual state inspection; it cannot be replayed')
        payload['started'] = True
        InstallationTasks.update(operation_payload=serialize_operation_payload(payload)).where(InstallationTasks.id == task.id).execute()
        action, data = payload['action'], payload['data']
        if action == 'monitor':
            from app.modules.pacemaker.monitor import check
            check(cluster)
        elif action == 'bootstrap':
            from app.modules.pacemaker.bootstrap import provision
            provision(cluster, actor.user_id, syn_flood=data.get('syn_flood', False), fence_pve=data.get('fence_pve', False))
        elif action in ('validate', 'apply'):
            change = service.change_for(cluster, data['change_id'])
            if change.kind == 'corosync':
                from app.modules.pacemaker.corosync import execute as execute_corosync
                execute_corosync(cluster, change, actor.user_id, apply=action == 'apply')
            else:
                service.validate_or_apply(cluster, data['change_id'], actor.user_id, apply=action == 'apply')
        elif action == 'operate':
            service.operate(cluster, actor.user_id, Action.model_validate(data))
        elif action in ('transport-quiesce','transport-resume','transport-recover','transport-migrate'):
            from app.modules.pacemaker import transport
            if data.get('confirm')!=cluster.name:raise ValueError('Cluster confirmation changed')
            if action=='transport-migrate':transport.execute(cluster,actor.user_id,data['token'],data['plan_digest'])
            else:getattr(transport,action.removeprefix('transport-'))(cluster,actor.user_id)
        elif action == 'autostart-policy':
            from app.modules.pacemaker.autostart import apply
            apply(cluster,actor.user_id,data)
        elif action == 'agent-install':
            from app.modules.pacemaker.agents import install
            install(cluster, actor.user_id, data)
        elif action == 'agent-repositories':
            from app.modules.pacemaker.agents import refresh_repositories
            refresh_repositories(cluster, actor.user_id)
        else:
            raise ValueError('Unsupported cluster operation')
        state, error = 'completed', None
    except RoxywiPublicError as exc:
        state, error = 'failed', exc.public_message
    except Exception:
        # Do not store raw SSH exceptions, candidate XML or credentials in task errors.
        state, error = 'failed', 'Cluster operation failed; inspect cluster state and node journal before retrying'
    InstallationTasks.update(status=state, error=error, finish_date=utc_now(), updated_at=utc_now()).where(InstallationTasks.id == task.id).execute()
    PacemakerCluster.update(active_task_id=None).where(
        (PacemakerCluster.id == payload['cluster_id']) & (PacemakerCluster.active_task_id == task.id)).execute()
    return state


def enqueue_witness(server_id, group_id, user_id, *, docker=False, action="witness-install", data=None):
    from peewee import SqliteDatabase
    from app.modules.db.db_model import Server
    from app.modules.pacemaker.qdevice import witness_server
    database = InstallationTasks._meta.database
    witness_ids=sorted({server_id,*([int(data['target_id'])] if action=='witness-trust' and data else [])})
    for ident in witness_ids:witness_server(ident,group_id)
    with database.atomic('IMMEDIATE') if isinstance(database, SqliteDatabase) else database.atomic():
        if not isinstance(database, SqliteDatabase):
            list(Server.select().where(Server.server_id.in_(witness_ids)).order_by(Server.server_id).for_update())
        server = witness_server(server_id, group_id)
        for task in InstallationTasks.select().where(
            (InstallationTasks.group_id == group_id) & (InstallationTasks.operation_type == 'pacemaker') &
            (InstallationTasks.status.not_in(('completed', 'failed')))
        ):
            payload = deserialize_operation_payload(task.operation_payload)
            if action=='witness-trust' and data and data.get('target_id') in (payload.get('server_id'),payload.get('data',{}).get('target_id')):
                raise RoxywiConflictError('Target witness has a queued or running operation')
            if payload.get('action') in ('witness-install','witness-migrate','witness-recover','witness-lifecycle','witness-lifecycle-recover','witness-trust','witness-trust-recover') and server_id in (payload.get('server_id'),payload.get('data',{}).get('target_id')):
                raise RoxywiConflictError('Witness installation is already queued or running')
        return InstallationTasks.create(service_name=f'Corosync witness: {server.hostname}', group_id=group_id,
            user_id=user_id, server_ids=witness_ids, operation_id=str(uuid4()), operation_type='pacemaker',
            status='created', updated_at=utc_now(), operation_payload=serialize_operation_payload({
                'action': action, 'server_id': server_id, 'docker': docker, 'data': data or {},
                'identity': {'ip': server.ip, 'port': server.port, 'cred_id': server.cred_id},
            }))


def execute_witness(task, payload):
    from app.modules.pacemaker.qdevice import witness_server, install_witness
    try:
        actor = User.get_or_none(User.user_id == task.user_id_id)
        if not actor or not actor.enabled or '5' not in user_sql.select_user_services(actor.user_id).split():
            raise ValueError('Witness permissions were revoked')
        if int(user_sql.get_user_role_in_group(actor.user_id, task.group_id_id)) > 3:
            raise ValueError('Operator permissions were revoked')
        server = witness_server(payload['server_id'], task.group_id_id)
        if payload.get('identity') != {'ip': server.ip, 'port': server.port, 'cred_id': server.cred_id}:
            raise ValueError('Witness server identity changed after queuing')
        if payload.get('started'):
            raise ValueError('Interrupted witness installation requires inspection before retrying')
        payload['started'] = True
        InstallationTasks.update(operation_payload=serialize_operation_payload(payload)).where(InstallationTasks.id == task.id).execute()
        if payload.get('action','witness-install') == 'witness-migrate':
            from app.modules.pacemaker.witness_migration import migrate
            payload['result'] = migrate(server.server_id,task.group_id_id,payload['data']['plan_digest'],actor.user_id)
        elif payload.get('action') == 'witness-trust':
            from app.modules.pacemaker.witness_trust import execute
            data=payload['data']
            payload['result']=execute(server.server_id,data['target_id'],task.group_id_id,data['rotate_ca'],data['plan_digest'],actor.user_id)
        elif payload.get('action') == 'witness-trust-recover':
            from app.modules.pacemaker.witness_trust import recover
            payload['result']=recover(server.server_id,task.group_id_id,payload['data']['token'])
        elif payload.get('action') == 'witness-lifecycle':
            from app.modules.pacemaker.witness_lifecycle import execute
            payload['result']=execute(server.server_id,task.group_id_id,payload['data']['operation'],payload['data']['plan_digest'],actor.user_id)
        elif payload.get('action') == 'witness-lifecycle-recover':
            from app.modules.pacemaker.witness_lifecycle import recover
            payload['result']=recover(server.server_id,task.group_id_id,payload['data']['token'])
        elif payload.get('action') == 'witness-recover':
            from app.modules.pacemaker.witness_migration import recover_migration
            payload['result'] = recover_migration(server.server_id,task.group_id_id,payload['data']['token'])
        elif payload.get('docker', False):
            install_witness(server.server_id, task.group_id_id, docker=True)
        else:
            install_witness(server.server_id, task.group_id_id)
        InstallationTasks.update(operation_payload=serialize_operation_payload(payload)).where(InstallationTasks.id==task.id).execute()
        state, error = 'completed', None
    except RoxywiPublicError as exc:
        state, error = 'failed', exc.public_message
    except Exception:
        state, error = 'failed', 'Witness operation failed; inspect server permissions, the qnetd journal or Docker container logs before retrying'
    InstallationTasks.update(status=state, error=error, finish_date=utc_now(), updated_at=utc_now()).where(InstallationTasks.id == task.id).execute()
    return state
