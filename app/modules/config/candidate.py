"""Shared configuration transaction, also executed standalone on managed hosts.

Only validators know how each service loads a candidate. File replacement,
recovery, command execution and the result contract belong to this module.
"""
import getopt
import io
import tarfile
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from uuid import uuid4


try:
    import roxywi_container_runtime as container_runtime
except ModuleNotFoundError:
    if __package__:
        from app.modules.connectors import containers as container_runtime
    else:
        # Direct CLI execution must not import the Flask application. Remote
        # framed execution supplies roxywi_container_runtime above instead.
        import importlib.util
        runtime_path = Path(__file__).resolve().parents[1] / 'connectors' / 'containers.py'
        runtime_spec = importlib.util.spec_from_file_location('roxywi_container_runtime', runtime_path)
        container_runtime = importlib.util.module_from_spec(runtime_spec)
        runtime_spec.loader.exec_module(container_runtime)


ERROR_CODES = {'validation_failed', 'apply_failed', 'recovery_failed', 'mount_failed', 'save_failed'}
# Allow lock acquisition, Docker staging, validation, apply and recovery to finish.
REMOTE_TIMEOUT = 360

# SPOP 2.0 HELLO health check. This small program also runs in a Docker network
# namespace with the host Python; the container needs no Python installation.
# Protocol: https://github.com/haproxy/haproxy/blob/master/doc/SPOE.txt
SPOA_HEALTHCHECK = r'''
import socket
import sys

def buffer(value):
    return bytes([len(value)]) + value

def receive(connection, size):
    data = b''
    while len(data) < size:
        part = connection.recv(size - len(data))
        if not part:
            raise ValueError('Incomplete frame')
        data += part
    return data

try:
    hello = (b'\x01\x00\x00\x00\x01\x00\x00'
             + buffer(b'supported-versions') + b'\x08' + buffer(b'2.0')
             + buffer(b'max-frame-size') + b'\x03\x80'
             + buffer(b'capabilities') + b'\x08\x00'
             + buffer(b'healthcheck') + b'\x11')
    with socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=2) as connection:
        connection.sendall(len(hello).to_bytes(4, 'big') + hello)
        size = int.from_bytes(receive(connection, 4), 'big')
        if not 7 < size <= 128:
            raise ValueError('Invalid frame size')
        data = receive(connection, size)
    if data[:7] != b'\x65\x00\x00\x00\x01\x00\x00':
        raise ValueError('Expected AGENT-HELLO')
    values, offset = {}, 7
    while offset < len(data):
        length = data[offset]
        key = data[offset + 1:offset + 1 + length]
        offset += 1 + length
        kind = data[offset]
        offset += 1
        if kind == 3 and data[offset] < 240:
            value = data[offset]
            offset += 1
        elif kind == 8 and data[offset] < 240:
            length = data[offset]
            value = data[offset + 1:offset + 1 + length]
            offset += 1 + length
        else:
            raise ValueError('Unexpected value type')
        if offset > len(data) or key in values:
            raise ValueError('Invalid HELLO values')
        values[key] = value
    if (values.get(b'version') != b'2.0' or not isinstance(values.get(b'max-frame-size'), int)
            or not size <= values[b'max-frame-size'] <= 128
            or not isinstance(values.get(b'capabilities'), bytes)):
        raise ValueError('Incompatible agent')
except (OSError, ValueError, IndexError):
    sys.exit(1)
'''


class CandidateApplyError(RuntimeError):
    def __init__(self, result: dict):
        self.code = result['code']
        self.reason = result.get('reason', '')
        self.cause = result.get('cause', '')
        super().__init__(json.dumps(result))


class _ConfigurationError(ValueError):
    """A controlled diagnostic that contains neither rule text nor command output."""


def check_result(output: str) -> None:
    result = json.loads(output)
    if result == {'status': 'ok'}:
        return
    if isinstance(result, dict) and result.get('status') == 'failed' and result.get('code') in ERROR_CODES:
        raise CandidateApplyError(result)
    raise RuntimeError('Unconfirmed configuration transaction result')


def remote_source():
    return globals()['container_runtime'].embedded() + Path(__file__).read_text(encoding='utf-8')


def candidate_command(service: str, target: str, candidate: str, action: str, *, main: str,
                      root: str = '', sources=(), container: str = '', action_command: str = '', service_unit: str = '',
                      apply_only: bool = False, expected_sha256: str = '', container_runtime=None, lock_root='') -> str:
    if service not in ('haproxy', 'nginx', 'apache', 'keepalived', 'nginx_waf', 'haproxy_waf') or action not in ('test', 'check', 'save', 'reload', 'restart', 'status'):
        raise ValueError('Unsupported configuration transaction')
    if action == 'status' and (not service.endswith('_waf') or candidate or action_command or apply_only):
        raise ValueError('Unsupported WAF status operation')
    if service == 'haproxy_waf' and action not in ('save', 'restart', 'status'):
        raise ValueError('HAProxy WAF supports save and restart only')
    if apply_only and (not service.endswith('_waf') or action not in ('reload', 'restart') or candidate):
        raise ValueError('Unsupported WAF apply operation')
    if service in ('nginx', 'apache', 'keepalived') or service.endswith('_waf'):
        if service not in ('nginx', 'apache', 'keepalived'):
            root = str(PurePosixPath(target).parent if apply_only or action == 'status' else PurePosixPath(target).parent.parent)
        elif not PurePosixPath(root).is_absolute():
            raise ValueError('NGINX WAF directory must be absolute')
        if lock_root and not PurePosixPath(lock_root).is_absolute():
            raise ValueError('Configuration lock directory must be absolute')
        lock_id = hashlib.sha256((lock_root or root).encode('utf-8')).hexdigest()
        lock = f'/var/lock/roxywi-waf-{lock_id}.lock'
    else:
        lock = '/var/lock/roxywi-haproxy-config.lock'
    spec = dict(service=service, target=target, candidate=candidate, action=action, main=main,
                root=root, sources=list(sources), container=container, action_command=action_command, service_unit=service_unit)
    if container_runtime is not None:
        spec['container_runtime'] = globals()['container_runtime'].validate(container_runtime)
    if apply_only:
        spec['apply_only'] = True
    if expected_sha256:
        spec['expected_sha256'] = expected_sha256
    script = remote_source()
    return shlex.join(['sudo', '-n', 'flock', '-w', '30', lock, 'python3', '-c', script, json.dumps(spec)])


def _run(arguments: list, *, timeout=30, separate_errors=False, input_data=None) -> subprocess.CompletedProcess:
    # Native diagnostics can contain configuration secrets; only metadata crosses SSH.
    return subprocess.run(arguments, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE if separate_errors else subprocess.STDOUT, timeout=timeout, check=False,
                          **({'input':input_data} if input_data is not None else {'stdin':subprocess.DEVNULL}))


def service_process(container, unit, *, runtime=None):
    """Return the service manager's state and its main PID, never a grep count."""
    name = container or unit
    if not name or name.startswith('-'):
        raise _ConfigurationError('A service or container name is required')
    if container:
        result = _run(container_runtime.argv(runtime, ['inspect', '--format', '{{json .State}}', container]), timeout=5)
        if result.returncode:
            return 'unknown', 0
        state = json.loads(result.stdout)
        pid = int(state['Pid'])
        if state.get('Running') and not state.get('Restarting') and not state.get('Paused') and pid > 0:
            return 'running', pid
        return 'stopped', 0
    result = _run(['systemctl', 'show', unit, '--property=MainPID', '--property=ActiveState', '--property=SubState'], timeout=5)
    if result.returncode:
        return 'unknown', 0
    state = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
    if not {'MainPID', 'ActiveState', 'SubState'}.issubset(state):
        return 'unknown', 0
    pid = int(state['MainPID'])
    if state['ActiveState'] == 'active' and state['SubState'] == 'running' and pid > 0:
        return 'running', pid
    return 'stopped', 0


def _regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise _ConfigurationError('Expected a regular file')


def _unlink(path: Path) -> None:
    # Managed hosts may use Python 3.6, before Path.unlink(missing_ok=...).
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _contents(path: Path):
    if path.is_symlink():
        raise _ConfigurationError('Configuration changed to a symlink')
    if not path.exists():
        return None
    _regular(path)
    return path.read_bytes()


def _copy(source: Path, destination: Path) -> None:
    shutil.copy2(source, destination)
    if os.name == 'posix':
        metadata = source.stat()
        os.chown(destination, metadata.st_uid, metadata.st_gid)


def _install(source: Path, target: Path, expected, metadata: Path = None) -> None:
    fd, name = tempfile.mkstemp(prefix='.roxywi-config-', dir=target.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        if metadata is not None:
            _copy(metadata, temporary)
        else:
            temporary.chmod(0o644)
        with temporary.open('wb') as stream:
            stream.write(source.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        if _contents(target) != expected:
            raise _ConfigurationError('Configuration changed during the transaction')
        os.replace(temporary, target)
    finally:
        _unlink(temporary)


def _container_path(path: Path, mounts: list, *, directory=False, writable=False, aliases=False, bind_only=False) -> str:
    matches = []
    for mount in mounts:
        source = Path(mount.get('Source', ''))
        if not source.is_absolute():
            continue
        try:
            relative = path.resolve().relative_to(source.resolve())
        except ValueError:
            continue
        matches.append((len(source.resolve().parts), mount, source, relative))
    if not matches:
        raise _ConfigurationError('Configuration path is not mounted in the container')
    longest = max(item[0] for item in matches)
    matches = [item for item in matches if item[0] == longest]
    if len(matches) > 1 and not aliases:
        raise _ConfigurationError('Configuration path has ambiguous container mounts')
    # HAProxy can read any alias. Prefer the writable one, as in its existing deployment role.
    _, mount, source, relative = max(matches, key=lambda item: bool(item[1].get('RW')))
    destination = PurePosixPath(mount.get('Destination', ''))
    if (not destination.is_absolute() or (directory and not source.is_dir())
            or (writable and not mount.get('RW')) or (bind_only and mount.get('Type') != 'bind')):
        raise _ConfigurationError('Mount the configuration directory with the required access before saving')
    runtime = destination.joinpath(*relative.parts)
    for other in mounts:
        other_destination = PurePosixPath(other.get('Destination', ''))
        if other is mount or not other_destination.is_absolute():
            continue
        try:
            runtime.relative_to(other_destination)
        except ValueError:
            continue
        if len(other_destination.parts) >= len(destination.parts):
            raise _ConfigurationError('Another container mount hides the selected configuration path')
    return str(runtime)


class _Validator:
    validate_before_install = True
    can_validate = True

    def __init__(self, spec, target, main):
        self.spec, self.target, self.main = spec, target, main
        self.container = spec.get('container', '')
        self.runtime = container_runtime.validate(spec.get('container_runtime'))
        self.mounts = []

    def runtime_argv(self, arguments):
        return container_runtime.argv(self.runtime, arguments)

    def inspect(self):
        if self.container:
            result = _run(self.runtime_argv(['inspect', '--format', '{{json .Mounts}}', self.container]), timeout=10)
            if result.returncode:
                raise _ConfigurationError('Cannot inspect container mounts')
            self.mounts = json.loads(result.stdout)

    def close(self):
        return

    def apply(self):
        if _run(['sh', '-c', self.spec['action_command']]).returncode:
            raise _ConfigurationError('Service action failed')


class _WafValidator(_Validator):
    validate_before_install = False

    def inspect(self):
        super().inspect()
        self.runtime_main = str(self.main)
        if self.container:
            _container_path(self.target, self.mounts, directory=True, bind_only=True)
            self.runtime_main = _container_path(self.main, self.mounts, bind_only=True)


class _KeepalivedValidator(_WafValidator):
    def inspect(self):
        super().inspect()
        self.command = (self.runtime_argv(['exec', self.container]) if self.container else []) + ['keepalived', '-t', '-f', self.runtime_main]

    def validate(self, staged=None):
        return _run(self.command).returncode == 0


class _ApacheValidator(_WafValidator):
    def inspect(self):
        _Validator.inspect(self)
        self.runtime_main = str(self.main)
        if self.container:
            _container_path(self.target, self.mounts, directory=True, bind_only=True, aliases=True)
            self.runtime_main = _container_path(self.main, self.mounts, bind_only=True, aliases=True)
        self.command = (self.runtime_argv(['exec', self.container]) if self.container else []) + ['apachectl', '-t', '-f', self.runtime_main]

    def validate(self, staged=None):
        return _run(self.command).returncode == 0


class _NginxValidator(_WafValidator):
    def inspect(self):
        super().inspect()
        self.command = (self.runtime_argv(['exec', self.container]) if self.container else []) + ['nginx', '-t', '-c', self.runtime_main]

    def validate(self, staged=None):
        return _run(self.command).returncode == 0

    def module_state(self):
        command = self.command.copy()
        command[-3] = '-T'
        result = _run(command, separate_errors=True)
        if result.returncode:
            return 'invalid', 'unknown'
        # Parse directives only; comments, quoted values and inactive files must
        # not be mistaken for an enabled module. Never return configuration text.
        dump = result.stdout.decode('utf-8')
        if not re.search(r'^# configuration file .+:$', dump, re.MULTILINE):
            raise _ConfigurationError('NGINX did not return its configuration dump')
        lexer = shlex.shlex(dump, posix=True, punctuation_chars=';{}')
        lexer.whitespace_split = True
        statement, states = [], set()
        for token in lexer:
            if token and all(char in ';{}' for char in token):
                if token.startswith(';') and len(statement) == 2 and statement[0] == 'modsecurity':
                    states.add(statement[1])
                statement = []
            else:
                statement.append(token)
        if not states:
            return 'valid', 'not_configured'
        if not states.issubset({'on', 'off'}):
            return 'valid', 'unknown'
        return 'valid', 'mixed' if len(states) > 1 else ('enabled' if 'on' in states else 'disabled')


class _HaproxyWafValidator(_WafValidator):
    # Upstream spoa-modsecurity has no syntax-check mode. Only a successful
    # restart followed by its HELLO response confirms that it loaded the rules.
    can_validate = False

    def inspect(self):
        super().inspect()
        entrypoint = self.target if self.spec.get('apply_only') or self.spec['action'] == 'status' else self.target.parent.parent / 'modsecurity.conf'
        if self.main != entrypoint:
            raise _ConfigurationError('Unexpected ModSecurity entrypoint')
        self.unit = self.spec.get('service_unit', '')
        if self.spec['action'] == 'restart':
            if self.container:
                if not shutil.which('nsenter'):
                    raise _ConfigurationError('Install util-linux on the Docker host to check WAF readiness')
            else:
                if not self.unit or self.unit.startswith('-'):
                    raise _ConfigurationError('WAF systemd service name is required')
                result = _run(['systemctl', 'show', self.unit, '--property=LoadState', '--value'], timeout=5)
                if result.returncode or result.stdout.strip() != b'loaded':
                    raise _ConfigurationError('WAF systemd service is not loaded')
            pid = self.process_id()
            if pid:
                self.listener_port(pid)  # Reject mismatched startup paths before replacing the rule.

    def process_id(self):
        return service_process(self.container, self.unit, **({'runtime':self.runtime} if self.spec.get('container_runtime') else {}))[1]

    def listener_port(self, pid):
        try:
            arguments = [os.fsdecode(value) for value in (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0') if value]
        except (FileNotFoundError, ProcessLookupError):
            return None
        if not arguments:
            return None  # Exiting processes can have an empty cmdline.
        try:
            options, remaining = getopt.getopt(arguments[1:], 'hdm:n:p:c:t:f:')
            options = dict(options)
        except getopt.GetoptError as exc:
            raise _ConfigurationError('Unsupported WAF agent startup arguments') from exc
        if remaining or PurePosixPath(options.get('-f', '')) != PurePosixPath(self.runtime_main):
            raise _ConfigurationError('Start the WAF agent directly with -f pointing to the configured modsecurity.conf')
        port = int(options.get('-p', 12345))
        if not 0 < port < 65536:
            raise _ConfigurationError('Invalid WAF listener port')
        return port

    def ready(self, pid):
        process = Path('/proc') / str(pid)
        port = self.listener_port(pid)
        if port is None:
            return False
        try:
            sockets = set()
            for descriptor in (process / 'fd').iterdir():
                try:
                    sockets.add(os.readlink(descriptor))
                except FileNotFoundError:
                    continue  # A descriptor can close while the process is starting.
            listening = any(len(fields) > 9 and fields[3] == '0A' and int(fields[1].split(':')[1], 16) == port
                            and 'socket:[' + fields[9] + ']' in sockets
                            for fields in (line.split() for line in (process / 'net/tcp').read_text().splitlines()[1:]))
            if not listening:
                return False
        except (FileNotFoundError, ProcessLookupError):
            return False  # The service can exit between the status and /proc reads.
        command = [sys.executable, '-c', SPOA_HEALTHCHECK, str(port)]
        if self.container:
            command = ['nsenter', '--target', str(pid), '--net', *command]
        try:
            return _run(command, timeout=3).returncode == 0
        except subprocess.TimeoutExpired:
            return False  # A bounded readiness loop reports failure to the transaction.

    def apply(self):
        previous_pid = self.process_id()
        super().apply()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            pid = self.process_id()
            if pid > 0 and pid != previous_pid and self.ready(pid) and self.process_id() == pid:
                return
            time.sleep(0.2)
        raise _ConfigurationError('The restarted WAF agent did not become ready')


class _HaproxyValidator(_Validator):
    def __init__(self, *args):
        super().__init__(*args)
        self.copied = False
        self.container_candidate = '/roxywi-' + uuid4().hex + '.cfg'

    def inspect(self):
        super().inspect()
        if self.container and self.spec['action'] not in ('test', 'check'):
            _container_path(self.target, self.mounts, directory=True, writable=True, aliases=True)

    def files(self, candidate):
        files = []
        for source in self.spec['sources']:
            source = Path(source)
            if not source.is_absolute():
                raise _ConfigurationError('Configuration sources must be absolute paths')
            if source.is_dir():
                entries = {path for path in source.glob('*.cfg') if path.is_file() and not path.name.startswith('.')}
                if candidate and self.target.parent.resolve() == source.resolve() and not self.target.name.startswith('.'):
                    entries.add(source / self.target.name)
                files.extend(sorted(entries, key=lambda path: os.fsencode(str(path))))
            else:
                files.append(source)
        canonical = [path.resolve() for path in files]
        if len(set(canonical)) != len(canonical):
            raise _ConfigurationError('Overlapping -f sources load the same file more than once')
        if candidate and canonical.count(self.target) != 1:
            raise _ConfigurationError('Selected file is not included in HAProxy startup sources; configure startup with -f')
        return canonical

    def validate(self, staged=None):
        files = self.files(staged is not None)
        if staged is not None and self.container and not self.copied:
            # /tmp may be a read-only bind mount. Use a unique path at the container root.
            self.copied = True
            if self.runtime['owner'] == 'root':
                copied = _run(self.runtime_argv(['cp', str(staged), self.container + ':' + self.container_candidate]))
            else:
                # The rootless CLI cannot read a root-owned staging directory.
                # Send only this file over stdin; never relax host permissions.
                stream = io.BytesIO()
                with tarfile.open(fileobj=stream, mode='w') as archive:
                    metadata = tarfile.TarInfo(self.container_candidate.lstrip('/'))
                    content = staged.read_bytes()
                    metadata.size, metadata.mode = len(content), 0o600
                    archive.addfile(metadata, io.BytesIO(content))
                copied = _run(self.runtime_argv(['cp', '-', self.container + ':/']), input_data=stream.getvalue())
            if copied.returncode:
                raise _ConfigurationError('Cannot stage the container candidate')
            uid = _run(self.runtime_argv(['exec', self.container, 'id', '-u']), timeout=10)
            gid = _run(self.runtime_argv(['exec', self.container, 'id', '-g']), timeout=10)
            if uid.returncode or gid.returncode:
                raise _ConfigurationError('Cannot determine the container user')
            owner = uid.stdout.decode().strip() + ':' + gid.stdout.decode().strip()
            if not re.fullmatch(r'[0-9]+:[0-9]+', owner):
                raise _ConfigurationError('Invalid container user identity')
            if _run(self.runtime_argv(['exec', '-u', '0', self.container, 'chown', owner, self.container_candidate]), timeout=10).returncode:
                raise _ConfigurationError('Cannot set container candidate ownership')
        arguments = []
        for path in files:
            if staged is not None and path == self.target:
                value = self.container_candidate if self.container else str(staged)
            elif self.container:
                value = _container_path(path, self.mounts, aliases=True)
            else:
                value = str(path)
            arguments.extend(['-f', value])
        command = (self.runtime_argv(['exec', self.container]) if self.container else []) + ['haproxy', '-c', *arguments]
        return _run(command).returncode == 0

    def close(self):
        if self.copied and _run(self.runtime_argv(['exec', '-u', '0', self.container, 'rm', '-f', self.container_candidate]), timeout=10).returncode:
            raise _ConfigurationError('Cannot remove the container candidate')


def _target(spec):
    target, main = Path(spec['target']), Path(spec['main'])
    if not target.is_absolute() or not main.is_absolute():
        raise _ConfigurationError('Configuration paths must be absolute')
    if spec['service'] == 'haproxy':
        if not Path(spec['root']).is_absolute():
            raise _ConfigurationError('HAProxy directory must be absolute')
        root = Path(spec['root']).resolve()
        target, main = target.resolve(), main.resolve()
        if target != main and (root not in target.parents or target.suffix != '.cfg'):
            raise _ConfigurationError('Selected configuration resolves outside the HAProxy directory')
    elif spec['service'] in ('nginx', 'apache', 'keepalived'):
        target = target.resolve()
        root = Path(spec['root']).resolve()
        if (not Path(spec['root']).is_absolute() or not main.is_file()
                or (target != main.resolve() and (root not in target.parents or target.suffix != '.conf'))):
            raise _ConfigurationError('Select the configured main file or a .conf file inside the proxy directory')
        if target.exists(): _regular(target)
    else:
        if spec.get('apply_only') or spec['action'] == 'status':
            if target.name != 'modsecurity.conf' or target.parent.name != 'waf' or target.parent.is_symlink():
                raise _ConfigurationError('Invalid WAF entrypoint path')
        elif (target.parent.name != 'rules' or target.parent.parent.name != 'waf'
                or target.parent.is_symlink() or not re.fullmatch(r'[A-Za-z0-9._-]+\.conf', target.name)):
            raise _ConfigurationError('Invalid WAF rule path')
        _regular(target)
        if not main.is_file():
            raise _ConfigurationError('Main configuration is missing')
    return target, main


def diagnose_waf(spec):
    """Inspect WAF without installing files or invoking a service action.

    These are point-in-time process and saved-configuration checks, not proof
    that every virtual host sends requests through the WAF.
    """
    result = dict(status='ok', process='unknown', check='not_checked', module='unknown', error='')
    phase = 'process_unavailable'
    try:
        if (spec['service'] not in ('nginx_waf', 'haproxy_waf') or spec.get('candidate')
                or spec.get('action_command') or spec.get('apply_only')):
            raise _ConfigurationError('Unsupported WAF status operation')
        container, unit = spec.get('container', ''), spec.get('service_unit', '')
        if not container:
            if not unit or unit.startswith('-'):
                raise _ConfigurationError('A service name is required')
            loaded = _run(['systemctl', 'show', unit, '--property=LoadState', '--value'], timeout=5)
            if loaded.returncode or loaded.stdout.strip() != b'loaded':
                result['process'] = 'missing' if loaded.stdout.strip() == b'not-found' else 'unknown'
                result['error'] = phase
                return result
        result['process'], pid = service_process(container, unit, **({'runtime':spec['container_runtime']} if spec.get('container_runtime') else {}))
        if result['process'] == 'unknown':
            result['error'] = phase
            return result
        phase = 'config_unavailable'
        target, main = _target(spec)
        validator_type = _NginxValidator if spec['service'] == 'nginx_waf' else _HaproxyWafValidator
        validator = validator_type(spec, target, main)
        validator.inspect()
        phase = 'check_unavailable'
        if spec['service'] == 'haproxy_waf':
            result['module'] = 'not_applicable'
            if pid:
                result['check'] = 'ready' if validator.ready(pid) else 'unready'
        elif not container or pid:
            result['check'], result['module'] = validator.module_state()
        # A restart during the check invalidates the readiness observation.
        if service_process(container, unit, **({'runtime':spec['container_runtime']} if spec.get('container_runtime') else {})) != (result['process'], pid):
            result.update(process='unknown', check='not_checked', error='process_changed')
    except Exception:
        # Return a bounded diagnostic, never configuration output or a command
        # containing secrets. The caller logs this code and renders its remedy.
        result['error'] = phase
    return result


def execute(spec: dict) -> dict:
    """Run one transaction under the lock acquired by candidate_command."""
    if spec.get('action') == 'status':
        return diagnose_waf(spec)
    result = {'status': 'failed', 'code': 'save_failed'}
    work = upload = validator = None
    installed = action_started = keep_backup = False
    original = content = None
    phase = 'prepare'
    try:
        service, action = spec['service'], spec['action']
        if service not in ('haproxy', 'nginx', 'apache', 'keepalived', 'nginx_waf', 'haproxy_waf') or action not in ('test', 'check', 'save', 'reload', 'restart'):
            raise _ConfigurationError('Unsupported configuration transaction')
        if service == 'haproxy_waf' and action not in ('save', 'restart'):
            raise _ConfigurationError('HAProxy WAF supports save and restart only')
        apply_only = spec.get('apply_only', False)
        if apply_only and (not service.endswith('_waf') or action not in ('reload', 'restart') or spec.get('candidate')):
            raise _ConfigurationError('Unsupported WAF apply operation')
        if action != 'check' and not apply_only:
            path = Path(spec['candidate'])
            if not path.is_absolute() or path.resolve() in (Path(spec['target']).resolve(), Path(spec['main']).resolve()):
                raise _ConfigurationError('Invalid candidate path')
            _regular(path)
            upload = path
            content = upload.read_bytes()
        target, main = _target(spec)
        action_command = spec.get('action_command', '') if action in ('reload', 'restart') else ''
        if action in ('reload', 'restart') and not action_command:
            raise _ConfigurationError('Service action command is missing')
        original = _contents(target)
        # Callers that prepare a candidate from a snapshot can reject stale edits
        # under the same lock that protects validation and file replacement.
        if 'expected_sha256' in spec:
            expected = spec['expected_sha256']
            if (not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected)
                    or original is None or hashlib.sha256(original).hexdigest() != expected):
                raise _ConfigurationError('Configuration changed before the transaction; prepare a new candidate')
        validator_type = {'haproxy': _HaproxyValidator, 'nginx': _NginxValidator, 'apache': _ApacheValidator, 'keepalived': _KeepalivedValidator,
                          'nginx_waf': _NginxValidator, 'haproxy_waf': _HaproxyWafValidator}[service]
        validator = validator_type(spec, target, main)
        phase = 'mount'
        validator.inspect()
        phase = 'validate'
        if apply_only:
            if validator.can_validate and not validator.validate():
                raise _ConfigurationError('Current WAF configuration validation failed')
            phase = 'apply'
            validator.apply()
            if _contents(target) != original:
                raise _ConfigurationError('WAF entrypoint changed during apply')
            result = {'status': 'ok'}
        elif action == 'check':
            if not validator.validate():
                raise _ConfigurationError('Current configuration validation failed')
            result = {'status': 'ok'}
        else:
            # Baseline failure must not prevent repairing an already invalid file.
            baseline_valid = False
            if validator.can_validate and (action_command or not validator.validate_before_install):
                baseline_valid = validator.validate()
            phase = 'prepare'
            work = Path(tempfile.mkdtemp(prefix='roxywi-candidate-'))
            backup, staged = work / 'before', work / 'candidate.cfg'
            if original is not None:
                _copy(target, backup)
                if backup.read_bytes() != original:
                    raise _ConfigurationError('Configuration changed before staging')
            staged.write_bytes(content)
            staged.chmod(0o600)
            phase = 'validate'
            if validator.validate_before_install and not validator.validate(staged):
                raise _ConfigurationError('Candidate configuration validation failed')
            if action != 'test' or not validator.validate_before_install:
                phase = 'prepare'
                installed = True
                _install(staged, target, original, backup if original is not None else None)
                phase = 'validate'
                if validator.can_validate and not validator.validate_before_install and not validator.validate(staged):
                    raise _ConfigurationError('Candidate configuration validation failed')
                if _contents(target) != content:
                    raise _ConfigurationError('Configuration changed during validation')
                if action == 'test':
                    _install(backup, target, content, backup)
                    installed = False
                elif action_command:
                    phase = 'apply'
                    action_started = True
                    validator.apply()
            result = {'status': 'ok'}
    except Exception as exc:
        code = {'validate': 'validation_failed', 'apply': 'apply_failed', 'mount': 'mount_failed'}.get(phase, 'save_failed')
        result = {'status': 'failed', 'code': code, 'phase': phase, 'cause': type(exc).__name__}
        if isinstance(exc, _ConfigurationError):
            result['reason'] = str(exc)
        if installed:
            try:
                if _contents(target) != original:
                    if original is None:
                        if _contents(target) != content:
                            raise _ConfigurationError('New configuration changed during the transaction')
                        target.unlink()
                    else:
                        _install(backup, target, content, backup)
                result['restored'] = True
                if action_started:
                    if validator.can_validate and (not baseline_valid or not validator.validate()):
                        raise _ConfigurationError('The previous configuration cannot be applied safely')
                    validator.apply()
            except Exception as recovery_error:
                keep_backup = True
                result.update(code='recovery_failed', backup=str(backup if original is not None else work),
                              recovery=type(recovery_error).__name__)
    finally:
        # Independent cleanup attempts: a failed Docker cleanup must not leak the upload.
        cleanups = []
        if validator:
            cleanups.append(validator.close)
        if upload:
            cleanups.append(lambda: _unlink(upload))
        if work and not keep_backup:
            cleanups.append(lambda: shutil.rmtree(work))
        for cleanup in cleanups:
            try:
                cleanup()
            except Exception as cleanup_error:
                result.update(status='failed', cleanup=type(cleanup_error).__name__)
                result.setdefault('code', 'save_failed')
    return result


def main() -> None:
    signals = [getattr(signal, name) for name in ('SIGHUP', 'SIGINT', 'SIGTERM') if hasattr(signal, name)]

    def interrupted(signum, frame):
        for number in signals:
            signal.signal(number, signal.SIG_IGN)
        raise InterruptedError('Configuration transaction interrupted')

    for number in signals:
        signal.signal(number, interrupted)
    print(json.dumps(execute(json.loads(sys.argv[1]))))


if __name__ == '__main__':
    main()
