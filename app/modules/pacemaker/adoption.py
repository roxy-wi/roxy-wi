"""Discover and verify an existing cluster without writing to its nodes."""
import hashlib
import json
import re

from app.modules.db.db_model import PacemakerChange, PacemakerCluster, Server
from app.modules.db.server import get_server_with_group
from app.modules.pacemaker import service
from app.modules.pacemaker.remote import Remote
from app.modules.pacemaker.schemas import ClusterCreate, Member
from app.modules.pacemaker.xml import configuration, digest, summary
from app.modules.roxywi.exception import RoxywiInputError, RoxywiConflictError
from app.modules.service.ha_topology import topology_guarded


INSPECT = r'''
import json, pathlib, subprocess
if pathlib.Path('/etc/pve').exists():
    raise SystemExit('Refusing to manage a Proxmox host')
def read(args, allowed=(0,)):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode not in allowed:
        raise SystemExit('Cannot read running cluster state')
    return result.stdout
print(json.dumps({
    'cmap': read(['corosync-cmapctl']),
    'xml': read(['cibadmin', '--query']),
    'status': read(['crm_mon', '--one-shot', '--output-as=xml'], (0, 1, 2)),
    'config': pathlib.Path('/etc/corosync/corosync.conf').read_text(),
}))
'''


def server_for(server_id, group_id):
    server = get_server_with_group(server_id, group_id)
    if not server.enabled or server.type_ip:
        raise RoxywiInputError('Select an enabled physical server in the active group')
    return server


def inspect(server):
    raw = json.loads(Remote(server).run(['python3', '-c', INSPECT], timeout=120))
    values = {}
    for line in raw['cmap'].splitlines():
        match = re.fullmatch(r'(\S+) \([^)]*\) = (.*)', line)
        if match:
            values[match[1]] = match[2]
    cib = configuration(raw['xml'])
    names = {node.get('id'): node.get('uname') for node in cib.findall('./nodes/node')}
    indexes = sorted({key.split('.')[2] for key in values if key.startswith('nodelist.node.')})
    members = []
    for index in indexes:
        prefix = f'nodelist.node.{index}.'
        nodeid = values.get(prefix + 'nodeid')
        member = Member(server_id=1, nodeid=nodeid,
                        name=values.get(prefix + 'name') or names.get(nodeid),
                        address=values.get(prefix + 'ring0_addr'))
        members.append({key: value for key, value in member.model_dump().items() if key != 'server_id'})
    if not 2 <= len(members) <= 32:
        raise RoxywiInputError('Discovery requires a Corosync nodelist with 2–32 members')
    # Also validate the cluster name and uniqueness of identities before displaying them.
    ClusterCreate(name=values.get('totem.cluster_name'), members=[
        dict(member, server_id=index) for index, member in enumerate(members, 1)
    ])
    topology = {'name': values['totem.cluster_name'], 'members': sorted(members, key=lambda member: member['nodeid'])}
    return {**topology, 'topology_digest': hashlib.sha256(json.dumps(topology, sort_keys=True).encode()).hexdigest(),
            'base_digest': digest(raw['xml']), 'state': summary(raw['status']),
            'xml': raw['xml'], 'config': raw['config'],
            'settings': {'adopted': True, 'membership_managed': False,
                         'token': values.get('totem.token'),
                         'qdevice_host': values.get('quorum.device.net.host'),
                         'qdevice_model': values.get('quorum.device.model')}}


def discover(server_id, group_id):
    found = inspect(server_for(server_id, group_id))
    servers = list(Server.select().where((Server.group_id == group_id) & (Server.enabled == 1) & (Server.type_ip == 0)))
    members = []
    for member in found['members']:
        matches = [server for server in servers if server.hostname == member['name'] or server.ip == member['address']]
        members.append(dict(member, server_id=matches[0].server_id if len(matches) == 1 else None))
    existing = PacemakerCluster.get_or_none((PacemakerCluster.group_id == group_id) & (PacemakerCluster.name == found['name']))
    return {key: found[key] for key in ('name', 'topology_digest', 'base_digest', 'state', 'settings')} | {
        'members': members, 'existing_cluster_id': existing.id if existing else None,
    }


@topology_guarded
def adopt(body, group_id, user_id):
    seed = server_for(body.seed_server_id, group_id)
    found = inspect(seed)
    if found['base_digest'] != body.base_digest or found['topology_digest'] != body.topology_digest:
        raise RoxywiConflictError('Cluster changed after discovery; inspect it again before adopting')
    if body.name != found['name'] or sorted(
        [{key: value for key, value in member.model_dump().items() if key != 'server_id'} for member in body.members],
        key=lambda member: member['nodeid'],
    ) != found['members']:
        raise RoxywiInputError('Keep the discovered cluster name, node names, IDs and Corosync addresses')
    if seed.server_id not in [member.server_id for member in body.members]:
        raise RoxywiInputError('The discovery server must be mapped to one of the cluster members')
    snapshots = []
    for member in body.members:
        server = server_for(member.server_id, group_id)
        node = found if server.server_id == seed.server_id else inspect(server)
        if node['topology_digest'] != found['topology_digest'] or node['base_digest'] != found['base_digest']:
            raise RoxywiInputError('Mapped nodes do not report the same cluster and CIB configuration')
        # Verify which member this SSH destination actually represents; a cluster-wide
        # CIB alone cannot distinguish swapped or duplicated server mappings.
        node_id = Remote(server).run(['corosync-cmapctl', 'runtime.votequorum.this_node_id']).strip().split(' = ')[-1]
        if node_id != str(member.nodeid):
            raise RoxywiInputError('A server is mapped to the wrong Corosync node ID')
        snapshots.append({'server_id': server.server_id, 'config': node['config']})
    database = PacemakerChange._meta.database
    with database.atomic():
        cluster = service.register(ClusterCreate(name=body.name, description=body.description, members=body.members), group_id)
        cluster.corosync_settings = json.dumps(found['settings'])
        cluster.save(only=[PacemakerCluster.corosync_settings])
        PacemakerChange.create(cluster=cluster, user_id=user_id, kind='cib', status='applied',
                               base_digest=found['base_digest'], candidate=service.encrypt(found['xml']),
                               previous=service.encrypt(found['xml']),
                               details=service.encrypt(json.dumps({'adopted_baseline': True, 'corosync': snapshots})))
        service.event(cluster, user_id, 'adopt', 'completed')
    return cluster
