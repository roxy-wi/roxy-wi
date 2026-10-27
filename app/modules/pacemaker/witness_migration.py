"""Reviewed native-to-Docker qnetd migration with an independent host rollback timer."""
import hashlib
import json
import re
import time
from contextlib import ExitStack
from uuid import uuid4

from app.modules.db.db_model import PacemakerCluster
from app.modules.pacemaker import service
from app.modules.pacemaker.platforms import SOURCE
from app.modules.pacemaker.remote import Remote
from app.modules.pacemaker.witness_docker import RUNTIME
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiValidationError

RECOVERY = r'''
import fcntl, re, stat
NATIVE = pathlib.Path('/etc/corosync/qnetd')
def atomic(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.state-', delete=False) as stream:
        temporary = pathlib.Path(stream.name)
        try:
            json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())
            temporary.chmod(0o600); os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
def folder(token):
    if not re.fullmatch(r'[0-9a-f]{32}', token): raise ValueError('Invalid migration identity')
    return ROOT / 'migrations' / token
def load(token):
    return json.loads((folder(token) / 'state.json').read_text())
def save(token, state):
    atomic(folder(token) / 'state.json', state)
def timer_name(token): return 'roxywi-qnetd-rollback-' + token

def recover(token):
    state = load(token)
    if state['phase'] in ('committed', 'rolled-back'):
        return state
    try:
        existing = container_state()
        if existing:
            if existing['Config']['Labels'].get('org.roxy-wi.migration') != token:
                raise ValueError('Recovery refuses an unrelated Docker container')
            command(['docker', 'rm', '-f', CONTAINER])
        if DATA.exists():
            destination = folder(token) / 'docker-stopped'
            if destination.exists(): raise ValueError('Recovery data already exists; inspect the migration journal')
            os.replace(DATA, destination)
        if state['enabled'] == 'enabled': command(['systemctl', 'enable', 'corosync-qnetd'])
        else: command(['systemctl', 'disable', 'corosync-qnetd'])
        command(['systemctl', 'start', 'corosync-qnetd'])
        if hashlib.sha256((NATIVE / 'nssdb/qnetd-cacert.crt').read_bytes()).hexdigest() != state['ca_fingerprint']:
            raise ValueError('Native CA changed during recovery')
        command(['corosync-qnetd-tool', '-s'])
        state['phase'] = 'rolled-back'; save(token, state)
        subprocess.run(['systemctl', 'stop', timer_name(token) + '.timer'], capture_output=True, timeout=15)
        return state
    except BaseException:
        state['phase'] = 'recovery-required'; save(token, state)
        raise
'''
RECOVER_CODE = SOURCE + RUNTIME + RECOVERY
HELPERS = r'''
def tree_digest(root):
    digest = hashlib.sha256(); total = 0
    files = sorted(root.rglob('*'))
    if len(files) > 1000: raise ValueError('Unexpectedly large witness certificate directory')
    for path in files:
        metadata = path.lstat()
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('Witness certificate storage contains unsupported file types')
        digest.update(str(path.relative_to(root)).encode()); digest.update(str((stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid)).encode())
        if path.is_file():
            total += metadata.st_size
            if total > 32 * 1024 * 1024: raise ValueError('Unexpectedly large witness certificate database')
            digest.update(path.read_bytes())
    return digest.hexdigest()

def source_info(token=None):
    ensure_no_pending(token)
    if pathlib.Path('/etc/pve').exists(): raise ValueError('Proxmox hosts cannot be migration targets')
    platform_profile()
    if container_state(): raise ValueError('The selected host already has a Docker witness')
    if DATA.exists(): raise ValueError('Orphaned Docker witness data requires recovery first')
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'corosync-qnetd'], capture_output=True).returncode:
        raise ValueError('Select a running native witness')
    for unit in ('corosync', 'pacemaker'):
        if subprocess.run(['systemctl', 'is-active', '--quiet', unit], capture_output=True).returncode == 0:
            raise ValueError('The witness must remain outside the cluster')
    enabled = subprocess.run(['systemctl','is-enabled','corosync-qnetd'],capture_output=True,text=True).stdout.strip()
    if enabled not in ('enabled','disabled'): raise ValueError('Unsupported native witness enablement state')
    pid = command(['systemctl', 'show', 'corosync-qnetd', '--property=MainPID', '--value'])
    args = pathlib.Path('/proc/' + str(int(pid)) + '/cmdline').read_bytes().decode().strip('\x00').split('\x00')
    # Preserve the standard TCP 5403 listener and refuse unreviewed custom semantics.
    allowed = ('-f', '-4', '-6')
    if pathlib.Path(args[0]).name != 'corosync-qnetd' or any(value not in allowed for value in args[1:]):
        raise ValueError('Custom qnetd arguments need an explicit compatible configuration; automatic conversion is unavailable')
    if '-4' in args or '-6' in args:
        raise ValueError('Custom qnetd address-family settings are not supported by the managed container')
    cert = NATIVE / 'nssdb/qnetd-cacert.crt'
    if not cert.is_file(): raise ValueError('The native witness has no initialized CA')
    connections = command(['corosync-qnetd-tool', '-l'])
    clusters = sorted(set(re.findall(r'^Cluster "(.*)":', connections, re.MULTILINE)))
    if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,62}', name) for name in clusters):
        raise ValueError('A connected cluster name cannot be managed by this workflow')
    if connections.strip() and not clusters: raise ValueError('Cannot identify connected qnetd clusters')
    return {'mode': 'native', 'ca_fingerprint': hashlib.sha256(cert.read_bytes()).hexdigest(),
            'database_digest': tree_digest(NATIVE), 'enabled': enabled, 'arguments': args[1:], 'clusters': clusters}

def pending():
    root = ROOT / 'migrations'
    if not root.exists(): return []
    result = []
    for path in sorted(root.glob('*/state.json')):
        state = json.loads(path.read_text())
        if state['phase'] not in ('committed', 'rolled-back'):
            result.append({'token': path.parent.name, 'phase': state['phase'], 'clusters':state.get('clusters',[])})
    return result

def copy_state(source, destination):
    shutil.copytree(source, destination)
    for path in [source, *source.rglob('*')]:
        relative = path.relative_to(source)
        metadata = path.stat()
        os.chown(destination / relative, metadata.st_uid, metadata.st_gid)

def prepare(token, expected):
    if pending(): raise ValueError('An unfinished migration must be recovered first')
    source = source_info()
    if source != expected: raise ValueError('The native witness changed; review a new migration plan')
    if not shutil.which('docker'):
        install_packages('witness-docker')
        command(['systemctl','enable','--now','docker'],timeout=60)
    if not shutil.which('docker'): raise ValueError('Docker Engine was installed but its CLI is unavailable')
    image = build_image()
    if source_info() != expected: raise ValueError('The native witness changed while preparing Docker')
    directory = folder(token); directory.mkdir(parents=True, mode=0o700)
    snapshot = directory / 'backup'
    copy_state(NATIVE, snapshot)
    if tree_digest(NATIVE) != source['database_digest'] or tree_digest(snapshot) != source['database_digest']:
        raise ValueError('The witness database changed during its backup')
    source.update(phase='prepared', image_id=image)
    save(token, source)
    probe = directory / 'probe'; shutil.copytree(snapshot, probe)
    for path in [probe, *probe.rglob('*')]: os.chown(path, 65532, 65532)
    # Validate the existing NSS database/private key in an isolated container before stopping qnetd.
    for args in (['-L', '-n', 'QNetd Cert'], ['-K', '-f', '/etc/corosync/qnetd/nssdb/pwdfile.txt']):
        command(['docker','run','--rm','--network','none','--read-only','--user','65532:65532',
                 '--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','certutil',
                 '--volume',str(probe)+':/etc/corosync/qnetd:rw,Z',image,'-d','/etc/corosync/qnetd/nssdb',*args],timeout=60)
    recovery = directory / 'recover.py'
    recovery.write_text(RECOVER_CODE + '\nlock = open("/run/lock/roxywi-qnetd.lock", "a")\nfcntl.flock(lock, fcntl.LOCK_EX)\nrecover(' + repr(token) + ')\n')
    recovery.chmod(0o600)
    return source

def switch(token):
    state = load(token)
    if state['phase'] != 'prepared': raise ValueError('Migration is not prepared')
    current = source_info(token)
    if any(state[key] != value for key, value in current.items()): raise ValueError('Witness changed after preparation')
    try:
        state['phase'] = 'switching'; save(token,state)
        command(['systemd-run','--unit',timer_name(token),'--on-active=180s',
                 '/usr/bin/python3',str(folder(token)/'recover.py')])
        command(['systemctl','stop','corosync-qnetd'])
        if tree_digest(NATIVE) != state['database_digest']: raise ValueError('Witness database changed at switchover')
        shutil.copytree(folder(token)/'backup', DATA)
        for path in [DATA,*DATA.rglob('*')]: os.chown(path,65532,65532)
        launch_docker(state['image_id'],migration=token)
        for _ in range(45):
            container = container_state()
            if container and docker_status(container)['active']: break
            time.sleep(1)
        else: raise ValueError('The container witness did not become ready')
        if hashlib.sha256(CERT.read_bytes()).hexdigest() != state['ca_fingerprint']: raise ValueError('Container CA fingerprint differs')
        state['phase']='verifying'; save(token,state)
        return state
    except BaseException:
        recover(token)
        raise

def commit(token):
    state=load(token)
    if state['phase'] != 'verifying': raise ValueError('Migration is not awaiting verification')
    if not docker_status(container_state())['active']: raise ValueError('Docker witness stopped before commit')
    if hashlib.sha256(CERT.read_bytes()).hexdigest() != state['ca_fingerprint']: raise ValueError('Witness CA changed')
    command(['systemctl','disable','corosync-qnetd'])
    atomic(ROOT/'mode.json',{'mode':'docker','migration':token,'ca_fingerprint':state['ca_fingerprint']})
    state['phase']='committed'; save(token,state)
    subprocess.run(['systemctl','stop',timer_name(token)+'.timer'],capture_output=True,timeout=15)
    return state
'''
REMOTE = SOURCE + RUNTIME + RECOVERY + '\nRECOVER_CODE = ' + repr(RECOVER_CODE) + '\n' + HELPERS + r'''
import sys
os.umask(0o077)
data=json.load(sys.stdin)
lock=open('/run/lock/roxywi-qnetd.lock','a')
try:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    action=data['action']
    if action=='plan':
        unfinished=pending()
        result={'pending':unfinished} if unfinished else {'source':source_info(),'pending':[]}
    elif action=='prepare': result=prepare(data['token'],data['source'])
    elif action=='switch': result=switch(data['token'])
    elif action=='commit': result=commit(data['token'])
    elif action=='recover': result=recover(data['token'])
    else: raise ValueError('Unknown migration action')
    print(json.dumps({'data':result}))
except ValueError as exc:
    print(json.dumps({'error':str(exc)}))
except BaseException:
    print(json.dumps({'error':'Witness migration step failed; use migration recovery and inspect the operation details'}))
'''


def call(server, action, **data):
    result = json.loads(Remote(server).run(['python3', '-c', REMOTE], data=json.dumps(dict(action=action, **data)), timeout=1200))
    if result.get('error'):
        raise RoxywiValidationError(result['error'])
    return result['data']


def attachments(server, group_id, names=()):
    found = []
    for cluster in PacemakerCluster.select():
        settings = json.loads(cluster.corosync_settings)
        if settings.get('qdevice_server_id') == server.server_id or cluster.name in names:
            if int(cluster.group_id) != int(group_id):
                raise RoxywiValidationError('The witness serves a cluster outside the active group')
            if settings.get('transport_pending'):raise RoxywiValidationError('Recover the attached cluster transport before changing its witness')
            found.append(cluster)
    if set(names) - {c.name for c in found}:
        raise RoxywiValidationError('Register every connected cluster before migrating its shared witness')
    return sorted(found, key=lambda c: c.id)


def verify(clusters, witness_ip=None):
    from app.modules.pacemaker.quorum import details
    for cluster in clusters:
        state = service.status(cluster)
        if not state['quorate'] or any(n['online'] != 'true' or n['unclean'] == 'true' for n in state['nodes']):
            raise RoxywiValidationError('Every attached cluster member must be online and quorate')
        for _member, server in service.members(cluster):
            remote = Remote(server)
            quorum = remote.run(['env', 'LC_ALL=C', 'corosync-quorumtool', '-s'], allowed=(0, 2))
            client = remote.run(['env', 'LC_ALL=C', 'corosync-qdevice-tool', '-s', '-v'])
            if witness_ip and not re.search(r'^QNetd host:\s+' + re.escape(witness_ip) + r':5403\s*$', client, re.M):
                raise RoxywiValidationError('An attached node uses another witness address or port')
            if details(quorum)['votes'] < 1 or not re.search(r'^TLS active:\s+Yes', client, re.M):
                raise RoxywiValidationError('Every attached node must have an active TLS witness vote')


def wait_verify(clusters, witness_ip, timeout=75):
    deadline=time.monotonic()+timeout
    while True:
        try:
            verify(clusters,witness_ip)
            return
        except Exception:
            if time.monotonic()>=deadline: raise
            time.sleep(2)


def plan(server_id, group_id):
    from app.modules.pacemaker.qdevice import witness_server
    server = witness_server(server_id, group_id)
    host = call(server, 'plan')
    if host.get('pending'):
        for item in host['pending']: attachments(server,group_id,item.get('clusters',[]))
        return {'pending': host['pending'], 'server': server.hostname, 'eligible': False}
    clusters = attachments(server, group_id, host['source']['clusters'])
    verify(clusters, server.ip)
    data = {'source': host['source'], 'server_id': server_id,
            'identity': {'ip': server.ip, 'port': server.port, 'cred_id': server.cred_id},
            'clusters': [{'id': c.id, 'name': c.name, 'members': c.servers} for c in clusters]}
    return dict(data, pending=[], server=server.hostname, eligible=True,
                plan_digest=hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest())


def migrate(server_id, group_id, digest, user_id=0):
    from app.modules.pacemaker.qdevice import witness_server
    server = witness_server(server_id, group_id)
    current = plan(server_id, group_id)
    if not current.get('eligible') or current['plan_digest'] != digest:
        raise RoxywiConflictError('Witness migration plan changed; review it again')
    clusters = attachments(server, group_id, current['source']['clusters'])
    token = uuid4().hex
    with ExitStack() as stack:
        locks = [(c, stack.enter_context(service.locked(c))) for c in clusters]
        for c, lock in locks:
            from datetime import timedelta
            from app.modules.common.time import utc_now
            PacemakerCluster.update(lock_until=utc_now()+timedelta(minutes=25)).where(
                (PacemakerCluster.id==c.id)&(PacemakerCluster.lock_token==lock)).execute()
            if c.active_task_id:
                from app.modules.db.db_model import InstallationTasks
                active=InstallationTasks.get_or_none(InstallationTasks.id==c.active_task_id)
                if active and active.status not in ('completed','failed'): raise RoxywiConflictError('An attached cluster operation is pending')
        try:
            call(server, 'prepare', token=token, source=current['source'])
            # Preparation can include a slow image build; check node health again before stopping qnetd.
            verify(clusters, server.ip)
            for c, lock in locks: service.renew_lock(c, lock)
            call(server, 'switch', token=token)
            wait_verify(clusters,server.ip)
            result = call(server, 'commit', token=token)
            for cluster in clusters: service.event(cluster, user_id, 'witness-migration', 'completed')
            return {'phase': result['phase'], 'token': token, 'ca_fingerprint': result['ca_fingerprint']}
        except Exception as failure:
            try:
                restored=call(server, 'recover', token=token)
                if restored['phase']=='rolled-back':
                    wait_verify(clusters, server.ip)
                    raise RoxywiValidationError('Migration failed; the native witness and its votes were restored. Review a new plan before retrying') from failure
            except RoxywiValidationError:
                raise
            except Exception:
                pass  # The host timer independently restores the native service after a controller failure.
            raise RoxywiValidationError('Migration could not be completed; read migration status and use Recover native witness') from failure


def recover_migration(server_id, group_id, token):
    from app.modules.pacemaker.qdevice import witness_server
    server = witness_server(server_id, group_id)
    host = call(server, 'plan')
    if token not in [item['token'] for item in host.get('pending', [])]:
        raise RoxywiValidationError('No unfinished migration with this identity exists')
    entry=next(item for item in host['pending'] if item['token']==token)
    clusters=attachments(server,group_id,entry.get('clusters',[]))
    with ExitStack() as stack:
        for cluster in clusters: stack.enter_context(service.locked(cluster))
        result = call(server, 'recover', token=token)
        wait_verify(clusters, server.ip)
    return {'phase': result['phase'], 'token': token, 'ca_fingerprint': result['ca_fingerprint']}
