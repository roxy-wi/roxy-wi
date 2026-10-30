"""Provision only empty supported Linux hosts; preserve existing clusters."""
import base64
import json
import secrets

from app.modules.roxywi.exception import RoxywiInputError
from app.modules.pacemaker.remote import Remote
from app.modules.pacemaker.platforms import SOURCE
from app.modules.pacemaker import install_log


PREFLIGHT = SOURCE + r'''
import os, subprocess
if os.path.exists('/etc/pve'):
    raise SystemExit('Refusing to provision a Proxmox host')
platform_profile()
if os.path.exists('/var/lib/roxy-wi/qnetd/data'):
    raise SystemExit('An existing Docker witness must remain outside the cluster')
for unit in ('corosync', 'pacemaker', 'corosync-qnetd'):
    if subprocess.run(['systemctl', 'is-active', '--quiet', unit]).returncode == 0:
        raise SystemExit('An existing cluster service is active')
if os.path.exists('/var/lib/pacemaker/cib/cib.xml'):
    raise SystemExit('An existing CIB must not be overwritten')
if os.path.exists('/etc/corosync/authkey'):
    raise SystemExit('An existing Corosync authentication key must not be overwritten')
if os.path.exists('/etc/corosync/corosync.conf'):
    raise SystemExit('An existing Corosync configuration must not be overwritten')
'''

PREPARE = r'''
import fcntl
lock = open('/run/lock/roxywi-bootstrap.lock', 'a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
''' + PREFLIGHT + r'''
import base64, json, pathlib, sys
data = json.load(sys.stdin)
install_packages('cluster', fence_pve=data.get('fence_pve', False))
fence_repaired = False
if data.get('fence_pve') or pathlib.Path('/usr/sbin/fence_pve').is_file():
    fence_repaired = repair_fence_pve()
for tool in ('cibadmin', 'crm_mon', 'crm_simulate', 'crm_verify', 'crm_diff', 'corosync-cmapctl'):
    if not shutil.which(tool):
        raise SystemExit('Required Pacemaker CLI tool is unavailable')
# Debian may start the default one-node cluster when the packages are first
# installed. Only nodes that passed preflight above reach this point.
installation_command(['systemctl', 'stop', 'pacemaker', 'corosync'], timeout=60)
# Preflight established that no CIB existed. Discard only the default CIB that
# Debian's package post-install startup may have created during this operation.
for default_cib in pathlib.Path('/var/lib/pacemaker/cib').glob('cib*'):
    if default_cib.is_file():
        default_cib.unlink()
os.umask(0o077)
pathlib.Path('/etc/corosync/authkey').write_bytes(base64.b64decode(data['key']))
pathlib.Path('/etc/corosync/corosync.conf').write_text(data['config'])
if data.get('syn_flood'):
    enable_syn_flood_protection()
# On RPM systems systemd creates StateDirectory only on first service start.
# Syntax validation must run before that first start.
pathlib.Path('/var/lib/corosync').mkdir(mode=0o755, parents=True, exist_ok=True)
if shutil.which('restorecon'):
    installation_command(['restorecon', '/etc/corosync/authkey', '/etc/corosync/corosync.conf',
                          '/var/lib/corosync'], timeout=15)
installation_command(['corosync', '-t'], timeout=15)
print(json.dumps({'fence_pve_repaired': fence_repaired}))
'''

REPOSITORIES = SOURCE + r'''
data = json.load(sys.stdin)
profile = platform_profile()
package_repositories(profile, 'cluster', role_packages(profile, 'cluster', data.get('fence_pve', False)))
'''

START = SOURCE + "\ninstallation_command(['systemctl', 'enable', '--now', 'corosync', 'pacemaker'], timeout=90)\n"


def corosync_config(cluster, checked):
    lines = [f'totem {{\n version: 2\n cluster_name: {cluster.name}\n transport: knet\n crypto_cipher: aes256\n crypto_hash: sha256\n}}',
             'nodelist {']
    for member, _server in checked:
        lines.append(f' node {{\n  name: {member.name}\n  nodeid: {member.nodeid}\n  ring0_addr: {member.address}\n }}')
    lines += ['}', 'quorum {\n provider: corosync_votequorum']
    if len(checked) == 2:
        lines.append(' two_node: 1\n wait_for_all: 1')
    lines += ['}', 'logging {\n to_syslog: yes\n timestamp: on\n}', '']
    return '\n'.join(lines)


def provision(cluster, user_id, *, syn_flood=False, fence_pve=False, log=None):
    from app.modules.pacemaker.service import members, locked, event, renew_lock
    if json.loads(cluster.corosync_settings).get('adopted'):
        raise RoxywiInputError('An adopted cluster cannot be bootstrapped again')

    def record(node, stage, level, message):
        renew_lock(cluster, token)
        if log is not None:
            log(node, stage, level, message)

    with locked(cluster) as token:
        checked = members(cluster)
        # Inspect every node before any node is modified.
        for member, server in checked:
            renew_lock(cluster, token)
            source = PREFLIGHT + '\nprint(installation_command(' + repr(
                ['hostname', '-f' if '.' in member.name else '-s']) + ').stdout.strip())\n'
            actual_name = install_log.run(Remote(server), source, member.name, 'Preflight', record)
            if actual_name != member.name:
                record(member.name, 'Preflight', 'error', 'Member name does not match the node hostname')
                raise RoxywiInputError('Member names must match node hostnames before provisioning')
            install_log.run(Remote(server), REPOSITORIES, member.name, 'Repositories', record,
                            data=json.dumps({'fence_pve': fence_pve}), timeout=240)
        config = corosync_config(cluster, checked)
        payload = json.dumps({'key': base64.b64encode(secrets.token_bytes(256)).decode(), 'config': config,
                              'syn_flood': syn_flood, 'fence_pve': fence_pve})
        event(cluster, user_id, 'bootstrap', 'started')
        for member, server in checked:
            renew_lock(cluster, token)
            result = json.loads(install_log.run(Remote(server), PREPARE, member.name, 'Packages and configuration',
                                               record, data=payload, timeout=600))
            if result['fence_pve_repaired']:
                event(cluster, user_id, f'fence-pve-repair:{member.name}', 'completed')
        # Start only after every node has the same authenticated membership.
        for member, server in checked:
            renew_lock(cluster, token)
            install_log.run(Remote(server), START, member.name, 'Start services', record, timeout=120)
        from app.modules.pacemaker.service import wait_ready
        record('Cluster', 'Readiness', 'info', 'Waiting for quorum and all registered nodes')
        try:
            wait_ready(cluster)
        except Exception:
            record('Cluster', 'Readiness', 'error', 'Cluster did not become quorate with all registered nodes online')
            raise
        record('Cluster', 'Readiness', 'info', 'All registered nodes are online and the cluster has quorum')
        settings = json.loads(cluster.corosync_settings)
        settings['syn_flood'] = syn_flood
        settings['fence_pve'] = fence_pve
        cluster.corosync_settings = json.dumps(settings)
        cluster.save(only=[type(cluster).corosync_settings])
        event(cluster, user_id, 'bootstrap', 'completed')
