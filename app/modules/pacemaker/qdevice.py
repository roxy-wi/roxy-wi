"""Initialize TLS for a new net qdevice through existing SSH credentials."""
import base64
import json

from app.modules.roxywi.exception import RoxywiInputError
from app.modules.pacemaker.remote import Remote
from app.modules.pacemaker.platforms import SOURCE
from app.modules.pacemaker.witness_docker import RUNTIME


WITNESS = SOURCE + RUNTIME + r'''
import base64, fcntl, json, os, pathlib, subprocess, sys, tempfile
data = json.load(sys.stdin)
if pathlib.Path('/etc/pve').exists():
    raise SystemExit('Refusing to configure a Proxmox host')
def run(args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
lock = open('/run/lock/roxywi-qnetd.lock', 'a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
state = container_state()
if data.get('docker') is False and state:
    raise SystemExit('A Docker witness already exists; explicit migration is required for native installation')
if data['action'] == 'init' and (data.get('docker') or state):
    if any(subprocess.run(['systemctl', 'is-active', '--quiet', unit], capture_output=True).returncode == 0
           for unit in ('corosync', 'pacemaker')):
        raise SystemExit('A witness must run outside the cluster')
    prepare_docker()
    state = container_state()
if state:
    if data['action'] in ('init', 'ca'):
        print(base64.b64encode(CERT.read_bytes()).decode())
    elif data['action'] == 'sign':
        os.umask(0o077)
        with tempfile.NamedTemporaryFile(dir=DATA, prefix='.request-', suffix='.crq') as request:
            request.write(base64.b64decode(data['request'], validate=True)); request.flush()
            os.chown(request.name, 65532, 65532)
            command(['docker', 'exec', CONTAINER, 'corosync-qnetd-certutil', '-s', '-c',
                     '/etc/corosync/qnetd/' + pathlib.Path(request.name).name, '-n', data['name']], timeout=120)
        print(base64.b64encode((DATA / 'nssdb' / ('cluster-' + data['name'] + '.crt')).read_bytes()).decode())
    else:
        raise SystemExit('Unknown witness action')
    sys.exit(0)
if data['action'] == 'ca':
    print(base64.b64encode(pathlib.Path('/etc/corosync/qnetd/nssdb/qnetd-cacert.crt').read_bytes()).decode())
    sys.exit(0)
if data['action'] == 'init':
    for unit in ('corosync', 'pacemaker'):
        if subprocess.run(['systemctl', 'is-active', '--quiet', unit]).returncode == 0:
            raise SystemExit('A witness must run outside the cluster')
    install_packages('witness')
    # RPM packages leave NSS initialization to the administrator; Debian may
    # already have initialized it. Never replace an existing certificate DB.
    database = pathlib.Path('/etc/corosync/qnetd/nssdb')
    if not database.exists():
        run(['corosync-qnetd-certutil', '-i'])
        user = subprocess.run(['systemctl', 'show', 'corosync-qnetd', '--property=User', '--value'],
                              check=True, capture_output=True, text=True).stdout.strip()
        if user:
            import pwd
            account = pwd.getpwnam(user)
            for path in [database, *database.rglob('*')]:
                os.chown(path, account.pw_uid, account.pw_gid)
    run(['systemctl', 'enable', '--now', 'corosync-qnetd'])
    print(base64.b64encode(pathlib.Path('/etc/corosync/qnetd/nssdb/qnetd-cacert.crt').read_bytes()).decode())
else:
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='roxywi-qnetd-') as tmp:
        path = pathlib.Path(tmp) / 'request.crq'
        path.write_bytes(base64.b64decode(data['request']))
        run(['corosync-qnetd-certutil', '-s', '-c', str(path), '-n', data['name']])
        cert = pathlib.Path('/etc/corosync/qnetd/nssdb') / ('cluster-' + data['name'] + '.crt')
        print(base64.b64encode(cert.read_bytes()).decode())
'''

WITNESS_STATUS = RUNTIME + r'''
import hashlib, json, pathlib, shutil, subprocess
state = container_state()
if state:
    print(json.dumps(docker_status(state)))
    raise SystemExit(0)
cert = pathlib.Path('/etc/corosync/qnetd/nssdb/qnetd-cacert.crt')
query = ['dpkg-query', '-W', '-f=${Version}', 'corosync-qnetd'] if shutil.which('dpkg-query') else ['rpm', '-q', '--qf', '%{VERSION}-%{RELEASE}', 'corosync-qnetd']
version = subprocess.run(query, capture_output=True, text=True)
print(json.dumps({
    'mode': 'native',
    'active': subprocess.run(['systemctl', 'is-active', '--quiet', 'corosync-qnetd']).returncode == 0,
    'version': version.stdout.strip() if version.returncode == 0 else None,
    'ca_fingerprint': hashlib.sha256(cert.read_bytes()).hexdigest() if cert.exists() else None,
}))
'''


def witness_server(server_id, group_id):
    from app.modules.pacemaker.adoption import server_for
    from app.modules.db.db_model import PacemakerCluster
    server = server_for(server_id, group_id)
    for cluster in PacemakerCluster.select():
        if server_id in [member['server_id'] for member in json.loads(cluster.servers)]:
            raise RoxywiInputError('Select a separate witness server outside every registered cluster')
    return server


def witness_status(server_id, group_id):
    server = witness_server(server_id, group_id)
    return json.loads(Remote(server).run(['python3', '-c', WITNESS_STATUS]))


def install_witness(server_id, group_id, *, docker=False):
    server = witness_server(server_id, group_id)
    Remote(server).run(['python3', '-c', WITNESS], data=json.dumps({'action': 'init', 'docker': docker}), timeout=1200)
    result = witness_status(server_id, group_id)
    if not result['active'] or not result['ca_fingerprint']:
        raise RoxywiInputError('The witness did not become ready; inspect its journal')
    return result

NODE = SOURCE + r'''
import base64, json, os, pathlib, subprocess, sys, tempfile
data = json.load(sys.stdin)
def run(args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
os.umask(0o077)
with tempfile.TemporaryDirectory(prefix='roxywi-qdevice-') as tmp:
    path = pathlib.Path(tmp) / 'cert'
    if data['action'] == 'init':
        install_packages('qdevice')
        path.write_bytes(base64.b64decode(data['ca']))
        if not pathlib.Path('/etc/corosync/qdevice/net/nssdb').exists():
            run(['corosync-qdevice-net-certutil', '-i', '-c', str(path)])
        if data.get('request'):
            run(['corosync-qdevice-net-certutil', '-r', '-n', data['name']])
            print(base64.b64encode(pathlib.Path('/etc/corosync/qdevice/net/nssdb/qdevice-net-node.crq').read_bytes()).decode())
    else:
        path.write_bytes(base64.b64decode(data['cert']))
        run(['corosync-qdevice-net-certutil', '-M' if data['action'] == 'sign' else '-m', '-c', str(path)])
        if data['action'] == 'sign':
            print(base64.b64encode(pathlib.Path('/etc/corosync/qdevice/net/nssdb/qdevice-net-node.p12').read_bytes()).decode())
'''


def initialize(cluster, checked, witness, renew):
    remote = Remote(witness)
    renew()
    ca = remote.run(['python3', '-c', WITNESS], data=json.dumps({'action': 'init'}), timeout=420).strip()
    primary = Remote(checked[0][1])
    request = ''
    for index, (_member, server) in enumerate(checked):
        renew()
        value = Remote(server).run(['python3', '-c', NODE], data=json.dumps({
            'action': 'init', 'ca': ca, 'name': cluster.name, 'request': index == 0,
        }), timeout=420).strip()
        if index == 0:
            request = value
    cert = remote.run(['python3', '-c', WITNESS], data=json.dumps({
        'action': 'sign', 'request': request, 'name': cluster.name,
    }), timeout=420).strip()
    pk12 = primary.run(['python3', '-c', NODE], data=json.dumps({'action': 'sign', 'cert': cert}), timeout=420).strip()
    for _member, server in checked[1:]:
        renew()
        Remote(server).run(['python3', '-c', NODE], data=json.dumps({'action': 'import', 'cert': pk12}), timeout=420)


def extend(primary, added, witness, renew):
    ca = Remote(witness).run(['python3', '-c', WITNESS], data=json.dumps({'action': 'ca'})).strip()
    pk12 = Remote(primary).run(['base64', '-w0', '/etc/corosync/qdevice/net/nssdb/qdevice-net-node.p12']).strip()
    for _member, server in added:
        renew()
        Remote(server).run(['python3', '-c', NODE], data=json.dumps({'action': 'init', 'ca': ca, 'request': False}), timeout=420)
        Remote(server).run(['python3', '-c', NODE], data=json.dumps({'action': 'import', 'cert': pk12}), timeout=420)
