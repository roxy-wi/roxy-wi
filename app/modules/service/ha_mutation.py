"""Serialize server/HA mutations with reviewed maintenance reservations."""
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from functools import wraps
from inspect import signature
import os
import json
from threading import get_ident
from types import SimpleNamespace

from flask import has_request_context

from app.modules.common.file_lock import file_lock
from app.modules.db.db_model import HaCluster, HaClusterSlave, PacemakerCluster
from app.modules.roxywi.exception import RoxywiResourceNotFound, RoxywiConflictError
from app.modules.service.ha_topology import topology_lock, owned


_held = ContextVar('keepalived_mutation_locks', default=None)
_pm_held = ContextVar('pacemaker_member_mutation_locks', default=None)


def check_idle(provider, cluster, group_id=None):
    from app.modules.service.ha_maintenance import assert_idle
    from app.modules.roxywi.common import require_active_group_access
    if cluster is None:
        raise RoxywiResourceNotFound('HA cluster not found')
    if has_request_context():
        require_active_group_access(cluster.group_id)
    elif group_id is not None and int(cluster.group_id) != int(group_id):
        raise RoxywiResourceNotFound('HA cluster not found')
    assert_idle(provider, cluster.id, cluster.group_id)


@contextmanager
def pacemaker_members(server_ids, group_id=None):
    """Use the same durable cluster lock as maintenance enqueue and execution."""
    from app.modules.pacemaker import service
    servers = {int(ident) for ident in server_ids}
    clusters = {cluster.id: cluster for cluster in PacemakerCluster.select()
                if servers.intersection(int(member['server_id']) for member in json.loads(cluster.servers))} if servers else {}
    owner = (os.getpid(), get_ident())
    previous = _pm_held.get()
    held = previous.ids if owned(previous) else frozenset()
    ids = set(clusters)
    new_ids = ids - held
    if held and new_ids and min(new_ids) < max(held):
        raise RoxywiConflictError('Cluster membership changed during this operation; retry the request')
    with ExitStack() as stack:
        for ident in sorted(new_ids):
            check_idle('pacemaker', clusters[ident], group_id)
            # locked() rechecks the durable node_maintenance marker after the
            # atomic lock-token acquisition. An already queued maintenance task
            # is additionally protected by assert_idle under that same lock.
            stack.enter_context(service.locked(clusters[ident]))
        lease = SimpleNamespace(owner=owner, ids=held | ids, active=True)
        token = _pm_held.set(lease)
        try:
            for ident in sorted(ids):
                cluster = service.get_cluster(ident, clusters[ident].group_id)
                check_idle('pacemaker', cluster, group_id)
            yield
        finally:
            lease.active = False
            _pm_held.reset(token)


@contextmanager
def mutation(cluster_id=None, *, server_ids=(), group_id=None):
    # Use the cluster's real group when checking its durable reservation. In
    # particular, a global administrator must not bypass another group's plan.
    from app.modules.service.ha_maintenance import path_lock
    server_ids = tuple(server_ids)
    with topology_lock(), ExitStack() as stack:
        ids = {int(cluster_id)} if cluster_id is not None else set()
        ids.update(member.cluster_id_id for member in HaClusterSlave.select().where(
            HaClusterSlave.server_id.in_(list(server_ids))))
        owner = (os.getpid(), get_ident())
        previous = _held.get()
        held = previous.ids if owned(previous) else frozenset()
        new_ids = ids - held
        if held and new_ids and min(new_ids) < max(held):
            # All writers acquire cluster locks in ascending order. Nested
            # callers discovering an earlier ID must retry the whole request
            # instead of waiting while holding a later lock.
            raise RoxywiConflictError('Cluster membership changed during this operation; retry the request')
        for ident in sorted(new_ids):
            check_idle('keepalived', HaCluster.get_or_none(HaCluster.id == ident), group_id)
            try:
                stack.enter_context(file_lock(path_lock(SimpleNamespace(provider='keepalived', cluster_id=ident)), blocking=False))
            except BlockingIOError:
                raise RoxywiConflictError('HA maintenance or another cluster operation is running; retry the request') from None
        lease = SimpleNamespace(owner=owner, ids=held | ids, active=True)
        token = _held.set(lease)
        try:
            for ident in sorted(ids):
                cluster = HaCluster.get_or_none(HaCluster.id == ident)
                check_idle('keepalived', cluster, group_id)
            with pacemaker_members(server_ids, group_id):
                yield
        finally:
            lease.active = False
            _held.reset(token)


def guarded(function):
    """Keep direct service callers under the same lock as HTTP mutations."""
    parameters = signature(function)
    @wraps(function)
    def wrapped(*args, **kwargs):
        values = parameters.bind(*args, **kwargs).arguments
        body = values.get('cluster')
        servers = getattr(body, 'servers', None) or values.get('servers') or []
        server_ids = [server['id'] if isinstance(server, dict) else server.id for server in servers]
        with mutation(values.get('cluster_id'), server_ids=server_ids, group_id=values.get('group_id')):
            return function(*args, **kwargs)
    return wrapped


def guarded_server(function):
    parameters = signature(function)
    @wraps(function)
    def wrapped(*args, **kwargs):
        values = parameters.bind(*args, **kwargs).arguments
        with mutation(server_ids=[values['server_id']]):
            return function(*args, **kwargs)
    return wrapped


def guarded_service(function):
    """Protect Keepalived apply/install/action paths, including queued workers."""
    parameters = signature(function)
    @wraps(function)
    def wrapped(*args, **kwargs):
        values = parameters.bind(*args, **kwargs).arguments
        service = values.get('service', values.get('ansible_role', values.get('service_name')))
        if service != 'keepalived' or values.get('just_save') in ('test', 'check', 'status'):
            return function(*args, **kwargs)
        from app.modules.db import server as server_sql
        body = values.get('json_data')
        body = body.model_dump(mode='json') if hasattr(body, 'model_dump') else body or {}
        server_ids = [server['id'] for server in body.get('servers') or []]
        if values.get('server_id') is not None:
            server_ids.append(values['server_id'])
        ips = values.get('server_ips') or []
        if values.get('server_ip'):
            ips = [*ips, values['server_ip']]
        server_ids.extend(server_sql.get_server_by_ip(ip).server_id for ip in ips)
        with mutation(values.get('cluster_id') or body.get('cluster_id'), server_ids=server_ids):
            return function(*args, **kwargs)
    return wrapped
