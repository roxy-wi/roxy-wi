"""Privileged, stdin-only certificate transport helper (also unit-testable without SSH).

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
import ssl
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from contextlib import contextmanager

try:
    import roxywi_container_runtime as container_runtime
    import roxywi_config_candidate as config_candidate
    import roxywi_haproxy_runtime as haproxy_runtime
except ModuleNotFoundError:
    from app.modules.connectors import containers as container_runtime
    from app.modules.config import candidate as config_candidate
    from app.modules.service import haproxy_runtime

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


@contextmanager
def configuration_lock():
    import fcntl
    with open('/var/lock/roxywi-haproxy-config.lock', 'a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


class CertificateFailure(RuntimeError):
    def __init__(self, code):
        super().__init__('Certificate operation failed: ' + code)
        self.code = code


def validate_configuration(data, check=None, rollback=False):
    if data.get('validation'):
        result = config_candidate.execute(data['validation'])
        if result.get('status') != 'ok':
            raise CertificateFailure('validation_failed')
    else:
        command(check or service_commands(data)[0],
                'Rollback configuration validation' if rollback else 'HAProxy configuration validation')


def runtime_argv(data, arguments):
    return container_runtime.argv(data.get('container_runtime'), arguments)


def host_path(data, value):
    """Resolve a configured container path through the existing persistent mounts."""
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Certificate directory must be absolute')
    if data.get('docker'):
        mounts = json.loads(command(runtime_argv(data, ['inspect', '--format', '{{json .Mounts}}',
                                     data['container']]), 'Inspect HAProxy container'))
        matches = []
        for mount in mounts:
            destination = Path(mount['Destination'])
            source = Path(mount['Source'])
            if path == destination or destination in path.parents:
                if source.is_file():
                    raise CertificateFailure('destination_unavailable')
                matches.append((len(destination.parts), source / path.relative_to(destination)))
            elif path == source or source in path.parents:
                if source.is_file():
                    raise CertificateFailure('destination_unavailable')
                matches.append((len(source.parts), path))
        if not matches:
            raise RuntimeError('HAProxy certificate directory must have a persistent directory mount')
        path = max(matches, key=lambda item: item[0])[1]
    return path


def certificate_directory(data):
    path = host_path(data, data['cert_dir'])
    path.mkdir(parents=True, exist_ok=True, mode=0o750)
    return path


def service_commands(data):
    if data.get('docker'):
        args = command(runtime_argv(data, ['exec', data['container'], 'cat', '/proc/1/cmdline']),
                       'Inspect HAProxy master process').decode().split('\x00')
        if not args or 'haproxy' not in Path(args[0]).name or not any(arg in ('-W', '-Ws') for arg in args):
            raise RuntimeError('Container PID 1 must run HAProxy with -W or -Ws for graceful certificate reload')
        config_path = Path(data['config_path'])
        mounts = json.loads(command(runtime_argv(data, ['inspect', '--format', '{{json .Mounts}}',
                                     data['container']]), 'Inspect HAProxy container'))
        for mount in sorted(mounts, key=lambda item: len(item['Source']), reverse=True):
            source = Path(mount['Source'])
            if config_path == source or source in config_path.parents:
                config_path = Path(mount['Destination']) / config_path.relative_to(source)
                break
        return (runtime_argv(data, ['exec', data['container'], 'haproxy', '-c', '-f', str(config_path)]),
                runtime_argv(data, ['kill', '--signal=USR2', data['container']]))
    return (['haproxy', '-c', '-f', data['config_path']], ['systemctl', 'reload', 'haproxy'])


def runtime_endpoint(data):
    port = int(data['runtime_port'])
    if data.get('docker'):
        networks = json.loads(command(runtime_argv(data, ['inspect', '--format', '{{json .NetworkSettings}}',
                                      data['container']]), 'Inspect HAProxy runtime endpoint'))
        for network in networks.get('Networks', {}).values():
            if network.get('IPAddress'):
                return network['IPAddress'], port
    return '127.0.0.1', port


def runtime_request(data, request):
    command, separator, payload = request.partition(' <<\n')
    host, port = runtime_endpoint(data)
    if data.get('docker') and data.get('container_runtime', {}).get('owner','root') != 'root':
        return rootless_runtime_request(data, dict(server=host,port=port,command=command,timeout=3,
            response_limit=1024*1024,payload=payload if separator else None))
    return haproxy_runtime.execute_runtime_command(host, port, command, timeout=3, response_limit=1024 * 1024,
                                                  payload=payload if separator else None)


def rootless_runtime_request(data,request):
    """A rootless bridge is not reachable at its private IP from the host."""
    def state():
        return json.loads(command(runtime_argv(data,['inspect',data['container']]),'Inspect HAProxy runtime namespace'))[0]
    observed=state()
    ident=observed.get('Id',observed.get('ID',''))
    pid=int(observed.get('State',{}).get('Pid',0))
    if not re.fullmatch(r'[0-9a-f]{64}',ident) or not observed['State'].get('Running') or pid<=0:
        raise CertificateFailure('runtime_unavailable')
    # Confirm ownership before pinning a namespace: PID reuse must not deliver a
    # private certificate to an unrelated process's network namespace.
    if ident not in Path('/proc',str(pid),'cgroup').read_text():
        raise CertificateFailure('runtime_unavailable')
    descriptor=os.open('/proc/'+str(pid)+'/ns/net',os.O_RDONLY)
    try:
        current=state()
        if current.get('Id',current.get('ID'))!=ident or current.get('State',{}).get('Pid')!=pid or not current['State'].get('Running'):
            raise CertificateFailure('process_changed')
        source=getattr(haproxy_runtime,'__source__',None)
        if source is None:source=Path(haproxy_runtime.__file__).read_text()
        source+='\nimport json,sys\nprint(execute_runtime_command(**json.load(sys.stdin)),end="")\n'
        return command(['nsenter','--net=/proc/self/fd/'+str(descriptor),sys.executable,'-c',source],
            'HAProxy rootless runtime request',timeout=10,pass_fds=(descriptor,),input=json.dumps(request).encode()).decode()
    finally:
        os.close(descriptor)


def runtime_pid(data):
    response = runtime_request(data, 'show info')
    match = re.search(r'^Pid:\s*(\d+)\s*$', response, re.M)
    if not match:
        raise RuntimeError('HAProxy runtime API is unavailable; check the configured socket port')
    return match.group(1)


def certificate_runtime_path(data):
    path = Path(data['cert_dir']) / data['pem_name']
    if data.get('docker'):
        mounts = json.loads(command(runtime_argv(data, ['inspect', '--format', '{{json .Mounts}}',
                                    data['container']]), 'Inspect HAProxy certificate mount'))
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
    validate_configuration(data, check, rollback)
    previous_pid = runtime_pid(data)
    path = certificate_runtime_path(data)
    if any(char in path for char in '\r\n;'):
        raise ValueError('Invalid certificate runtime path')
    info = runtime_request(data, 'show ssl cert ' + path.replace('\\', '\\\\').replace(' ', '\\ '))
    require_loaded = 'Status: Used' in info and bool(pem)
    command(reload, 'Rollback HAProxy reload' if rollback else 'HAProxy reload')
    return verify_runtime(data, pem, previous_pid, require_loaded=require_loaded)


def private_file(path, data, metadata=None, *, replace=True):
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        if metadata:
            os.chmod(temporary, metadata['mode'])
            os.chown(temporary, metadata['uid'], metadata['gid'])
        if path.exists():
            # Atomic replacement must preserve the label assigned to the
            # directory-mounted file by Podman on SELinux hosts.
            for attribute in os.listxattr(path):
                try:
                    os.setxattr(temporary, attribute, os.getxattr(path, attribute))
                except OSError as error:
                    import errno
                    if Path('/sys/fs/selinux/enforce').exists() or error.errno not in (errno.ENOTSUP, errno.EINVAL, errno.EPERM):
                        raise
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)  # Atomic creation, without replacing another writer's file.
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
    data = creation_data(data)
    target, journal = deployment_journal(data)
    pending, previous, receipt = journal / 'pending.json', journal / 'previous.pem', journal / 'applied'
    if not pending.exists():
        return {'finished': True}
    saved = json.loads(pending.read_text())
    if saved.get('transaction') != data.get('transaction'):
        raise RuntimeError('Another certificate deployment owns the recovery journal')
    if saved.get('method') == 'runtime':
        return finish_runtime(data, target, journal, saved)
    if saved.get('method') == 'runtime_create':
        return finish_creation(data, target, journal, saved)
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
    if data.get('destination'):
        return deploy_creation(data)
    if data.get('apply_mode') in ('auto', 'runtime'):
        target, journal = deployment_journal(data)
        pending = journal / 'pending.json'
        saved = json.loads(pending.read_text()) if pending.exists() else {}
        if saved.get('method') == 'runtime' or data['apply_mode'] == 'runtime' or (
                not saved and runtime_certificate(data).get('fingerprint')):
            return deploy_runtime(data)
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
        validate_configuration(data, check)
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


def runtime_path(data):
    return runtime_argument(certificate_runtime_path(data))


def runtime_argument(path):
    if any(c in path for c in '\x00\r\n;'):
        raise CertificateFailure('invalid_path')
    return path.replace('\\', '\\\\').replace(' ', '\\ ')


def pem_fingerprint(pem):
    certificate = re.search(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', pem, re.S)
    if not certificate:
        return ''
    try:
        return hashlib.sha1(ssl.PEM_cert_to_DER_cert(certificate.group(0))).hexdigest().upper()
    except ValueError:
        return ''


def runtime_certificate(data, staged=False):
    response = runtime_request(data, 'show ssl cert ' + ('*' if staged else '') + runtime_path(data))
    return runtime_metadata(response)


def runtime_metadata(response):
    fields = dict(line.split(':', 1) for line in response.splitlines() if ':' in line)
    fields = {key: value.strip() for key, value in fields.items()}
    fingerprint = fields.get('SHA1 FingerPrint', '').replace(':', '').upper()
    if not re.fullmatch(r'[0-9A-F]{40}', fingerprint):
        fingerprint = ''
    domains = [re.sub(r'^DNS:', '', name.strip()) for name in fields.get('Subject Alternative Name', '').split(',')
               if name.strip()]
    if not domains:
        common_name = re.search(r'(?:^|/)CN=([^/]+)', fields.get('Subject', ''))
        domains = [common_name.group(1)] if common_name else []
    expiry = fields.get('notAfter', '')
    if expiry:
        try:
            expiry = parsedate_to_datetime(expiry).isoformat()
        except (ValueError, TypeError, OverflowError):
            expiry = ''  # Unsupported runtime metadata must not masquerade as a valid date.
    return dict(fingerprint=fingerprint, fingerprint_algorithm='SHA-1', domains=domains, not_after=expiry,
                used=fields.get('Status') == 'Used')


def runtime_transactions(data):
    response = runtime_request(data, 'show ssl cert')
    if not response.lstrip().startswith('#'):
        raise CertificateFailure('runtime_unavailable')
    return [line.strip()[1:] for line in response.splitlines() if line.startswith('*')]


def runtime_capabilities(data, *, create=False):
    runtime_pid(data)
    if runtime_request(data, 'show cli level').strip() != 'admin':
        raise CertificateFailure('runtime_permissions')
    help_text = runtime_request(data, 'help')
    commands = ['set ssl cert', 'commit ssl cert', 'abort ssl cert']
    if create:
        commands += ['new ssl cert', 'del ssl cert', 'add ssl crt-list', 'del ssl crt-list', 'show ssl crt-list']
    if any(command not in help_text for command in commands):
        raise CertificateFailure('runtime_unsupported')


def stage_certificate(data, pem):
    # Normalize PEM blocks: a blank line terminates the Runtime payload.
    payload = '\n'.join(line.strip() for line in pem.splitlines() if line.strip())
    response = runtime_request(data, 'set ssl cert ' + runtime_path(data) + ' <<\n' + payload + '\n')
    if (not re.search(r'^Transaction (?:created|updated) for certificate ', response, re.M)
            or runtime_certificate(data, staged=True)['fingerprint'] != pem_fingerprint(pem)):
        raise CertificateFailure('runtime_rejected')


def commit_certificate(data, fingerprint):
    try:
        runtime_request(data, 'commit ssl cert ' + runtime_path(data))
    except OSError:
        # A lost acknowledgement does not imply a failed commit.
        if runtime_certificate(data)['fingerprint'] != fingerprint:
            raise
    if (certificate_runtime_path(data) in runtime_transactions(data)
            or runtime_certificate(data)['fingerprint'] != fingerprint):
        raise CertificateFailure('verification_failed')


def restore_file(target, previous, saved):
    private_file(target, previous.read_bytes(), metadata=saved)


def finish_runtime(data, target, journal, saved):
    pending, previous, receipt = journal / 'pending.json', journal / 'previous.pem', journal / 'applied'
    if data['operation'] == 'rollback':
        if not target.is_file() or target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() not in (
                saved['old_digest'], saved['digest']):
            raise CertificateFailure('concurrent_change')
        active = runtime_certificate(data)['fingerprint']
        if active not in (saved['old_fingerprint'], saved['fingerprint']):
            raise CertificateFailure('recovery_failed')
        transactions = runtime_transactions(data)
        if transactions:
            if transactions != [certificate_runtime_path(data)] or runtime_certificate(data, True)['fingerprint'] not in (
                    saved['old_fingerprint'], saved['fingerprint']):
                raise CertificateFailure('transaction_busy')
            runtime_request(data, 'abort ssl cert ' + runtime_path(data))
            if runtime_transactions(data):
                raise CertificateFailure('recovery_failed')
        restore_file(target, previous, saved)
        validate_configuration(data, rollback=True)
        # The chain may change while the leaf fingerprint remains identical.
        stage_certificate(data, previous.read_text())
        commit_certificate(data, saved['old_fingerprint'])
        if runtime_certificate(data)['fingerprint'] != saved['old_fingerprint']:
            raise CertificateFailure('recovery_failed')
        if receipt.exists():
            receipt.unlink()
    elif (not target.is_file() or target.is_symlink()
          or hashlib.sha256(target.read_bytes()).hexdigest() != saved['digest']
          or runtime_certificate(data)['fingerprint'] != saved['fingerprint']):
        raise CertificateFailure('verification_failed')
    pending.unlink()
    previous.unlink(missing_ok=True)
    return {'finished': True}


def deploy_runtime(data):
    if data.get('update_directory'):
        path = str(Path(data['update_directory']) / data['pem_name'])
        if path not in runtime_certificate_paths(data):
            raise CertificateFailure('destination_unavailable')
        data = creation_data(data)
    target, journal = deployment_journal(data)
    pending, previous, receipt = journal / 'pending.json', journal / 'previous.pem', journal / 'applied'
    pem = data['pem']
    digest = hashlib.sha256(pem.encode('ascii')).hexdigest()
    fingerprint = pem_fingerprint(pem)
    if not fingerprint or len(pem) > 1024 * 1024:
        raise CertificateFailure('invalid_pem')
    if not target.is_file() or target.is_symlink():
        raise CertificateFailure('invalid_path')
    runtime_capabilities(data)
    original = target.read_bytes()
    actual = hashlib.sha256(original).hexdigest()
    saved = json.loads(pending.read_text()) if pending.exists() else None
    if saved:
        if saved.get('transaction') != data.get('transaction') or saved.get('digest') != digest:
            raise CertificateFailure('transaction_busy')
        if actual not in (saved['old_digest'], digest):
            raise CertificateFailure('concurrent_change')
    else:
        active = runtime_certificate(data)['fingerprint']
        if receipt.exists() and receipt.read_text() == digest and actual == digest and active == fingerprint:
            validate_configuration(data)
            return {'deployed': True, 'sha256': digest, 'verification': 'runtime'}
        if data.get('expected_revision') and data['expected_revision'] != actual:
            raise CertificateFailure('concurrent_change')
        if not active:
            raise CertificateFailure('not_loaded')
        if active != pem_fingerprint(original.decode('ascii')):
            raise CertificateFailure('disk_mismatch')
        if runtime_transactions(data):
            raise CertificateFailure('transaction_busy')
        validate_configuration(data)
        info = target.stat()
        saved = dict(method='runtime', transaction=data.get('transaction'), digest=digest, fingerprint=fingerprint,
                     old_digest=actual, old_fingerprint=active, mode=info.st_mode & 0o640,
                     uid=info.st_uid, gid=info.st_gid)
        private_file(previous, original)
        private_file(pending, json.dumps(saved).encode())
    try:
        active = runtime_certificate(data)['fingerprint']
        if active not in (saved['old_fingerprint'], fingerprint):
            raise CertificateFailure('concurrent_change')
        pid = runtime_pid(data)
        transactions = runtime_transactions(data)
        if transactions and (transactions != [certificate_runtime_path(data)] or
                             runtime_certificate(data, True)['fingerprint'] != fingerprint):
            raise CertificateFailure('transaction_busy')
        already_committed = saved.get('committed') and actual == digest and active == fingerprint
        if not already_committed and not transactions:
            stage_certificate(data, pem)
        if actual != digest:
            private_file(target, pem.encode('ascii'), metadata=saved)
        validate_configuration(data)
        if runtime_pid(data) != pid:
            raise CertificateFailure('process_changed')
        if not already_committed:
            commit_certificate(data, fingerprint)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest or runtime_certificate(data)['fingerprint'] != fingerprint:
            raise CertificateFailure('verification_failed')
        private_file(receipt, digest.encode())
        saved['committed'] = True
        private_file(pending, json.dumps(saved).encode())
    except Exception:
        try:
            finish_runtime(dict(data, operation='rollback'), target, journal, saved)
        except Exception:
            raise CertificateFailure('recovery_failed') from None
        raise
    if not data.get('transaction'):
        finish_runtime(dict(data, operation='commit'), target, journal, saved)
    return {'deployed': True, 'sha256': digest, 'verification': 'runtime'}


def creation_data(data):
    destination = data.get('destination')
    if destination and destination['kind'] == 'directory':
        return dict(data, cert_dir=destination['path'])
    if data.get('update_directory'):
        return dict(data, cert_dir=data['update_directory'])
    return data


def certificate_destinations(data):
    response = runtime_request(data, 'show ssl crt-list')
    destinations = []
    for value in response.splitlines():
        if not value or value.startswith('#'):
            continue
        if not Path(value).is_absolute():
            # Relative startup paths cannot be resolved safely without HAProxy's cwd.
            continue
        runtime_argument(value)
        path = host_path(data, value)
        if path.is_symlink():
            continue
        if path.is_dir() or path.is_file():
            destinations.append(dict(path=value, kind='directory' if path.is_dir() else 'crt_list'))
    return destinations


def crt_entries(data, destination):
    response = runtime_request(data, 'show ssl crt-list ' + runtime_argument(destination))
    if not response.startswith('#'):
        raise CertificateFailure('destination_unavailable')
    # Runtime prints paths verbatim, even when they contain spaces. Match loaded
    # filenames before parsing optional SSL parameters/SNI filters after them.
    certificates = runtime_request(data, 'show ssl cert')
    if not certificates.startswith('#'):
        raise CertificateFailure('runtime_unavailable')
    paths = sorted((p for p in certificates.splitlines() if p and not p.startswith(('#', '*'))), key=len, reverse=True)
    entries = []
    for line in response.splitlines():
        if not line or line.startswith('#'):
            continue
        path = next((path for path in paths if line == path or line.startswith(path + ' ')), None)
        if path:
            entries.append(path)
    return entries


def crt_list_content(original, path):
    # Unlike haproxy.cfg, crt-list's file parser does not support quoted paths.
    if any(c.isspace() or c == '#' for c in path):
        raise CertificateFailure('crt_list_path_unsupported')
    return original + (b'\n' if original and not original.endswith(b'\n') else b'') + path.encode() + b'\n'


def creation_preflight(data):
    data = creation_data(data)
    runtime_capabilities(data, create=True)
    destination = data['destination']
    if destination not in certificate_destinations(data):
        raise CertificateFailure('destination_unavailable')
    target, journal = deployment_journal(data)
    pending = journal / 'pending.json'
    if pending.exists():
        saved = json.loads(pending.read_text())
        if saved.get('transaction') != data.get('transaction') or saved.get('destination') != destination:
            raise CertificateFailure('transaction_busy')
        return {'checked': True}
    for other in (ROOT / 'deployments').glob('*/pending.json'):
        if json.loads(other.read_text()).get('destination') == destination:
            raise CertificateFailure('transaction_busy')
    if target.exists() or target.is_symlink():
        raise CertificateFailure('certificate_exists')
    response = runtime_request(data, 'show ssl cert')
    if not response.startswith('#'):
        raise CertificateFailure('runtime_unavailable')
    if certificate_runtime_path(data) in response.splitlines():
        raise CertificateFailure('certificate_exists')
    if runtime_transactions(data):
        raise CertificateFailure('transaction_busy')
    if certificate_runtime_path(data) in crt_entries(data, destination['path']):
        raise CertificateFailure('certificate_exists')
    if destination['kind'] == 'crt_list':
        crt_list_content(b'', certificate_runtime_path(data))
        source = host_path(data, destination['path'])
        if source.stat().st_size > 1024 * 1024:
            raise CertificateFailure('destination_unavailable')
        # Refuse even an unloaded disk entry; adding it twice changes SNI selection.
        for line in source.read_text().splitlines():
            tokens = line.split('#', 1)[0].split()
            if tokens and tokens[0] == certificate_runtime_path(data):
                raise CertificateFailure('certificate_exists')
    validate_configuration(data)
    return {'checked': True}


def creation_disk_state(data, target, journal, saved, *, rollback=False, complete=True):
    """Restore/verify only files still matching this operation's recorded contents."""
    if target.is_symlink() or (target.exists() and
            hashlib.sha256(target.read_bytes()).hexdigest() != saved['digest']):
        raise CertificateFailure('concurrent_change')
    source = None
    if saved['destination']['kind'] == 'crt_list':
        source = host_path(data, saved['destination']['path'])
        if (source.is_symlink() or not source.is_file() or
                hashlib.sha256(source.read_bytes()).hexdigest() not in (saved['list_before'], saved['list_after'])):
            raise CertificateFailure('concurrent_change')
    if rollback:
        if source:
            private_file(source, (journal / 'previous.crt-list').read_bytes(), metadata=saved['list_metadata'])
        target.unlink(missing_ok=True)
    elif complete and (not target.is_file() or (source and hashlib.sha256(source.read_bytes()).hexdigest() != saved['list_after'])):
        raise CertificateFailure('verification_failed')


def finish_creation(data, target, journal, saved):
    path, destination = certificate_runtime_path(data), saved['destination']['path']
    info = runtime_certificate(data)
    if info['fingerprint'] not in ('', saved['fingerprint']):
        raise CertificateFailure('concurrent_change')
    entries = crt_entries(data, destination)
    if data['operation'] == 'rollback':
        # Inspect disk ownership before changing Runtime as well.
        creation_disk_state(data, target, journal, saved, complete=False)
        if path in entries:
            runtime_request(data, 'del ssl crt-list ' + runtime_argument(destination) + ' ' + runtime_path(data))
            if path in crt_entries(data, destination):
                raise CertificateFailure('recovery_failed')
        transactions = runtime_transactions(data)
        if path in transactions:
            if runtime_certificate(data, True)['fingerprint'] not in ('', saved['fingerprint']):
                raise CertificateFailure('transaction_busy')
            runtime_request(data, 'abort ssl cert ' + runtime_path(data))
        response = runtime_request(data, 'show ssl cert')
        if path in response.splitlines():
            runtime_request(data, 'del ssl cert ' + runtime_path(data))
        if path in runtime_request(data, 'show ssl cert').splitlines() or path in runtime_transactions(data):
            raise CertificateFailure('recovery_failed')
        creation_disk_state(data, target, journal, saved, rollback=True)
        validate_configuration(data, rollback=True)
        (journal / 'applied').unlink(missing_ok=True)
    else:
        creation_disk_state(data, target, journal, saved)
        if path not in entries or info['fingerprint'] != saved['fingerprint'] or not info['used']:
            raise CertificateFailure('verification_failed')
    (journal / 'pending.json').unlink()
    (journal / 'previous.crt-list').unlink(missing_ok=True)
    return {'finished': True}


def deploy_creation(data):
    data = creation_data(data)
    target, journal = deployment_journal(data)
    pending, receipt = journal / 'pending.json', journal / 'applied'
    pem = data['pem']
    digest, fingerprint = hashlib.sha256(pem.encode('ascii')).hexdigest(), pem_fingerprint(pem)
    if not fingerprint or len(pem) > 1024 * 1024:
        raise CertificateFailure('invalid_pem')
    creation_preflight(data)
    if pending.exists():
        saved = json.loads(pending.read_text())
        if saved.get('method') != 'runtime_create' or saved['digest'] != digest:
            raise CertificateFailure('transaction_busy')
    else:
        saved = dict(method='runtime_create', transaction=data.get('transaction'), digest=digest,
                     fingerprint=fingerprint, destination=data['destination'])
        if data['destination']['kind'] == 'crt_list':
            source = host_path(data, data['destination']['path'])
            original = source.read_bytes()
            updated = crt_list_content(original, certificate_runtime_path(data))
            info = source.stat()
            saved.update(list_before=hashlib.sha256(original).hexdigest(), list_after=hashlib.sha256(updated).hexdigest(),
                         list_metadata=dict(uid=info.st_uid, gid=info.st_gid, mode=info.st_mode & 0o777))
            private_file(journal / 'previous.crt-list', original)
        private_file(pending, json.dumps(saved).encode())
    try:
        pid = runtime_pid(data)
        path = certificate_runtime_path(data)
        if not target.exists():
            private_file(target, pem.encode('ascii'), replace=False)
        elif target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise CertificateFailure('concurrent_change')
        if data['destination']['kind'] == 'crt_list':
            source = host_path(data, data['destination']['path'])
            current = hashlib.sha256(source.read_bytes()).hexdigest()
            if source.is_symlink() or current not in (saved['list_before'], saved['list_after']):
                raise CertificateFailure('concurrent_change')
            if current == saved['list_before']:
                original = (journal / 'previous.crt-list').read_bytes()
                updated = crt_list_content(original, path)
                private_file(source, updated, metadata=saved['list_metadata'])
        validate_configuration(data)
        if runtime_pid(data) != pid:
            raise CertificateFailure('process_changed')
        response = runtime_request(data, 'show ssl cert')
        if path not in response.splitlines():
            runtime_request(data, 'new ssl cert ' + runtime_path(data))
            if path not in runtime_request(data, 'show ssl cert').splitlines():
                raise CertificateFailure('runtime_rejected')
        info = runtime_certificate(data)
        if info['fingerprint'] not in ('', fingerprint):
            raise CertificateFailure('concurrent_change')
        if runtime_transactions(data) and (runtime_transactions(data) != [path] or
                runtime_certificate(data, True)['fingerprint'] != fingerprint):
            raise CertificateFailure('transaction_busy')
        if not info['fingerprint'] or runtime_transactions(data):
            stage_certificate(data, pem)
            commit_certificate(data, fingerprint)
        destination = data['destination']['path']
        if path not in crt_entries(data, destination):
            runtime_request(data, 'add ssl crt-list ' + runtime_argument(destination) + ' ' + runtime_path(data))
        if (path not in crt_entries(data, destination) or not runtime_certificate(data)['used'] or runtime_pid(data) != pid):
            raise CertificateFailure('verification_failed')
        creation_disk_state(data, target, journal, saved)
        private_file(receipt, digest.encode())
    except Exception:
        try:
            finish_creation(dict(data, operation='rollback'), target, journal, saved)
        except Exception:
            raise CertificateFailure('recovery_failed') from None
        raise
    if not data.get('transaction'):
        finish_creation(dict(data, operation='commit'), target, journal, saved)
    return {'deployed': True, 'sha256': digest, 'verification': 'runtime'}


def store_file(data):
    name, content = data['pem_name'], data['pem']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.(pem|crt|key)', name):
        raise CertificateFailure('invalid_path')
    if not isinstance(content, str) or not content or len(content.encode('utf-8')) > 1024 * 1024:
        raise CertificateFailure('invalid_pem')
    target = certificate_directory(data) / name
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise CertificateFailure('invalid_path')
    journal = ROOT / 'deployments' / hashlib.sha256(str(target).encode()).hexdigest()
    if (journal / 'pending.json').exists():
        raise CertificateFailure('transaction_busy')
    metadata = None
    if target.exists():
        info = target.stat()
        metadata = dict(mode=info.st_mode & 0o640, uid=info.st_uid, gid=info.st_gid)
    private_file(target, content.encode('utf-8'), metadata=metadata)
    return {'stored': True}


def runtime_certificate_paths(data):
    response = runtime_request(data, 'show ssl cert')
    if not response.lstrip().startswith('#'):
        raise CertificateFailure('runtime_unsupported')
    return [line.strip() for line in response.splitlines() if line and not line.startswith(('#', '*'))]


def catalog(data):
    directory = certificate_directory(data)
    error, paths, writable = None, [], False
    if data.get('runtime', True):
        try:
            paths = runtime_certificate_paths(data)
            runtime_capabilities(data)
            writable = True
        except (OSError, RuntimeError, ValueError) as exc:
            error = getattr(exc, 'code', 'runtime_unavailable')
    destinations, create_error = [], error
    if data.get('runtime', True) and not error:
        try:
            runtime_capabilities(data, create=True)
            destinations = certificate_destinations(data)
        except (OSError, RuntimeError, ValueError) as exc:
            create_error = getattr(exc, 'code', 'runtime_unavailable')
    files = {certificate_runtime_path(dict(data, pem_name=file.name)): file for file in directory.iterdir()
             if file.suffix.lower() in ('.pem', '.crt', '.key') and file.is_file() and not file.is_symlink()}
    uploaded_paths = set(files)
    for destination in destinations:
        if destination['kind'] != 'directory':
            continue
        for file in host_path(data, destination['path']).iterdir():
            if file.suffix == '.pem' and file.is_file() and not file.is_symlink():
                files[str(Path(destination['path']) / file.name)] = file
    managed_paths = set(files)
    unavailable_paths = set()
    for path in set(paths) - managed_paths:
        try:
            file = host_path(data, path)
        except (ValueError, RuntimeError):
            # A runtime certificate can live outside the container's persistent mounts.
            unavailable_paths.add(path)
            continue
        if file.is_symlink():
            unavailable_paths.add(path)
        elif file.is_file():
            files[path] = file
    result = []
    for path in sorted(set(files) | set(paths)):
        file = files.get(path)
        item = dict(name=Path(path).name, path=path, runtime_status='unknown' if error and not paths else 'not_loaded',
                    disk_status='unknown' if path in unavailable_paths else 'missing',
                    can_update=False, can_view=bool(file), can_delete=False,
                    revision='', domains=[], not_after='', fingerprint='')
        leaf_fingerprint = ''
        if file and path not in uploaded_paths:
            item['directory'] = str(Path(path).parent)
        if file:
            if file.stat().st_size > 1024 * 1024:
                item['disk_status'] = 'invalid'
                item['can_view'] = False
            else:
                content = file.read_bytes()
                leaf = re.search(rb'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', content, re.S)
                item.update(certificate=leaf.group(0).decode('ascii') if leaf else '',
                            revision=hashlib.sha256(content).hexdigest(), disk_status='stored')
                leaf_fingerprint = pem_fingerprint(item['certificate'])
        if path in paths:
            info_data = dict(data, cert_dir=str(Path(path).parent), pem_name=Path(path).name, docker=False)
            # The endpoint still belongs to the configured container.
            try:
                info = runtime_metadata(runtime_request(data, 'show ssl cert ' + runtime_path(info_data)))
            except (OSError, RuntimeError):
                error = 'runtime_unavailable'
                item['runtime_status'] = 'unknown'
                result.append(item)
                continue
            active = info['fingerprint']
            item['runtime'] = info
            item['runtime_status'] = ('used' if info['used'] else 'loaded') if active else 'unknown'
            if file:
                item['disk_status'] = 'matches' if active and active == leaf_fingerprint else 'differs'
            item['can_update'] = (writable and bool(file) and item['disk_status'] == 'matches'
                                  and file.suffix == '.pem')
        result.append(item)
    if error:
        for item in result:
            item['can_update'] = False
    for item in result:
        item['can_delete'] = item['can_view'] and item['path'] not in paths and not error
        item['delete_error'] = error or ('certificate_in_use' if item['path'] in paths else 'invalid_path')
        item['update_error'] = error or ('disk_mismatch' if item['disk_status'] == 'differs' else
                                        'not_loaded_error' if item['path'] not in paths else 'invalid_path')
    return {'certificates': result, 'runtime_error': error, 'destinations': destinations,
            'create_error': create_error, 'can_create': bool(destinations) and not create_error}


def catalog_file(data):
    """Resolve only files already exposed by the service catalog, under the shared lock."""
    item = next((item for item in catalog(data)['certificates'] if item['path'] == data['path']), None)
    if not item or not item['can_view']:
        raise CertificateFailure('invalid_path')
    target = host_path(data, item['path'])
    if target.is_symlink() or not target.is_file() or target.stat().st_size > 1024 * 1024:
        raise CertificateFailure('invalid_path')
    return target, item


def read_file(data):
    target, _item = catalog_file(data)
    content = target.read_text(encoding='ascii')
    if target.suffix.lower() != '.key':
        # Viewing a certificate does not disclose its bundled private key.
        content = '\n'.join(re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', content, re.S))
    return {'content': content}


def remove_file(data):
    target, item = catalog_file(data)
    if not item['can_delete']:
        raise CertificateFailure(item['delete_error'])
    if hashlib.sha256(target.read_bytes()).hexdigest() != data['revision']:
        raise CertificateFailure('concurrent_change')
    journal = None
    if target.suffix == '.pem':
        _target, journal = deployment_journal(dict(data, docker=False, cert_dir=str(target.parent), pem_name=target.name))
    if journal and (journal / 'pending.json').exists():
        raise CertificateFailure('transaction_busy')
    # Retain the original inode until validation of the complete HAProxy configuration succeeds.
    descriptor, temporary = tempfile.mkstemp(prefix='.roxywi-remove-', dir=target.parent)
    os.close(descriptor)
    backup = Path(temporary)
    os.replace(target, backup)
    try:
        if data.get('runtime', True):
            validate_configuration(data)
    except Exception:
        # Link without replacement; retain the backup if an external writer recreated the path.
        try:
            os.link(backup, target)
        except FileExistsError:
            raise CertificateFailure('recovery_failed') from None
        backup.unlink()
        raise
    backup.unlink()
    return {'deleted': True}


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
        handlers = {'issue': issue, 'deploy': deploy, 'delete': delete, 'catalog': catalog, 'store': store_file,
                    'check-new': creation_preflight, 'read-file': read_file, 'remove-file': remove_file,
                    'rollback': finish_deployment, 'commit': finish_deployment, 'preflight': preflight,
                    'legacy-export': legacy_export, 'legacy-disable': legacy_disable}
        # ACME challenges may take minutes; they must not block certificate listing.
        lock = configuration_lock if data['operation'] in ('deploy', 'rollback', 'commit', 'preflight', 'catalog', 'store', 'check-new', 'read-file', 'remove-file') else host_lock
        with lock():
            result = handlers[data['operation']](data)
        print(json.dumps(result))
    except Exception as error:
        # Only our fixed messages are public. Never print subprocess output/input.
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(json.dumps({'error': detail, 'code': getattr(error, 'code', 'remote_failed'),
                          'retry_at': getattr(error, 'retry_at', None)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
