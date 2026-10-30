"""Shared target detection and package installation for cluster roles.

The source is sent over SSH; it uses only the target's Python standard library.
Distribution profiles describe an implementation, not a claim of live qualification.
"""

SOURCE = r'''
import json, os, pathlib, re, shlex, shutil, subprocess, sys

def installation_message(message, level='info'):
    if globals().get('INSTALL_LOG', False):
        print('ROXYWI_INSTALL_LOG ' + json.dumps({'message': message, 'level': level}), flush=True)

def installation_command(command, *, timeout=90, env=None):
    installation_message('Running: ' + shlex.join(command))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                env=env or dict(os.environ, LC_ALL='C'))
    except subprocess.TimeoutExpired as exc:
        output = ''.join(part.decode('utf-8', errors='replace') if isinstance(part, bytes) else part
                         for part in (exc.stdout or '', exc.stderr or ''))
        installation_message(output[-16000:], 'error')
        raise SystemExit('Command timed out after %s seconds' % timeout)
    output = (result.stdout or '') + (result.stderr or '')
    if output.strip():
        installation_message(output[-16000:], 'error' if result.returncode else 'info')
    if result.returncode:
        raise SystemExit('Command failed (exit %s); check the installation output above' % result.returncode)
    return result

def role_packages(profile, role, fence_pve=False):
    packages = {'cluster': ['corosync', 'pacemaker', 'resource-agents', 'python3'],
                'witness': ['corosync-qnetd'], 'witness-podman': ['podman', 'nftables'], 'qdevice': ['corosync-qdevice'],
                'witness-docker': ['docker.io'] if profile['manager'] == 'apt-get' else ['docker-ce', 'docker-ce-cli', 'containerd.io']}[role]
    if fence_pve:
        if role != 'cluster':
            raise SystemExit('Fencing agents belong on cluster nodes only')
        packages.append('fence-agents-pve')
    return packages

def package_repositories(profile, role, packages):
    if profile['manager'] != 'dnf':
        return []
    result = installation_command(['dnf', '-q', 'repolist', '--all'])
    repositories = []
    if role in ('cluster', 'witness', 'qdevice'):
        for line in result.stdout.splitlines():
            columns = line.split()
            repo = columns[0] if columns else ''
            if (repo.lower() in ('highavailability', 'crb', 'powertools')
                    or re.fullmatch(r'rhel-[89]-for-[a-z0-9_]+-highavailability-rpms', repo)
                    or re.fullmatch(r'ol[89]_(addons|codeready_builder)', repo)):
                repositories.append(repo)
    options = ['--enablerepo=' + repo for repo in sorted(set(repositories))]
    if repositories:
        installation_message('Using configured repositories for this installation: ' + ', '.join(sorted(set(repositories))))
    result = installation_command(['dnf', '-q', *options, 'repoquery', '--queryformat', '%{name}', *packages], timeout=120)
    available = set(result.stdout.splitlines())
    missing = sorted(set(packages) - available)
    if missing:
        raise SystemExit('Packages unavailable: ' + ', '.join(missing)
                         + '. Configure the OS High Availability repositories and entitlement, then retry.')
    installation_message('All required packages are available')
    return options

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
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', LC_ALL='C')
    packages = role_packages(profile, role, fence_pve)
    if profile['manager'] == 'apt-get':
        installation_command(['apt-get', '-o', 'DPkg::Lock::Timeout=60', 'update', '-qq'], env=env)
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
        command = ['dnf', '-y', *package_repositories(profile, role, packages), 'install']
    installation_command(command + packages, env=env, timeout=240)
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
