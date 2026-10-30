import json
import secrets
from contextlib import contextmanager
from datetime import timedelta

from cryptography.fernet import Fernet
from peewee import IntegrityError, SqliteDatabase

from app.modules.db.db_model import PacemakerCluster, PacemakerChange, PacemakerEvent, Server
from app.modules.db.server import get_server_with_group, select_servers_with_group
from app.modules.pacemaker.remote import Remote, RemoteError
from app.modules.pacemaker.schemas import ClusterCreate, Member
from app.modules.pacemaker.transaction import TRANSACTION
from app.modules.pacemaker.xml import configuration, digest, summary
from app.modules.roxywi.exception import RoxywiInputError, RoxywiConflictError, RoxywiResourceNotFound
from app.modules.common.time import utc_now
from app.modules.service.ha_topology import topology_guarded


def _cipher():
    from app.modules.server.ssh import _get_fernet_key
    return Fernet(_get_fernet_key().encode())


def encrypt(value):
    return _cipher().encrypt(value.encode()).decode()


def decrypt(value):
    return _cipher().decrypt(value.encode()).decode()


def get_cluster(cluster_id, group_id):
    try:
        return PacemakerCluster.get((PacemakerCluster.id == cluster_id) & (PacemakerCluster.group_id == group_id))
    except PacemakerCluster.DoesNotExist as exc:
        raise RoxywiResourceNotFound('Cluster not found in the active group') from exc


def members(cluster):
    """Validate the saved membership against one current, group-scoped read."""
    declared = [Member.model_validate(value) for value in json.loads(cluster.servers)]
    servers = {server.server_id: server for server in select_servers_with_group(cluster.group_id).where(
        Server.server_id.in_([member.server_id for member in declared]))}
    result = []
    for member in declared:
        server = servers.get(member.server_id)
        if server is None:
            raise RoxywiResourceNotFound('Cluster member not found in the active group')
        if not server.enabled or server.type_ip:
            raise RoxywiInputError('Cluster members must be enabled physical server entries')
        result.append((member, server))
    return result


def serialize(cluster):
    # Check current server ownership even for previously saved cluster records.
    checked = members(cluster)
    return {'id': cluster.id, 'name': cluster.name, 'description': cluster.description,
            'corosync_settings': json.loads(cluster.corosync_settings),
            'monitor_enabled': cluster.monitor_enabled, 'health': cluster.health,
            'members': [member.model_dump() for member, _server in checked]}


@topology_guarded
def register(body: ClusterCreate, group_id):
    database = PacemakerCluster._meta.database
    with database.atomic('IMMEDIATE') if isinstance(database, SqliteDatabase) else database.atomic():
        if not isinstance(database, SqliteDatabase):
            list(Server.select().where(Server.server_id.in_([m.server_id for m in body.members]))
                 .order_by(Server.server_id).for_update())
        registered = {item['server_id']
                      for cluster in PacemakerCluster.select(PacemakerCluster.servers).where(PacemakerCluster.group_id == group_id)
                      for item in json.loads(cluster.servers)}
        for member in body.members:
            server = get_server_with_group(member.server_id, group_id)
            if not server.enabled or server.type_ip:
                raise RoxywiInputError('Select enabled physical servers')
            if member.server_id in registered:
                raise RoxywiInputError('A server is already registered in another Pacemaker cluster')
        try:
            return PacemakerCluster.create(name=body.name, description=body.description, group_id=group_id,
                                           servers=json.dumps([member.model_dump() for member in body.members]))
        except IntegrityError as exc:
            raise RoxywiInputError('A cluster with this name already exists') from exc


@contextmanager
def locked(cluster, *, maintenance_id=None):
    token = secrets.token_hex(16)
    now = utc_now()
    updated = (PacemakerCluster.update(lock_token=token, lock_until=now + timedelta(minutes=10))
               .where((PacemakerCluster.id == cluster.id) &
                      ((PacemakerCluster.lock_token.is_null()) | (PacemakerCluster.lock_until < now))).execute())
    if not updated:
        raise RoxywiConflictError('Another cluster operation is running')
    try:
        current=get_cluster(cluster.id,cluster.group_id)
        pending=json.loads(current.corosync_settings).get('node_maintenance')
        if pending is not None and pending!=maintenance_id:
            raise RoxywiConflictError('A node is handed over for maintenance; use its reviewed return workflow before changing the cluster')
        yield token
    finally:
        (PacemakerCluster.update(lock_token=None, lock_until=None)
         .where((PacemakerCluster.id == cluster.id) & (PacemakerCluster.lock_token == token)).execute())


def event(cluster, user_id, action, status):
    PacemakerEvent.create(cluster=cluster, user_id=user_id if user_id is not None else 0, action=action, status=status)


def renew_lock(cluster, token):
    if not isinstance(token, str) or not token:
        raise RoxywiConflictError('Cluster operation lock was lost; inspect state before retrying')
    until = utc_now() + timedelta(minutes=10)
    database = PacemakerCluster._meta.database
    with database.atomic():
        updated = PacemakerCluster.update(lock_until=until).where(
            (PacemakerCluster.id == cluster.id) & (PacemakerCluster.lock_token == token)).execute()
        if updated == 1:
            return
        if updated == 0:
            # MariaDB reports changed rows, so an identical second-precision
            # DATETIME renewal can report zero while this lease is still ours.
            current = PacemakerCluster.select().where(
                (PacemakerCluster.id == cluster.id) & (PacemakerCluster.lock_token == token) &
                (PacemakerCluster.lock_until >= until.replace(microsecond=0)))
            if not isinstance(database, SqliteDatabase):
                # A locking current read must not trust an older RR snapshot.
                current = current.for_update()
            if current.exists():
                return
        raise RoxywiConflictError('Cluster operation lock was lost; inspect state before retrying')


def connection(cluster):
    # Fail over only reads. A failed write must never be replayed on another node.
    for _member, server in members(cluster):
        remote = Remote(server)
        try:
            xml = remote.run(['cibadmin', '--query'])
            configuration(xml)
            cluster_name = remote.run(['corosync-cmapctl', 'totem.cluster_name']).strip().split(' = ', 1)[-1]
            if cluster_name != cluster.name:
                continue
            return remote, xml
        except Exception:
            continue
    raise RemoteError('No cluster node is reachable with a readable CIB')


def status(cluster):
    remote, _xml = connection(cluster)
    result = summary(remote.run(['crm_mon', '--one-shot', '--output-as=xml'], allowed=(0, 1, 2)))
    result['source'] = remote.server.hostname
    from app.modules.pacemaker.quorum import details
    try:
        result['quorum_details'] = details(remote.run(['env', 'LC_ALL=C', 'corosync-quorumtool', '-s'], allowed=(0, 2)))
    except (RemoteError, ValueError):
        result['quorum_details'] = {'configured': None, 'votes': None, 'two_node': None}
    return result


def wait_ready(cluster, *, seconds=60):
    import time
    deadline = time.monotonic() + seconds
    expected = {member.name for member, _s in members(cluster)}
    while time.monotonic() < deadline:
        try:
            state = status(cluster)
            online = {node['name'] for node in state['nodes'] if node['online'] == 'true'}
            if state['quorate'] and expected <= online:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RemoteError('Cluster did not become quorate with all registered nodes online')


def get_config(cluster):
    _remote, xml = connection(cluster)
    return {'xml': xml, 'digest': digest(xml)}


def draft(cluster, user_id, body):
    configuration(body.xml)
    with locked(cluster):
        _remote, current = connection(cluster)
        if digest(current) != body.base_digest:
            raise RoxywiConflictError('Configuration changed; load a fresh CIB')
        change = PacemakerChange.create(cluster=cluster, user_id=user_id, base_digest=body.base_digest,
                                         candidate=encrypt(body.xml), previous=encrypt(current))
        event(cluster, user_id, f'draft:{change.id}', 'saved')
        return change


def change_for(cluster, change_id):
    try:
        return PacemakerChange.get((PacemakerChange.cluster == cluster.id) & (PacemakerChange.id == change_id))
    except PacemakerChange.DoesNotExist as exc:
        raise RoxywiResourceNotFound('Change not found') from exc


def validate_or_apply(cluster, change_id, user_id, *, apply=False):
    with locked(cluster):
        change = change_for(cluster, change_id)
        if change.status in ('applying', 'applied', 'unknown'):
            raise RoxywiConflictError('This change was already attempted; inspect state and create a fresh draft')
        if apply and change.status != 'validated':
            raise RoxywiInputError('Validate and review the change before applying')
        remote, current = connection(cluster)
        if digest(current) != change.base_digest:
            raise RoxywiConflictError('Configuration changed since the draft was created')
        if apply and not status(cluster)['quorate']:
            raise RoxywiInputError('Cannot apply configuration without quorum')
        change.status = 'applying' if apply else 'validating'
        change.save()
        event(cluster, user_id, f'{"apply" if apply else "validate"}:{change.id}', 'started')
        try:
            result = json.loads(remote.run(['python3', '-c', TRANSACTION], timeout=180, data=json.dumps({
                'base_digest': change.base_digest, 'xml': decrypt(change.candidate), 'apply': apply,
            })))
            if result.get('error'):
                if result.get('conflict'):
                    raise RoxywiConflictError(result['error'])
                raise ValueError(result['error'])
            change.status = result['status']
            change.result = encrypt(json.dumps(result))
            change.save()
            event(cluster, user_id, f'{"apply" if apply else "validate"}:{change.id}', change.status)
            return result
        except Exception:
            change.status = 'unknown' if apply else 'failed'
            change.save()
            event(cluster, user_id, f'{"apply" if apply else "validate"}:{change.id}', change.status)
            raise


def restore_draft(cluster, change_id, user_id):
    from app.modules.pacemaker.schemas import Candidate
    old = change_for(cluster, change_id)
    if old.kind != 'cib':
        raise RoxywiInputError('Restore Corosync membership through a new reviewed membership change')
    # Restore is a NEW reviewed change against the current cluster, never a
    # forced CIB replacement or an automatic rollback after a network timeout.
    current = get_config(cluster)
    return draft(cluster, user_id, Candidate(xml=decrypt(old.previous), base_digest=current['digest']))


def operate(cluster, user_id, body):
    with locked(cluster):
        remote, xml = connection(cluster)
        config = configuration(xml)
        node_names = {member.name for member, _server in members(cluster)}
        if body.node and body.node not in node_names:
            raise RoxywiInputError('Node is not a registered cluster member')
        if body.action in ('standby', 'online'):
            if body.target not in node_names:
                raise RoxywiInputError('Select a registered node')
            argv = ['crm_standby', '--node', body.target, '--update', 'on' if body.action == 'standby' else 'off']
        elif body.action in ('maintenance-on', 'maintenance-off'):
            argv = ['crm_attribute', '--type', 'crm_config', '--name', 'maintenance-mode',
                    '--update', 'true' if body.action == 'maintenance-on' else 'false']
        else:
            resources = {item.get('id') for item in config.findall('./resources//*') if item.tag in ('primitive', 'group', 'clone', 'master', 'bundle')}
            if not body.target or body.target not in resources:
                raise RoxywiInputError('Select an existing cluster resource')
            argv = ['crm_resource', '--resource', body.target]
            if body.action == 'move':
                if not body.node:
                    raise RoxywiInputError('Select a destination node')
                argv += ['--move', '--node', body.node]
            elif body.action in ('clear', 'cleanup', 'restart'):
                argv += [{'clear': '--clear', 'cleanup': '--cleanup', 'restart': '--restart'}[body.action]]
            elif body.action in ('enable', 'disable'):
                argv += ['--meta', '--set-parameter', 'target-role', '--parameter-value',
                         'Started' if body.action == 'enable' else 'Stopped']
        event(cluster, user_id, f'{body.action}:{body.target}', 'started')
        try:
            remote.run(argv, timeout=90)
        except Exception:
            event(cluster, user_id, f'{body.action}:{body.target}', 'unknown')
            raise
        event(cluster, user_id, f'{body.action}:{body.target}', 'completed')


def logs(cluster, server_id):
    for _member, server in members(cluster):
        if server.server_id == server_id:
            return Remote(server).run(['journalctl', '--unit=corosync', '--unit=pacemaker',
                                       '--no-pager', '--lines=200', '--output=short-iso'])
    raise RoxywiInputError('Server is not a cluster member')
