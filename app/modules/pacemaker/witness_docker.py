"""Fixed qnetd image recipe and bounded host-side Docker lifecycle helpers."""
import hashlib

DOCKERFILE = '''FROM debian:trixie-slim
LABEL org.roxy-wi.role="qnetd"
RUN printf '#!/bin/sh\\nexit 101\\n' > /usr/sbin/policy-rc.d && chmod +x /usr/sbin/policy-rc.d \\
 && apt-get update && apt-get install -y --no-install-recommends corosync-qnetd \\
 && rm -rf /var/lib/apt/lists/* /etc/corosync/qnetd/nssdb \\
 && install -d -o 65532 -g 65532 /etc/corosync/qnetd /run/corosync-qnetd
COPY entrypoint /usr/local/bin/roxywi-qnetd
RUN chmod 0755 /usr/local/bin/roxywi-qnetd
USER 65532:65532
EXPOSE 5403/tcp
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 CMD corosync-qnetd-tool -s >/dev/null || exit 1
ENTRYPOINT ["/usr/local/bin/roxywi-qnetd"]
'''
ENTRYPOINT = '''#!/bin/sh
set -eu
umask 077
if [ ! -f /etc/corosync/qnetd/nssdb/qnetd-cacert.crt ]; then
    if [ -e /etc/corosync/qnetd/nssdb ]; then
        echo "Incomplete witness certificate database; inspect persistent data before retrying" >&2
        exit 1
    fi
    corosync-qnetd-certutil -i
fi
exec corosync-qnetd -f -s req -c on
'''

RUNTIME = r'''
import hashlib, json, os, pathlib, shutil, socket, subprocess, tempfile, time
CONTAINER = 'roxywi-qnetd'
ROOT = pathlib.Path('/var/lib/roxy-wi/qnetd')
DATA = ROOT / 'data'
CERT = DATA / 'nssdb/qnetd-cacert.crt'
def command(args, timeout=30):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout).stdout.strip()
def ensure_no_pending(exclude=None):
    for name in ('migrations','lifecycle','trust'):
        for path in (ROOT/name).glob('*/state.json'):
            state=json.loads(path.read_text())
            if path.parent.name!=exclude and state['phase'] not in ('committed','rolled-back'):
                raise ValueError('An unfinished witness operation requires recovery in its matching GUI section first')
def container_state():
    if not shutil.which('docker'):
        return None
    # A daemon failure is an unknown state, never permission to install another witness.
    command(['docker', 'info', '--format', '{{.ServerVersion}}'])
    names = command(['docker', 'ps', '-a', '--format', '{{.Names}}']).splitlines()
    if CONTAINER not in names:
        return None
    try:
        state = json.loads(command(['docker', 'inspect', CONTAINER]))[0]
    except subprocess.CalledProcessError:
        # A recovery may remove the managed container between list and inspect.
        if CONTAINER not in command(['docker','ps','-a','--format','{{.Names}}']).splitlines(): return None
        raise
    mounts = state.get('Mounts', [])
    if (state.get('Config', {}).get('Labels', {}).get('org.roxy-wi.role') != 'qnetd'
        or not any(m.get('Type') == 'bind' and m.get('Source') == str(DATA)
                   and m.get('Destination') == '/etc/corosync/qnetd' for m in mounts)):
        raise SystemExit('The qnetd container name belongs to an unmanaged installation')
    return state

def docker_status(state):
    running = state['State'].get('Running', False)
    ready = False
    version = None
    if running:
        ready = subprocess.run(['docker', 'exec', CONTAINER, 'corosync-qnetd-tool', '-s'],
                               capture_output=True, timeout=15).returncode == 0
        version = command(['docker', 'exec', CONTAINER, 'dpkg-query', '-W', '-f=${Version}', 'corosync-qnetd'])
    return {'mode': 'docker', 'active': ready, 'version': version,
            'ca_fingerprint': hashlib.sha256(CERT.read_bytes()).hexdigest() if CERT.exists() else None,
            'container': CONTAINER, 'image_id': state['Image'],
            'health': state['State'].get('Health', {}).get('Status', 'unknown')}

def build_image():
    tag = 'roxywi-qnetd:' + RECIPE[:20]
    image = subprocess.run(['docker', 'image', 'inspect', tag], capture_output=True, text=True, timeout=30)
    if image.returncode != 0:
        with tempfile.TemporaryDirectory(prefix='roxywi-qnetd-build-') as build:
            pathlib.Path(build, 'Dockerfile').write_text(DOCKERFILE)
            pathlib.Path(build, 'entrypoint').write_text(ENTRYPOINT)
            command(['docker', 'build', '--label', 'org.roxy-wi.recipe=' + RECIPE, '-t', tag, build], timeout=600)
    image_id = json.loads(command(['docker', 'image', 'inspect', tag]))[0]['Id']
    return image_id

def launch_docker(image_id, migration=None):
    command(['docker', 'run', '--detach', '--name', CONTAINER, '--label', 'org.roxy-wi.role=qnetd',
             '--label', 'org.roxy-wi.recipe=' + RECIPE, *(['--label', 'org.roxy-wi.migration=' + migration] if migration else []), '--restart', 'unless-stopped', '--network', 'host',
             '--user', '65532:65532', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
             '--pids-limit', '64', '--memory', '128m', '--cpus', '0.5',
             '--tmpfs', '/run/corosync-qnetd:rw,nosuid,nodev,noexec,uid=65532,gid=65532,mode=0700,size=4m',
             '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,mode=1777,size=16m',
             '--volume', str(DATA) + ':/etc/corosync/qnetd:rw,Z', image_id])

def prepare_docker():
    ensure_no_pending()
    platform_profile()
    retained = False
    receipt = ROOT / 'mode.json'
    if receipt.is_file():
        recorded = json.loads(receipt.read_text())
        retained = recorded.get('mode') == 'docker' and CERT.is_file() and recorded.get('ca_fingerprint') == hashlib.sha256(CERT.read_bytes()).hexdigest()
    if pathlib.Path('/etc/corosync/qnetd/nssdb').exists() and not retained:
        raise SystemExit('An existing native witness requires an explicit migration; it will not be replaced')
    if not shutil.which('docker'):
        install_packages('witness-docker')
        subprocess.run(['systemctl', 'enable', '--now', 'docker'], check=True, capture_output=True, timeout=60)
    existing = container_state()
    if existing:
        if existing['Config'].get('Labels', {}).get('org.roxy-wi.recipe') != RECIPE:
            raise SystemExit('Existing witness image differs; plan an explicit image upgrade preserving its certificate data')
        command(['docker', 'start', CONTAINER])
    else:
        if pathlib.Path('/etc/corosync/qnetd/nssdb').exists() or subprocess.run(
                ['systemctl', 'is-active', '--quiet', 'corosync-qnetd'], capture_output=True).returncode == 0:
            raise SystemExit('An existing native witness requires an explicit migration; it will not be replaced')
        # Check before building or creating persistent state. Do not evict another listener.
        with socket.socket() as listener:
            listener.bind(('0.0.0.0', 5403))
        ROOT.mkdir(parents=True, mode=0o700, exist_ok=True)
        if DATA.exists():
            # Orphaned state may belong to a previous installation; never generate a new CA over it.
            raise SystemExit('Witness data exists without its managed container; inspect and recover it explicitly')
        image_id = build_image()
        DATA.mkdir(mode=0o700)
        os.chown(DATA, 65532, 65532)
        launch_docker(image_id)
    for _ in range(60):
        state = container_state()
        if state and docker_status(state)['active'] and CERT.is_file():
            return
        if state and not state['State'].get('Running'):
            break
        time.sleep(1)
    raise SystemExit('Container witness did not become ready; inspect its logs and persistent data')
'''
# Only these in-repository constants become executable input on the SSH host.
RECIPE = hashlib.sha256((DOCKERFILE + ENTRYPOINT).encode()).hexdigest()
RUNTIME = ('DOCKERFILE = ' + repr(DOCKERFILE) + '\nENTRYPOINT = ' + repr(ENTRYPOINT)
           + '\nRECIPE = ' + repr(RECIPE) + '\n' + RUNTIME)
