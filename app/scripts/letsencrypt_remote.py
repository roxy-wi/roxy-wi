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
import socket
import ssl
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from contextlib import contextmanager


ROOT = Path('/var/lib/roxy-wi/letsencrypt')
LEGACY = Path('/etc/letsencrypt')
LEGACY_BACKUP = Path('/var/backups/roxy-wi-letsencrypt')


class AcmeFailure(RuntimeError):
    def __init__(self, message, code='acme_failed', retry_at=None):
        super().__init__(message)
        self.code, self.retry_at = code, retry_at


def diagnose_acme(output):
    """Classify CLI failures without returning provider output or credentials."""
    if isinstance(output, bytes):
        output = output.decode('utf-8', errors='replace')
    lowered = output.lower()
    if any(value in lowered for value in ('ratelimited', 'rate limit', 'too many', 'retry-after', 'retry after')):
        now = datetime.now(timezone.utc)
        retry_at = now + timedelta(days=1)
        match = re.search(r'retry[- ]after[:\s]+(\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:Z|\+00:00| UTC)?)', output, re.I)
        if match:
            try:
                retry_at = datetime.strptime(match.group(1)[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            except ValueError:
                pass  # A malformed provider date retains the conservative delay.
        else:
            match = re.search(r'retry-after[\s\x27\x22:]+([^\r\n]+)', output, re.I)
            if match:
                value = match.group(1).strip().strip('\x27\x22,')
                try:
                    retry_at = now + timedelta(seconds=int(value)) if value.isdigit() else parsedate_to_datetime(value)
                except (ValueError, TypeError, OverflowError):
                    pass  # Unknown provider date: retain the conservative one-day delay.
        retry_at = max(now + timedelta(minutes=1), retry_at.astimezone(timezone.utc))
        return AcmeFailure('ACME rate limit reached; retry after ' + retry_at.isoformat(), 'rate_limited', retry_at.isoformat())
    for patterns, code, message in (
        (('caa',), 'caa_denied', 'CAA policy does not authorize this certificate; check domain CAA records'),
        (('invalid api', 'authentication error', 'invalid token', 'invalidclienttokenid', 'accessdenied', 'unauthorized to'),
         'dns_credentials', 'DNS provider rejected the credentials or their permissions'),
        (('nxdomain', 'no txt record', 'incorrect txt', 'dns problem', 'propagation'),
         'dns_validation', 'DNS challenge record could not be validated; check the zone and propagation time'),
        (('connection refused', 'timeout during connect', 'fetching http', 'invalid response from http'),
         'http_validation', 'HTTP challenge is unreachable or returns the wrong response; check port 80 and HA routing'),
        (('plugin does not appear', 'unrecognized arguments', 'no module named'),
         'plugin_missing', 'Required Certbot plugin is unavailable or incompatible'),
    ):
        if any(value in lowered for value in patterns):
            return AcmeFailure(message, code)
    return AcmeFailure('ACME validation failed; run the staging setup check for domain and server diagnostics')


def command(argv, stage, timeout=180, **kwargs):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, **kwargs)
    if result.returncode:
        if 'ACME challenge' in stage:
            raise diagnose_acme(result.stderr + result.stdout)
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


def runtime_endpoint(data):
    port = int(data['runtime_port'])
    if data.get('docker'):
        networks = json.loads(command(['docker', 'inspect', '--format', '{{json .NetworkSettings}}',
                                      data['container']], 'Inspect HAProxy runtime endpoint'))
        for network in networks.get('Networks', {}).values():
            if network.get('IPAddress'):
                return network['IPAddress'], port
    return '127.0.0.1', port


def runtime_request(data, request):
    with socket.create_connection(runtime_endpoint(data), timeout=3) as stream:
        stream.settimeout(3)
        stream.sendall((request + '\n').encode())
        stream.shutdown(socket.SHUT_WR)
        output = bytearray()
        while len(output) < 1024 * 1024:
            chunk = stream.recv(65536)
            if not chunk:
                return output.decode('utf-8', errors='replace')
            output.extend(chunk)
    raise RuntimeError('HAProxy runtime response exceeds the allowed size')


def runtime_pid(data):
    response = runtime_request(data, 'show info')
    match = re.search(r'^Pid:\s*(\d+)\s*$', response, re.M)
    if not match:
        raise RuntimeError('HAProxy runtime API is unavailable; check the configured socket port')
    return match.group(1)


def certificate_runtime_path(data):
    path = Path(data['cert_dir']) / data['pem_name']
    if data.get('docker'):
        mounts = json.loads(command(['docker', 'inspect', '--format', '{{json .Mounts}}',
                                    data['container']], 'Inspect HAProxy certificate mount'))
        for mount in sorted(mounts, key=lambda item: len(item['Source']), reverse=True):
            source = Path(mount['Source'])
            if path == source or source in path.parents:
                path = Path(mount['Destination']) / path.relative_to(source)
                break
    return str(path)


def verify_runtime(data, pem, previous_pid=None, timeout=30, require_loaded=False):
    if not data.get('runtime_port'):
        raise RuntimeError('HAProxy runtime port is required to verify certificate deployment')
    certificate = re.search(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', pem, re.S)
    expected = hashlib.sha1(ssl.PEM_cert_to_DER_cert(certificate.group(0))).hexdigest().upper() if certificate else None
    path = certificate_runtime_path(data)
    if any(char in path for char in '\r\n;'):
        raise ValueError('Invalid certificate runtime path')
    path = path.replace('\\', '\\\\').replace(' ', '\\ ')
    deadline = time.monotonic() + timeout
    while True:
        try:
            pid = runtime_pid(data)
            if previous_pid is None or pid != previous_pid:
                response = runtime_request(data, 'show ssl cert ' + path)
                fingerprint = re.search(r'^SHA1 FingerPrint:\s*([0-9A-Fa-f:]+)', response, re.M)
                if fingerprint and expected and fingerprint.group(1).replace(':', '').upper() == expected:
                    return 'loaded'
                # A new certificate may intentionally be stored before configuring its bind.
                if not require_loaded and ('Can\'t display the certificate' in response or 'Certificate not found' in response):
                    return 'stored_unreferenced'
        except (OSError, RuntimeError):
            pass  # A short runtime socket interruption is expected during reload.
        if time.monotonic() >= deadline:
            raise RuntimeError('HAProxy reload was not confirmed by its runtime API; certificate deployment was rejected')
        time.sleep(0.25)


def reload_verified(data, pem, check, reload, rollback=False):
    command(check, 'Rollback configuration validation' if rollback else 'HAProxy configuration validation')
    previous_pid = runtime_pid(data)
    path = certificate_runtime_path(data)
    if any(char in path for char in '\r\n;'):
        raise ValueError('Invalid certificate runtime path')
    info = runtime_request(data, 'show ssl cert ' + path.replace('\\', '\\\\').replace(' ', '\\ '))
    require_loaded = 'Status: Used' in info and bool(pem)
    command(reload, 'Rollback HAProxy reload' if rollback else 'HAProxy reload')
    return verify_runtime(data, pem, previous_pid, require_loaded=require_loaded)


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


def deployment_journal(data):
    target = certificate_directory(data) / data['pem_name']
    if Path(data['pem_name']).name != data['pem_name'] or not data['pem_name'].endswith('.pem'):
        raise ValueError('Invalid PEM name')
    journal = ROOT / 'deployments' / hashlib.sha256(str(target).encode()).hexdigest()
    journal.mkdir(parents=True, exist_ok=True, mode=0o700)
    return target, journal


def finish_deployment(data):
    target, journal = deployment_journal(data)
    pending, previous, receipt = journal / 'pending.json', journal / 'previous.pem', journal / 'applied'
    if not pending.exists():
        return {'finished': True}
    saved = json.loads(pending.read_text())
    if saved.get('transaction') != data.get('transaction'):
        raise RuntimeError('Another certificate deployment owns the recovery journal')
    if data['operation'] == 'rollback':
        if saved['had_old']:
            with tempfile.TemporaryDirectory(prefix='.roxywi-le-', dir=target.parent) as directory:
                temporary = Path(directory) / 'certificate'
                shutil.copyfile(previous, temporary)
                os.chmod(temporary, saved['mode'])
                os.chown(temporary, saved['uid'], saved['gid'])
                os.replace(temporary, target)
        elif target.exists():
            target.unlink()
        check, reload = service_commands(data)
        rollback_pem = target.read_text() if target.exists() else ''
        reload_verified(data, rollback_pem, check, reload, rollback=True)
        if receipt.exists():
            receipt.unlink()
    pending.unlink()
    if previous.exists():
        previous.unlink()
    return {'finished': True}


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
    _, journal = deployment_journal(data)
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
        rollback_pem = target.read_text() if target.exists() else ''
        reload_verified(data, rollback_pem, check, reload, rollback=True)
        pending.unlink()
        if previous.exists():
            previous.unlink()

    digest = hashlib.sha256(pem).hexdigest()
    if pending.exists():
        saved = json.loads(pending.read_text())
        if saved.get('transaction'):
            if saved['transaction'] != data.get('transaction'):
                raise RuntimeError('Finish the previous certificate deployment before replacing this PEM')
            # Repeat validation/reload after a lost SSH response or killed worker.
            if target.exists() and target.read_bytes() == pem:
                verification = reload_verified(data, data['pem'], check, reload)
                private_file(receipt, digest.encode())
                return {'deployed': True, 'sha256': digest, 'verification': verification}
        rollback()  # Recover a killed worker before accepting another PEM.
    if receipt.exists() and target.exists() and receipt.read_text() == digest and target.read_bytes() == pem:
        command(check, 'HAProxy configuration validation')
        verification = verify_runtime(data, data['pem'])
        return {'deployed': True, 'sha256': digest, 'verification': verification}
    runtime_pid(data)  # Refuse to change files if we cannot verify the reload.
    # Keep all intermediate files in a subdirectory, outside HAProxy's PEM scan.
    with tempfile.TemporaryDirectory(prefix='.roxywi-le-', dir=directory) as temporary:
        staged = Path(temporary) / 'certificate'
        staged.write_bytes(pem)
        os.chmod(staged, 0o600)
        had_old = target.exists()
        saved = {'had_old': had_old, 'transaction': data.get('transaction')}
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
            verification = reload_verified(data, data['pem'], check, reload)
        except Exception:
            rollback()
            raise
        private_file(receipt, digest.encode())
        if not data.get('transaction'):
            pending.unlink()
            if previous.exists():
                previous.unlink()
    return {'deployed': True, 'sha256': digest, 'verification': verification}


def issue(data):
    root = ROOT / str(int(data['le_id'])) / ('r' + str(int(data['revision'])))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    accounts = ROOT / 'accounts' / str(int(data['group_id']))
    copy_accounts(accounts, root / 'config' / 'accounts')
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
    try:
        command(args, 'Standalone ACME challenge (public port 80 must reach port 8888)', timeout=1200, env=environment)
    finally:
        copy_accounts(root / 'config' / 'accounts', accounts)
    if data.get('test'):
        return {'tested': True}
    live = root / 'config' / 'live' / name
    return {'fullchain': (live / 'fullchain.pem').read_text(), 'key': (live / 'privkey.pem').read_text()}


def copy_accounts(source, destination):
    """Reuse one account per CA, preserving existing lineages' account identity.

    The caller holds the group/host lock. Never merge multiple accounts for the
    same CA into a fresh config-dir: noninteractive Certbot cannot choose one.
    """
    for registration in sorted(source.glob('**/regr.json')):
        if any(part.startswith('.') for part in registration.relative_to(source).parts):
            continue
        account = registration.parent
        ca = destination / account.parent.relative_to(source)
        if list(ca.glob('*/regr.json')):
            continue
        ca.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = ca / account.name
        with tempfile.TemporaryDirectory(prefix='.account-', dir=ca) as temporary:
            staged = Path(temporary) / account.name
            shutil.copytree(account, staged)
            for path in staged.rglob('*'):
                os.chmod(path, 0o700 if path.is_dir() else 0o600)
            os.chmod(staged, 0o700)
            os.replace(staged, target)


def delete(data):
    target = ROOT / str(int(data['le_id']))
    if target.parent != ROOT or target.is_symlink() or int(data['le_id']) <= 0:
        raise ValueError('Invalid managed certificate directory')
    if target.exists():
        shutil.rmtree(target)
    # Deployed PEMs remain available to existing HAProxy configurations.
    return {'deleted': True}


def preflight(data):
    directory = certificate_directory(data)
    with tempfile.TemporaryDirectory(prefix='.roxywi-check-', dir=directory) as temporary:
        private_file(Path(temporary) / 'write-check', b'check')
    check, _reload = service_commands(data)
    command(check, 'HAProxy configuration validation')
    runtime_pid(data)
    if data.get('standalone'):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('0.0.0.0', 8888))
    return {'checked': True}


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
                      'rollback': finish_deployment, 'commit': finish_deployment, 'preflight': preflight,
                      'legacy-export': legacy_export, 'legacy-disable': legacy_disable}[data['operation']](data)
        print(json.dumps(result))
    except Exception as error:
        # Only our fixed messages are public. Never print subprocess output/input.
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(json.dumps({'error': detail, 'code': getattr(error, 'code', 'remote_failed'),
                          'retry_at': getattr(error, 'retry_at', None)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
