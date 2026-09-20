"""Privileged, stdin-only LE transport helper (also unit-testable without SSH).

Only fixed operations are exposed. JSON input/output travels over the existing
SSH connection; private keys never appear in command arguments or log messages.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import re
from contextlib import contextmanager


ROOT = Path('/var/lib/roxy-wi/letsencrypt')
LEGACY = Path('/etc/letsencrypt')
LEGACY_BACKUP = Path('/var/backups/roxy-wi-letsencrypt')


def command(argv, stage, timeout=180, **kwargs):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, **kwargs)
    if result.returncode:
        raise RuntimeError(stage + ' failed; check server configuration and permissions')
    return result.stdout


@contextmanager
def host_lock():
    import fcntl
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ROOT / '.lock').open('a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def certificate_directory(data):
    path = Path(data['cert_dir'])
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Certificate directory must be absolute')
    if data.get('docker'):
        mounts = json.loads(command(['docker', 'inspect', '--format', '{{json .Mounts}}',
                                     data['container']], 'Inspect HAProxy container'))
        matches = []
        for mount in mounts:
            destination = Path(mount['Destination'])
            source = Path(mount['Source'])
            if path == destination or destination in path.parents:
                matches.append((len(destination.parts), source / path.relative_to(destination)))
            elif path == source or source in path.parents:
                matches.append((len(source.parts), path))
        if not matches:
            raise RuntimeError('HAProxy certificate directory must have a persistent directory mount')
        path = max(matches, key=lambda item: item[0])[1]
    path.mkdir(parents=True, exist_ok=True, mode=0o750)
    return path


def service_commands(data):
    if data.get('docker'):
        args = command(['docker', 'exec', data['container'], 'cat', '/proc/1/cmdline'],
                       'Inspect HAProxy master process').decode().split('\x00')
        if not args or 'haproxy' not in Path(args[0]).name or not any(arg in ('-W', '-Ws') for arg in args):
            raise RuntimeError('Container PID 1 must run HAProxy with -W or -Ws for graceful certificate reload')
        config_path = Path(data['config_path'])
        mounts = json.loads(command(['docker', 'inspect', '--format', '{{json .Mounts}}',
                                     data['container']], 'Inspect HAProxy container'))
        for mount in sorted(mounts, key=lambda item: len(item['Source']), reverse=True):
            source = Path(mount['Source'])
            if config_path == source or source in config_path.parents:
                config_path = Path(mount['Destination']) / config_path.relative_to(source)
                break
        return (['docker', 'exec', data['container'], 'haproxy', '-c', '-f', str(config_path)],
                ['docker', 'kill', '--signal=USR2', data['container']])
    return (['haproxy', '-c', '-f', data['config_path']], ['systemctl', 'reload', 'haproxy'])


def private_file(path, data):
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def deploy(data):
    name = data['pem_name']
    if Path(name).name != name or not name.endswith('.pem'):
        raise ValueError('Invalid PEM name')
    directory = certificate_directory(data)
    target = directory / name
    if target.is_symlink():
        raise RuntimeError('Refusing to replace a certificate symlink')
    pem = data['pem'].encode('ascii')
    check, reload = service_commands(data)
    journal = ROOT / 'deployments' / hashlib.sha256(str(target).encode()).hexdigest()
    journal.mkdir(parents=True, exist_ok=True, mode=0o700)
    pending, previous, receipt = journal / 'pending.json', journal / 'previous.pem', journal / 'applied'

    def rollback():
        saved = json.loads(pending.read_text())
        if saved['had_old']:
            with tempfile.TemporaryDirectory(prefix='.roxywi-le-', dir=directory) as recovery:
                restored = Path(recovery) / 'certificate'
                shutil.copyfile(previous, restored)
                os.chmod(restored, saved['mode'])
                os.chown(restored, saved['uid'], saved['gid'])
                os.replace(restored, target)
        elif target.exists():
            target.unlink()
        command(check, 'Rollback configuration validation')
        command(reload, 'Rollback HAProxy reload')
        pending.unlink()
        if previous.exists():
            previous.unlink()

    if pending.exists():
        rollback()  # Recover a killed worker before accepting another PEM.
    digest = hashlib.sha256(pem).hexdigest()
    if receipt.exists() and target.exists() and receipt.read_text() == digest and target.read_bytes() == pem:
        command(check, 'HAProxy configuration validation')
        return {'deployed': True, 'sha256': digest}
    # Keep all intermediate files in a subdirectory, outside HAProxy's PEM scan.
    with tempfile.TemporaryDirectory(prefix='.roxywi-le-', dir=directory) as temporary:
        staged = Path(temporary) / 'certificate'
        staged.write_bytes(pem)
        os.chmod(staged, 0o600)
        had_old = target.exists()
        saved = {'had_old': had_old}
        if had_old:
            private_file(previous, target.read_bytes())
            info = target.stat()
            os.chown(staged, info.st_uid, info.st_gid)
            os.chmod(staged, info.st_mode & 0o640)
            saved.update(uid=info.st_uid, gid=info.st_gid, mode=info.st_mode & 0o640)
        private_file(pending, json.dumps(saved).encode())
        # A retry always reloads: the previous worker may have died after rename.
        os.replace(staged, target)
        try:
            command(check, 'HAProxy configuration validation')
            command(reload, 'HAProxy reload')
        except Exception:
            rollback()
            raise
        private_file(receipt, digest.encode())
        pending.unlink()
        if previous.exists():
            previous.unlink()
    return {'deployed': True, 'sha256': digest}


def issue(data):
    root = ROOT / str(int(data['le_id'])) / ('r' + str(int(data['revision'])))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = os.environ.copy()
    if data.get('proxy') and data['proxy'] != 'None':
        environment.update(http_proxy=data['proxy'], https_proxy=data['proxy'])
    if shutil.which('certbot') is None:
        if shutil.which('apt-get'):
            command(['apt-get', 'update'], 'Refresh Certbot package index', timeout=600, env=environment)
            command(['apt-get', 'install', '-y', 'certbot'], 'Install Certbot', timeout=600,
                    env={**environment, 'DEBIAN_FRONTEND': 'noninteractive'})
        elif shutil.which('dnf') or shutil.which('yum'):
            manager = shutil.which('dnf') or shutil.which('yum')
            command([manager, 'install', '-y', 'certbot'], 'Install Certbot (EPEL may be required)', timeout=600, env=environment)
        else:
            raise RuntimeError('Install Certbot on the standalone server')
    name = 'roxywi-' + str(int(data['le_id']))
    args = ['certbot', 'certonly', '--standalone', '--http-01-port', '8888',
            '--non-interactive', '--agree-tos', '--keep-until-expiring', '--email', data['email'],
            '--cert-name', name, '--config-dir', str(root / 'config'),
            '--work-dir', str(root / 'work'), '--logs-dir', str(root / 'logs')]
    for domain in data['domains']:
        args.extend(['-d', domain])
    if data.get('test'):
        args.append('--dry-run')
    command(args, 'Standalone ACME challenge (public port 80 must reach port 8888)', timeout=1200, env=environment)
    if data.get('test'):
        return {'tested': True}
    live = root / 'config' / 'live' / name
    return {'fullchain': (live / 'fullchain.pem').read_text(), 'key': (live / 'privkey.pem').read_text()}


def delete(data):
    target = ROOT / str(int(data['le_id']))
    if target.parent != ROOT or target.is_symlink() or int(data['le_id']) <= 0:
        raise ValueError('Invalid managed certificate directory')
    if target.exists():
        shutil.rmtree(target)
    # Deployed PEMs remain available to existing HAProxy configurations.
    return {'deleted': True}


def remove_legacy_entries(crontab):
    lines = crontab.splitlines(keepends=True)
    retained, removed, index = [], 0, 0
    marker = re.compile(r"^#Ansible: (?:Let's encrypt renew script|Roxy-WI certbot certificate renew|Roxy-WI le certificate .+)$")
    while index < len(lines):
        if marker.fullmatch(lines[index].strip()):
            if index + 1 == len(lines) or not re.match(r'^\s*(?:@|\d|\*)', lines[index + 1]):
                raise RuntimeError('Unexpected legacy LE cron entry; inspect it before migration')
            index += 2
            removed += 1
        else:
            retained.append(lines[index])
            index += 1
    return ''.join(retained), removed


def legacy_export(data):
    name = data['domain'][2:] if data['domain'].startswith('*.') else data['domain']
    if Path(name).name != name or name in ('.', '..'):
        raise ValueError('Invalid legacy certificate name')
    candidates = [name, *sorted(path.name for path in (LEGACY / 'live').glob(name + '-[0-9][0-9][0-9][0-9]'))]
    bundles = []
    for candidate in candidates:
        live = LEGACY / 'live' / candidate
        if not live.exists():
            continue
        bundles.append({'name': candidate, 'fullchain': (live / 'fullchain.pem').read_text(),
                        'key': (live / 'privkey.pem').read_text()})
    return {'bundles': bundles}


def read_crontab():
    result = subprocess.run(['crontab', '-u', 'root', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                            timeout=30, env={**os.environ, 'LC_ALL': 'C'})
    if result.returncode == 1 and 'no crontab for root' in result.stderr.lower():
        return ''
    if result.returncode:
        raise RuntimeError('Cannot read root crontab')
    return result.stdout


def legacy_disable(data):
    # Stop the owning daemon explicitly before cutover; never kill Certbot.
    for service in ('cron', 'crond'):
        check = subprocess.run(['systemctl', 'is-active', service], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if check.returncode == 0:
            raise RuntimeError('Stop cron/crond on this host before migrating LE')
    for timer in ('certbot.timer', 'certbot-renew.timer', 'snap.certbot.renew.timer'):
        check = subprocess.run(['systemctl', 'is-active', timer], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if check.returncode == 0:
            raise RuntimeError('Stop legacy Certbot timers on this host before migrating LE')
    processes = command(['ps', '-eo', 'args='], 'Check legacy LE processes').decode()
    for line in processes.splitlines():
        words = line.split()
        if any(Path(word).name in ('certbot', 'renew_letsencrypt.sh') for word in words[:3]):
            raise RuntimeError('Wait for the running legacy Certbot operation to finish')
        if words and Path(words[0]).name == 'rsync' and '/etc/letsencrypt/live/' in line:
            raise RuntimeError('Wait for the running legacy certificate transfer to finish')
    original = read_crontab()
    cleaned, removed = remove_legacy_entries(original)
    LEGACY_BACKUP.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(LEGACY_BACKUP, 0o700)
    snapshot = LEGACY_BACKUP / (hashlib.sha256(original.encode()).hexdigest() + '.crontab')
    if not snapshot.exists():
        with snapshot.open('x') as stream:
            stream.write(original)
        os.chmod(snapshot, 0o600)
    if read_crontab() != original:
        raise RuntimeError('Crontab changed during migration; retry')
    if removed:
        command(['crontab', '-u', 'root', '-'], 'Remove legacy LE cron', input=cleaned.encode())
    if remove_legacy_entries(read_crontab())[1]:
        raise RuntimeError('Legacy LE cron entries still exist')
    # Disable only these renewal lineages, including runs from certbot.timer.
    # Keep live/archive files in place for any existing consumers.
    for name in data['names']:
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('Invalid legacy certificate name')
        source = LEGACY / 'renewal' / (name + '.conf')
        if source.exists():
            content = source.read_bytes()
            dest = LEGACY_BACKUP / (name + '-' + hashlib.sha256(content).hexdigest() + '.conf')
            if not dest.exists():
                dest.write_bytes(content)
                os.chmod(dest, 0o600)
            source.unlink()
    return {'removed': removed}


def main():
    os.umask(0o077)
    try:
        data = json.load(sys.stdin)
        with host_lock():
            result = {'issue': issue, 'deploy': deploy, 'delete': delete,
                      'legacy-export': legacy_export, 'legacy-disable': legacy_disable}[data['operation']](data)
        print(json.dumps(result))
    except Exception as error:
        # Only our fixed messages are public. Never print subprocess output/input.
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(json.dumps({'error': detail}))
        sys.exit(1)


if __name__ == '__main__':
    main()
