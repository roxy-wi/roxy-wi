"""Shared Keepalived observation for Checker and the HA interface."""
import json
import ipaddress
from pathlib import Path

from app.modules.connectors import containers, keepalived as probe
from app.modules.db import service as service_sql
from app.modules.integrations.keepalived_contract import KeepalivedSnapshot
from app.modules.pacemaker.remote import Remote
from app.modules.service import container_settings


def probe_settings(server) -> dict:
    """Resolve the saved binding without discovering or falling back to a host."""
    if service_sql.select_service_setting(server.server_id, 'keepalived', 'dockerized') == '1':
        runtime = container_settings.runtime(server.server_id, 'keepalived')
        if runtime['owner'] != 'root':
            raise ValueError('Keepalived requires a rootful host-network container')
        return dict(runtime=runtime, name=container_settings.name(server.server_id, 'keepalived'))
    return {}


def collect(server) -> KeepalivedSnapshot:
    """Use the server's existing SSH identity and configured container binding."""
    source = Path(probe.__file__).read_text(encoding='utf-8')
    data = probe_settings(server)
    prefix = containers.embedded() if data else ''
    source = prefix + source + '''
import json, sys
data = json.load(sys.stdin)
record = module.container_state(data['runtime'], data['name']) if data else None
result = collect(record)
if data:
    current = module.container_state(data['runtime'], data['name'])
    if (current.get('Id', current.get('ID')) != record.get('Id', record.get('ID')) or
            any(current['State'].get(key) != record['State'].get(key)
                for key in ('Pid', 'Running', 'Restarting', 'Paused', 'StartedAt'))):
        raise ValueError('Container changed during the probe')
print(json.dumps(result))
'''
    output = Remote(server).run(['python3', '-c', source], data=json.dumps(data), timeout=45)
    if probe_settings(server) != data:
        raise ValueError('Keepalived binding changed during the probe')
    return KeepalivedSnapshot.model_validate_json(output)


def summary(snapshot: KeepalivedSnapshot) -> str:
    """Keep the existing single-label UI, giving faults precedence over roles."""
    if snapshot.service == 'DOWN':
        return 'DOWN'
    states = {instance.state for instance in snapshot.instances}
    return next(state for state in ('FAULT', 'INIT', 'MASTER', 'BACKUP') if state in states)


def vip_owners(vips, observations):
    """Find actual address owners, normalizing IPv4/IPv6 and CIDR notation."""
    addresses = {
        node['id']: {str(ipaddress.ip_interface(ip).ip)
                     for ip in node['addresses']}
        for node in observations if not node.get('error')
    }
    return {
        str(ipaddress.ip_interface(vip).ip): [
            ident for ident, values in addresses.items()
            if str(ipaddress.ip_interface(vip).ip) in values
        ] for vip in vips
    }


def cluster_status(cluster_id, group_id):
    """Observe every registered VIP and member without persisting a health claim."""
    from app.modules.common.execution_context import group_settings
    from app.modules.db.db_model import HaClusterSlave, HaClusterVip
    from app.modules.service import ha_readiness

    def registration():
        cluster, nodes = ha_readiness.subject('keepalived', cluster_id, group_id)
        members = sorted(
            (row.router_id_id, row.server_id_id)
            for row in HaClusterSlave.select().where(
                HaClusterSlave.cluster_id == cluster_id)
        )
        vips = sorted(
            (row.router_id_id, str(ipaddress.ip_interface(row.vip).ip))
            for row in HaClusterVip.select().where(
                HaClusterVip.cluster_id == cluster_id)
        )
        identity = (cluster.readiness_key, ha_readiness.identities(nodes),
                    members, vips)
        return cluster, nodes, members, vips, identity

    cluster, nodes, members, vips, identity = registration()
    observations = []
    for name, server in nodes:
        try:
            with group_settings(group_id):
                observation = ha_readiness.keepalived_node(cluster, name, server)
        except Exception:
            # Report an unknown node, never convert a failed SSH read to BACKUP.
            observation = {'id': server.server_id, 'error': 'Node unavailable'}
        observations.append(observation)
    if registration()[-1] != identity:
        return {'status': 'unknown', 'message': 'Cluster changed during the check'}
    owners = vip_owners([vip for _router, vip in vips], observations)
    unreadable = any(node.get('error') for node in observations)
    results = []
    for router, vip in vips:
        member_ids = {ident for rid, ident in members if rid == router}
        states = {}
        for node in observations:
            if node.get('error') or node['id'] not in member_ids:
                continue
            states[node['id']] = (
                next((item['state'] for item in node.get('instances', [])
                      if item['name'] == f'VI_{router}'), 'UNKNOWN')
                if node['active'] else 'DOWN'
            )
        masters = [ident for ident, state in states.items() if state == 'MASTER']
        owner = owners[vip]
        if len(owner) > 1 or len(masters) > 1:
            status, message = 'error', 'Competing VIP owners or MASTER instances'
        elif owner and (owner[0] not in member_ids or
                        states.get(owner[0]) in ('DOWN', 'FAULT', 'BACKUP', 'INIT')):
            status, message = 'error', 'VIP is present on an invalid owner'
        elif unreadable:
            status, message = 'unknown', 'Not all members could be verified'
        elif not owner:
            status, message = 'error', 'VIP has no owner'
        elif len(member_ids) < 2 or 'UNKNOWN' in states.values():
            status, message = 'unknown', 'Registered VRRP instance is missing'
        elif any(state != 'BACKUP' for ident, state in states.items()
                 if ident != owner[0]):
            status, message = 'warning', 'VIP is available; a standby is not ready'
        else:
            status, message = 'ok', 'VIP has one MASTER and ready standby members'
        results.append({'vip': vip, 'status': status, 'message': message,
                        'owners': owner, 'masters': masters})
    status = next((value for value in ('error', 'unknown', 'warning', 'ok')
                   if any(row['status'] == value for row in results)), 'unknown')
    message = next((row['message'] for row in results if row['status'] == status),
                   'No registered VIPs')
    return {'status': status, 'message': message, 'vips': results}
