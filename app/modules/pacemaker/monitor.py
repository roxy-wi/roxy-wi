"""Opt-in monitoring; send notifications only when cluster health changes."""
import json
from datetime import timedelta
from uuid import uuid4

from app.modules.common.time import utc_now
from app.modules.db.db_model import PacemakerCluster, ServiceNotification
from app.modules.pacemaker import service
from app.modules.roxywi.exception import RoxywiConflictError


def dispatch():
    from app.modules.pacemaker.operations import enqueue
    queued = 0
    due = utc_now() - timedelta(seconds=60)
    for cluster in PacemakerCluster.select().where(
        (PacemakerCluster.monitor_enabled == True) &
        ((PacemakerCluster.checked_at.is_null()) | (PacemakerCluster.checked_at < due))
    ):
        try:
            enqueue(cluster, None, 'monitor')
            queued += 1
        except RoxywiConflictError:
            continue
    return queued


def health(state):
    if not state['quorate']:
        return 'quorum-lost'
    if any(node['online'] != 'true' or node['unclean'] == 'true' for node in state['nodes']):
        return 'node-unavailable'
    if state['failures'] or any(resource['failed'] == 'true' or resource['blocked'] == 'true' for resource in state['resources']):
        return 'resource-failed'
    witness = state.get('quorum_details', {})
    if witness.get('configured') and witness.get('votes') == 0:
        return 'witness-unavailable'
    return 'healthy'


def check(cluster):
    with service.locked(cluster,maintenance_id=json.loads(cluster.corosync_settings).get('node_maintenance')):
        checked = service.members(cluster)
        try:
            observed = health(service.status(cluster))
        except Exception:
            observed = 'unreachable'
        now = utc_now()
        with PacemakerCluster._meta.database.atomic():
            current = service.get_cluster(cluster.id, cluster.group_id)
            if current.monitor_enabled and current.health != observed:
                service.event(cluster, 0, 'health', observed)
                if observed != 'healthy' or current.health not in ('unknown', 'healthy'):
                    ServiceNotification.create(event_id=str(uuid4()), category='pacemaker', observed_at=now,
                        payload=json.dumps({'service': 'pacemaker', 'server_address': checked[0][1].ip,
                            'group_id': int(cluster.group_id), 'level': 'info' if observed == 'healthy' else 'critical',
                            'message': f'Pacemaker cluster {cluster.name}: {observed}', 'alert_type': 'service'}))
            PacemakerCluster.update(health=observed, checked_at=now).where(PacemakerCluster.id == cluster.id).execute()
