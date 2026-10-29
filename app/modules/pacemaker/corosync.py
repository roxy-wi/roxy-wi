"""Review and coordinate authenticated Corosync membership changes."""
import base64
import hashlib
import json
import secrets
from app.modules.service.ha_topology import topology_guarded

from app.modules.db.db_model import PacemakerCluster, PacemakerChange
from app.modules.db.server import get_server_with_group
from app.modules.pacemaker import service
from app.modules.pacemaker.bootstrap import corosync_config, PREFLIGHT, PREPARE
from app.modules.pacemaker.remote import Remote
from app.modules.pacemaker.schemas import CorosyncCandidate
from app.modules.roxywi.exception import RoxywiInputError, RoxywiConflictError


FILE = r'''
import hashlib, json, os, pathlib, subprocess, sys
data = json.load(sys.stdin)
config = pathlib.Path('/etc/corosync/corosync.conf')
stage = config.parent / ('.roxywi-' + data['token'] + '.conf')
if data['action'] == 'cleanup':
    stage.unlink(missing_ok=True)
    sys.exit(0)
if hashlib.sha256(config.read_bytes()).hexdigest() != data['digest']:
    raise SystemExit('Corosync configuration changed')
if data['action'] == 'stage':
    fd = os.open(stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(data['config'])
        stream.flush()
        os.fsync(stream.fileno())
    subprocess.run(['corosync', '-t', '-c', str(stage)], check=True, capture_output=True, timeout=15)
elif data['action'] == 'commit':
    os.replace(stage, config)
'''


def fingerprint(text):
    return hashlib.sha256(text.encode()).hexdigest()


def read_all(cluster):
    return [(member, server, Remote(server).run(['cat', '/etc/corosync/corosync.conf']))
            for member, server in service.members(cluster)]


def render(cluster, body, checked):
    result = corosync_config(cluster, checked)
    result = result.replace(' transport: knet', f' token: {body.token}\n transport: knet')
    if body.qdevice_server_id:
        witness = get_server_with_group(body.qdevice_server_id, cluster.group_id)
        if witness.server_id in [member.server_id for member, _s in checked] or not witness.enabled or witness.type_ip:
            raise RoxywiInputError('Quorum witness must be a separate enabled physical server entry')
        # The net model uses mutually authenticated TLS; never downgrade to tls: off.
        from ipaddress import ip_address
        address = str(ip_address(witness.ip))
        result = result.replace(' two_node: 1\n wait_for_all: 1', '')
        result = result.replace(' provider: corosync_votequorum',
            ' provider: corosync_votequorum\n device {\n  votes: 1\n  model: net\n  net {\n'
            f'   host: {address}\n   algorithm: ffsplit\n   tls: required\n  }}\n }}')
    return result


def draft(cluster, user_id, body):
    if json.loads(cluster.corosync_settings).get('membership_managed') is False:
        raise RoxywiInputError('Adopted Corosync settings are preserved. Migrate to a managed transport configuration before changing membership or the witness')
    if body.name != cluster.name:
        raise RoxywiInputError('Cluster name cannot be changed')
    with service.locked(cluster):
        checked = []
        for member in body.members:
            server = get_server_with_group(member.server_id, cluster.group_id)
            if not server.enabled or server.type_ip:
                raise RoxywiInputError('Select enabled physical server entries')
            # Prevent attaching servers already managed by another cluster.
            for other in PacemakerCluster.select().where(PacemakerCluster.id != cluster.id):
                if member.server_id in [item['server_id'] for item in json.loads(other.servers)]:
                    raise RoxywiInputError('Server is registered in another cluster')
            checked.append((member, server))
        previous = read_all(cluster)
        if len({config for _m, _s, config in previous}) != 1:
            raise RoxywiInputError('Corosync files differ across nodes; reconcile drift before changing membership')
        config = render(cluster, body, checked)
        change = PacemakerChange.create(cluster=cluster, user_id=user_id, kind='corosync',
            base_digest=fingerprint(previous[0][2]), candidate=service.encrypt(config), previous=service.encrypt(previous[0][2]),
            details=service.encrypt(body.model_dump_json()))
        service.event(cluster, user_id, f'corosync-draft:{change.id}', 'saved')
        return change


@topology_guarded
def execute(cluster, change, user_id, *, apply=False):
    with service.locked(cluster) as lease:
        if json.loads(cluster.corosync_settings).get('membership_managed') is False:
            raise RoxywiInputError('Adopted Corosync transport requires an explicit migration before managed membership changes')
        if change.status in ('applied', 'applying', 'unknown'):
            raise RoxywiConflictError('This change was already attempted; inspect state before retrying')
        if apply and change.status != 'validated':
            raise RoxywiInputError('Validate the Corosync change first')
        body = CorosyncCandidate.model_validate_json(service.decrypt(change.details))
        existing = read_all(cluster)
        if any(fingerprint(config) != change.base_digest for _m, _s, config in existing):
            raise RoxywiConflictError('Corosync files changed since this draft was created')
        state = service.status(cluster)
        old_settings = json.loads(cluster.corosync_settings)
        if old_settings.get('qdevice_server_id') and body.qdevice_server_id and old_settings['qdevice_server_id'] != body.qdevice_server_id:
            raise RoxywiInputError('Migrate existing qdevice certificates explicitly before selecting another witness')
        if not state['quorate'] or any(node['online'] != 'true' for node in state['nodes']):
            raise RoxywiInputError('Corosync changes require quorum and every current node online')
        old_ids = {member.server_id for member, _s, _conf in existing}
        checked = [(member, get_server_with_group(member.server_id, cluster.group_id)) for member in body.members]
        if any(not server.enabled or server.type_ip for _member, server in checked):
            raise RoxywiInputError('Cluster members must be enabled physical server entries')
        new_ids = {member.server_id for member, _s in checked}
        # Recheck on validation and apply, including drafts validated by older
        # versions. A surviving member is needed to reload the running cluster.
        primary = next((server for member, server in checked if member.server_id in old_ids), None)
        if primary is None:
            raise RoxywiInputError('Keep at least one existing member; replace cluster nodes in separate reviewed changes')
        # Changing node IDs/addresses in place requires an explicit external
        # maintenance procedure. Add/remove complete nodes through this workflow.
        for member, _server in checked:
            for old, _s, _conf in existing:
                if member.server_id == old.server_id and member != old:
                    raise RoxywiInputError('Existing node identity/address cannot change during online reconfiguration')
        for old, _server, _conf in existing:
            if old.server_id not in new_ids:
                node = next((item for item in state['nodes'] if item['name'] == old.name), None)
                if not node or node['standby'] != 'true' or any(old.name in r['nodes'] for r in state['resources']):
                    raise RoxywiInputError('Put removed nodes in standby and drain their resources first')
        token = secrets.token_hex(16)
        candidate = service.decrypt(change.candidate)
        change.status = 'applying' if apply else 'validating'
        change.save()
        try:
            for old, server, _conf in existing:
                if old.server_id not in new_ids:
                    continue
                service.renew_lock(cluster, lease)
                Remote(server).run(['python3', '-c', FILE], data=json.dumps({
                    'action': 'stage', 'token': token, 'digest': change.base_digest, 'config': candidate,
                }))
            for member, server in checked:
                if member.server_id not in old_ids:
                    Remote(server).run(['python3', '-c', PREFLIGHT])
                    if Remote(server).run(['hostname', '-f' if '.' in member.name else '-s']).strip() != member.name:
                        raise RoxywiInputError('New node hostname must match its registered name')
            if apply:
                # Prepare new nodes with the same authentication key before
                # reloading membership on any running node.
                key = Remote(existing[0][1]).run(['base64', '-w0', '/etc/corosync/authkey'])
                for member, server in checked:
                    if member.server_id not in old_ids:
                        service.renew_lock(cluster, lease)
                        prepared = json.loads(Remote(server).run(['python3', '-c', PREPARE], data=json.dumps({'key': key, 'config': candidate,
                            'syn_flood': old_settings.get('syn_flood', False),
                            'fence_pve': old_settings.get('fence_pve', False)}), timeout=450))
                        if prepared['fence_pve_repaired']:
                            service.event(cluster, user_id, f'fence-pve-repair:{member.name}', 'completed')
                if body.qdevice_server_id and old_settings.get('qdevice_server_id') != body.qdevice_server_id:
                    from app.modules.pacemaker.qdevice import initialize
                    initialize(cluster, checked, get_server_with_group(body.qdevice_server_id, cluster.group_id),
                               lambda: service.renew_lock(cluster, lease))
                elif body.qdevice_server_id:
                    from app.modules.pacemaker.qdevice import extend
                    extend(existing[0][1], [(m, s) for m, s in checked if m.server_id not in old_ids],
                           get_server_with_group(body.qdevice_server_id, cluster.group_id),
                           lambda: service.renew_lock(cluster, lease))
                if old_settings.get('qdevice_server_id') and not body.qdevice_server_id:
                    for _member, server, _conf in existing:
                        Remote(server).run(['systemctl', 'disable', '--now', 'corosync-qdevice'])
                for old, server, _conf in existing:
                    if old.server_id not in new_ids:
                        Remote(server).run(['systemctl', 'disable', '--now', 'pacemaker', 'corosync'], timeout=90)
                for old, server, _conf in existing:
                    if old.server_id in new_ids:
                        Remote(server).run(['python3', '-c', FILE], data=json.dumps({
                            'action': 'commit', 'token': token, 'digest': change.base_digest,
                        }))
                Remote(primary).run(['corosync-cfgtool', '-R'])
                for member, server in checked:
                    if member.server_id not in old_ids:
                        Remote(server).run(['systemctl', 'enable', '--now', 'corosync', 'pacemaker'], timeout=90)
                    if body.qdevice_server_id:
                        Remote(server).run(['systemctl', 'enable', '--now', 'corosync-qdevice'], timeout=60)
                for old, server, _conf in existing:
                    if old.server_id not in new_ids:
                        # Removing the stale Pacemaker node record is distinct
                        # from removing the Corosync membership.
                        Remote(primary).run(['crm_node', '--force', '--remove', old.name])
                PacemakerCluster.update(servers=json.dumps([m.model_dump() for m, _s in checked]),
                    corosync_settings=json.dumps({**old_settings, 'token': body.token, 'qdevice_server_id': body.qdevice_server_id})).where(PacemakerCluster.id == cluster.id).execute()
                updated = service.get_cluster(cluster.id, cluster.group_id)
                service.wait_ready(updated)
                if body.qdevice_server_id:
                    from app.modules.pacemaker.witness_migration import wait_verify
                    witness = get_server_with_group(body.qdevice_server_id, cluster.group_id)
                    wait_verify([updated], witness.ip)
            change.status = 'applied' if apply else 'validated'
            change.result = service.encrypt(json.dumps({'status': change.status, 'simulation':
                'Corosync syntax checked on every existing node. Applying reloads membership across the cluster; new nodes are provisioned and removed nodes are stopped.'}))
            change.save()
            service.event(cluster, user_id, f'corosync:{change.id}', change.status)
        except Exception:
            change.status = 'unknown' if apply else 'failed'
            change.save()
            service.event(cluster, user_id, f'corosync:{change.id}', change.status)
            raise
        finally:
            for _member, server, _conf in existing:
                try:
                    Remote(server).run(['python3', '-c', FILE], data=json.dumps({'action': 'cleanup', 'token': token}))
                except Exception:
                    pass
