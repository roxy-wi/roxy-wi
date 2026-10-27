"""Shared target detection and package installation for cluster roles.

The source is sent over SSH; it uses only the target's Python standard library.
Distribution profiles describe an implementation, not a claim of live qualification.
"""

SOURCE = r'''
import os, pathlib, re, shlex, shutil, subprocess, sys
def platform_profile():
    if sys.version_info < (3, 8):
        raise SystemExit('Cluster management requires Python 3.8 or newer as python3 on the target host')
    values = {}
    for line in pathlib.Path('/etc/os-release').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            parts = shlex.split(value)
            values[key] = parts[0] if parts else ''
    distro = values.get('ID', '')
    major = int(values.get('VERSION_ID', '0').split('.')[0])
    if distro == 'debian' and major >= 11:
        family, manager = 'debian', 'apt-get'
    elif distro == 'ubuntu' and major >= 20:
        family, manager = 'ubuntu', 'apt-get'
    elif (distro in ('rhel', 'rocky', 'almalinux', 'centos', 'ol') or 'rhel' in values.get('ID_LIKE', '').split()) and major in (8, 9):
        family, manager = 'el', 'dnf'
    else:
        raise SystemExit('No automatic installation profile for this OS; use adoption after manual cluster installation')
    if not shutil.which(manager) or not pathlib.Path('/run/systemd/system').is_dir():
        raise SystemExit('Automatic cluster installation requires a systemd host and its native package manager')
    if pathlib.Path('/.dockerenv').exists() or pathlib.Path('/run/.containerenv').exists():
        raise SystemExit('Cluster daemons must run on the host; container workloads can be managed as resources')
    return {'id': distro, 'version': values.get('VERSION_ID'), 'family': family, 'manager': manager,
            'qualified': (distro == 'debian' and major == 13) or (distro == 'rocky' and values.get('VERSION_ID') == '9.8')}

def install_packages(role, *, fence_pve=False):
    profile = platform_profile()
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive')
    packages = {'cluster': ['corosync', 'pacemaker', 'resource-agents', 'python3'],
                'witness': ['corosync-qnetd'], 'qdevice': ['corosync-qdevice'],
                'witness-docker': ['docker.io'] if profile['manager'] == 'apt-get' else ['docker-ce', 'docker-ce-cli', 'containerd.io']}[role]
    if fence_pve:
        if role != 'cluster':
            raise SystemExit('Fencing agents belong on cluster nodes only')
        packages.append('fence-agents-pve')
    if profile['manager'] == 'apt-get':
        subprocess.run(['apt-get', '-o', 'DPkg::Lock::Timeout=60', 'update', '-qq'], check=True, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        if role == 'witness-docker':
            split = subprocess.run(['apt-cache', 'show', 'docker-cli'], capture_output=True)
            if split.returncode == 0 and split.stdout:
                packages.append('docker-cli')
        if role == 'cluster':
            packages.append('pacemaker-cli-utils')
            if fence_pve:
                split = subprocess.run(['apt-cache', 'show', 'fence-agents-pve'], capture_output=True)
                if split.returncode != 0 or not split.stdout:
                    packages.remove('fence-agents-pve')
                    packages.append('fence-agents')
            if profile['family'] == 'ubuntu':
                split = subprocess.run(['apt-cache', 'show', 'resource-agents-base'], capture_output=True)
                if split.returncode == 0 and split.stdout:
                    packages.remove('resource-agents')
                    packages += ['resource-agents-base', 'resource-agents-extra']
        command = ['apt-get', '-o', 'DPkg::Lock::Timeout=60', 'install', '-y', '--no-install-recommends']
    else:
        command = ['dnf', '-y', 'install']
    subprocess.run(command + packages, check=True, env=env, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=240)
    return profile

def repair_fence_pve():
    import hashlib, stat, tempfile, xml.etree.ElementTree as ET
    agent = pathlib.Path('/usr/sbin/fence_pve')
    if not agent.is_file():
        raise SystemExit('Requested fence_pve agent is not installed')
    original = agent.read_text()
    placeholder = 'sys.path.append("@FENCEAGENTSLIBDIR@")'
    repaired = False
    if '@FENCEAGENTSLIBDIR@' in original:
        library = pathlib.Path('/usr/share/fence/fencing.py')
        if original.count(placeholder) != 1 or original.count('@FENCEAGENTSLIBDIR@') != 1 or not library.is_file():
            raise SystemExit('Unknown fence_pve packaging defect; inspect the installed agent')
        fixed = original.replace(placeholder, 'sys.path.append("/usr/share/fence")')
        compile(fixed, str(agent), 'exec')
        backup_root = pathlib.Path('/var/lib/roxy-wi/fence-agents')
        backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        backup = backup_root / ('fence_pve.' + hashlib.sha256(original.encode()).hexdigest() + '.orig')
        if not backup.exists():
            with backup.open('x') as saved:
                saved.write(original)
            backup.chmod(0o600)
        mode = agent.stat()
        stage = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=agent.parent, prefix='.roxywi-fence-pve-', delete=False) as stream:
                stage = pathlib.Path(stream.name)
                stream.write(fixed)
                stream.flush()
                os.fsync(stream.fileno())
            stage.chmod(stat.S_IMODE(mode.st_mode))
            os.chown(stage, mode.st_uid, mode.st_gid)
            os.replace(stage, agent)
            if shutil.which('restorecon'):
                subprocess.run(['restorecon', str(agent)], check=True, capture_output=True, timeout=15)
        finally:
            if stage is not None:
                stage.unlink(missing_ok=True)
        repaired = True
    metadata = subprocess.run([str(agent), '--action', 'metadata'], check=True,
                              capture_output=True, text=True, timeout=30)
    root = ET.fromstring(metadata.stdout)
    if root.tag != 'resource-agent' or root.get('name') != 'fence_pve':
        raise SystemExit('fence_pve did not return valid agent metadata')
    return repaired

def enable_syn_flood_protection():
    # Tune TCP only. Strict reverse-path filtering can break asymmetric HA routing.
    current = int(pathlib.Path('/proc/sys/net/ipv4/tcp_max_syn_backlog').read_text())
    values = {'net.ipv4.tcp_syncookies': 1, 'net.ipv4.tcp_synack_retries': 3,
              'net.ipv4.tcp_max_syn_backlog': max(current, 4096)}
    path = pathlib.Path('/etc/sysctl.d/90-roxywi-syn-flood.conf')
    text = '# Managed by Roxy-WI: optional TCP SYN protection\n' + ''.join('%s = %s\n' % item for item in values.items())
    stage = path.with_suffix('.tmp')
    stage.write_text(text)
    stage.chmod(0o644)
    os.replace(stage, path)
    for key, value in values.items():
        subprocess.run(['sysctl', '-w', '%s=%s' % (key, value)], check=True, capture_output=True, timeout=10)
'''

DETECT = SOURCE + '''
import json
try:
    print(json.dumps(dict(platform_profile(), supported=True)))
except SystemExit as exc:
    print(json.dumps({'supported': False, 'reason': str(exc)}))
'''
