"""Standard-library OCI runtime connector, also shipped to managed Linux hosts.

A runtime identity is explicit: never discover another user's containers or silently
fall back to another engine. Lifecycle units are optional for adopted containers.
"""
import json
import configparser
import re
import shlex
import subprocess
import time
import os
import sys
from pathlib import Path

ENGINES = ('docker', 'podman')
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
OWNER = re.compile(r'^[a-z_][a-z0-9_-]{0,31}\$?$')
UNIT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}\.service$')


def validate(spec=None):
    spec = {} if spec is None else spec
    if not isinstance(spec, dict):
        raise ValueError('Container runtime settings must be an object')
    if set(spec) - {'engine', 'owner', 'unit'}:
        raise ValueError('Unknown container runtime setting')
    engine, owner, unit = spec.get('engine', 'docker'), spec.get('owner', 'root'), spec.get('unit', '')
    if engine not in ENGINES or not isinstance(owner, str) or not OWNER.fullmatch(owner):
        raise ValueError('Select a supported engine and a Linux container owner')
    if not isinstance(unit, str) or (unit and not UNIT.fullmatch(unit)):
        raise ValueError('Invalid container lifecycle unit')
    if unit and engine != 'podman':
        raise ValueError('Lifecycle units require a verified Podman Quadlet')
    return dict(engine=engine, owner=owner, unit=unit)


def name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError('Invalid container name')
    return value


def identity(spec=None):
    """Resolve rootless identity on the managed host, not on the web controller."""
    spec = validate(spec)
    if spec['owner'] == 'root':
        return []
    import pwd
    account = pwd.getpwnam(spec['owner'])
    if account.pw_uid == 0 or not Path('/run/user', str(account.pw_uid)).is_dir():
        raise ValueError('Container owner needs an active user runtime directory')
    env = ['HOME=' + account.pw_dir, 'USER=' + account.pw_name, 'LOGNAME=' + account.pw_name,
           'PATH=/usr/local/bin:/usr/bin:/bin', 'XDG_RUNTIME_DIR=/run/user/' + str(account.pw_uid),
           'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/' + str(account.pw_uid) + '/bus']
    if spec['engine'] == 'docker':
        env.append('DOCKER_HOST=unix:///run/user/' + str(account.pw_uid) + '/docker.sock')
    return ['runuser', '--user', account.pw_name, '--', 'env', '-i', *env]


def argv(spec, arguments):
    spec = validate(spec)
    if not isinstance(arguments, (list, tuple)) or not arguments:
        raise ValueError('Container command arguments are required')
    if any(not isinstance(value, str) or any(ord(c) < 32 for c in value) for value in arguments):
        raise ValueError('Invalid container command argument')
    return identity(spec) + [spec['engine'], *arguments]


def lifecycle(spec, container, action):
    spec, container = validate(spec), name(container)
    if action not in ('start', 'stop', 'restart', 'reload', 'haproxy-reload'):
        raise ValueError('Unsupported container lifecycle action')
    if action == 'haproxy-reload':
        process = subprocess.run(argv(spec, ['exec', container, 'cat', '/proc/1/cmdline']),
            check=True, capture_output=True, timeout=10).stdout.decode().split('\x00')
        if not process or 'haproxy' not in Path(process[0]).name or not any(arg in ('-W', '-Ws') for arg in process):
            raise ValueError('HAProxy reload requires master-worker mode (-W or -Ws) as container PID 1')
        return argv(spec, ['kill', '-s', 'USR2', container])
    if action == 'reload':
        return argv(spec, ['kill', '-s', 'HUP', container])
    if spec['unit']:
        verify_unit(spec, container)
        return identity(spec) + ['systemctl', *(['--user'] if spec['owner'] != 'root' else []), action, spec['unit']]
    return argv(spec, [action, container])


def quadlet_name(configuration, source):
    raw = configuration.get('Container', 'ContainerName', fallback='')
    values = shlex.split(raw) if raw else ['systemd-' + source.stem]
    if len(values) != 1:
        raise ValueError('Unsupported Quadlet container name')
    return name(values[0])


def verify_unit(spec, container):
    """A selected unit must be the Quadlet defining this exact container."""
    prefix = identity(spec) + ['systemctl', *(['--user'] if spec['owner'] != 'root' else [])]
    result = subprocess.run([*prefix, 'show', spec['unit'], '--property=SourcePath', '--value'],
                            check=True, capture_output=True, text=True, timeout=15)
    source = Path(result.stdout.strip())
    if not source.is_absolute() or source.suffix != '.container':
        raise ValueError('The lifecycle unit must originate from a Podman Quadlet')
    if spec['owner'] == 'root':
        roots = ['/etc/containers/systemd', '/usr/share/containers/systemd', '/run/containers/systemd']
    else:
        import pwd
        account = pwd.getpwnam(spec['owner'])
        roots = [str(Path(account.pw_dir) / '.config/containers/systemd'),
                 '/etc/containers/systemd/users', '/usr/share/containers/systemd/users',
                 '/run/user/' + str(account.pw_uid) + '/containers/systemd']
    if not any(source.resolve().is_relative_to(Path(root).resolve()) for root in roots):
        raise ValueError('Unexpected Quadlet source location')
    configuration = configparser.ConfigParser(interpolation=None, strict=False)
    configuration.read(source)
    if quadlet_name(configuration, source) != container:
        raise ValueError('The selected Quadlet does not define this container name')


def shell(spec, arguments=None, *, container=None, action=None):
    """Construct SSH shell safely; rootless account lookup runs on the host."""
    spec = validate(spec)
    if spec['owner'] == 'root' and not (action and (spec['unit'] or action == 'haproxy-reload')):
        values = lifecycle(spec, container, action) if action else argv(spec, arguments)
        return shlex.join(['sudo', *values])
    script = Path(__file__).read_text(encoding='utf-8') + '\n'
    script += ('data=json.loads(__import__("sys").argv[1])\n'
               'args=lifecycle(data["runtime"],data["container"],data["action"]) if data.get("action") else argv(data["runtime"],data["arguments"])\n'
               'raise SystemExit(subprocess.run(args, timeout=180).returncode)\n')
    data = dict(runtime=spec, arguments=arguments, container=container, action=action)
    return shlex.join(['sudo', '-n', 'python3', '-c', script, json.dumps(data)])


def embedded():
    """Install this fixed repository source in a remote helper's module namespace."""
    source = Path(__file__).read_text(encoding='utf-8')
    return ('import types, sys\nmodule=types.ModuleType("roxywi_container_runtime")\n'
            'sys.modules[module.__name__]=module\n'
            'exec(compile(' + repr(source) + ',module.__name__,"exec"),module.__dict__)\n')


def inspect_host(spec):
    """Return bounded operational metadata, never environment or registry secrets."""
    spec = validate(spec)
    deadline = time.monotonic() + 45
    def read(arguments):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('Container inspection exceeded its time limit')
        result = subprocess.run(argv(spec, arguments), check=True, capture_output=True, text=True, timeout=min(20, remaining))
        if len(result.stdout) > 2 * 1024 * 1024:
            raise ValueError('Container inspection exceeded its size limit')
        return result.stdout
    version = read(['--version']).strip()
    names = read(['ps','--all','--format','{{.Names}}']).splitlines()
    if len(names) > 128:
        raise ValueError('Too many containers; select a dedicated owner before discovery')
    result = []
    for value in names:
        value = name(value)
        state = json.loads(read(['inspect',value]))[0]
        result.append(dict(name=value, image=state.get('Config',{}).get('Image',''),
            running=bool(state.get('State',{}).get('Running')), unit='',
            network=state.get('HostConfig',{}).get('NetworkMode',''),
            mounts=[dict(source=m.get('Source',''),destination=m.get('Destination',''),
                         writable=bool(m.get('RW',False))) for m in state.get('Mounts',[])][:64]))
    if spec['engine'] == 'podman':
        if spec['owner'] == 'root':
            roots = [Path('/etc/containers/systemd'),Path('/run/containers/systemd'),Path('/usr/share/containers/systemd')]
        else:
            import pwd
            account = pwd.getpwnam(spec['owner'])
            roots = [Path(account.pw_dir)/'.config/containers/systemd',
                     Path('/etc/containers/systemd/users')/str(account.pw_uid),
                     Path('/etc/containers/systemd/users')]
        files = sorted({p for root in roots for p in root.glob('*.container')})[:256]
        for path in files:
            if path.stat().st_size > 65536:
                continue
            configuration=configparser.ConfigParser(interpolation=None,strict=False)
            try:
                configuration.read(path)
            except configparser.Error:
                continue
            try:
                value=quadlet_name(configuration,path)
            except ValueError:
                continue
            for item in result:
                if item['name'] != value:
                    continue
                selected=dict(spec,unit=path.stem+'.service')
                try:
                    verify_unit(selected,value)
                except (ValueError,OSError,subprocess.SubprocessError):
                    continue
                item['unit']=selected['unit']
    return dict(runtime=spec, version=version, cgroup_v2=Path('/sys/fs/cgroup/cgroup.controllers').is_file(), containers=result)


def container_state(spec, container):
    """Distinguish an absent, stopped Quadlet from an inaccessible engine."""
    spec, container = validate(spec), name(container)
    result = subprocess.run(argv(spec, ['inspect', container]), capture_output=True, text=True, timeout=15)
    if len(result.stdout) + len(result.stderr) > 65536:
        raise ValueError('Container status exceeded its size limit')
    if result.returncode:
        # Quadlet removes its container when stopped. Never treat an engine,
        # permission or invalid-unit failure as an intentionally stopped proxy.
        if spec['engine'] == 'podman' and spec['unit']:
            exists = subprocess.run(argv(spec, ['container', 'exists', container]), capture_output=True, timeout=15)
            if exists.returncode == 1:
                verify_unit(spec, container)
                unit = subprocess.run(identity(spec) + ['systemctl', *(['--user'] if spec['owner'] != 'root' else []),
                    'show', spec['unit'], '--property=ActiveState', '--value'],
                    check=True, capture_output=True, text=True, timeout=15)
                if unit.stdout.strip() == 'inactive':
                    return {'State': {'Running': False}}
        result.check_returncode()
    return json.loads(result.stdout)[0]


def service_status(spec,container,service):
    """Read process/version metadata from this exact container, not a host grep."""
    spec=validate(spec);container=name(container)
    if service not in ('nginx','apache','keepalived'):
        raise ValueError('Unsupported container status probe')
    def read(arguments,check=True):
        result=subprocess.run(argv(spec,arguments),check=check,capture_output=True,text=True,timeout=15)
        if len(result.stdout)+len(result.stderr)>65536:raise ValueError('Container status exceeded its size limit')
        return result
    state=container_state(spec,container)
    process=state.get('State',{})
    result=dict(Version='unknown',Uptime=process.get('StartedAt','') if process.get('Running') else 'stopped',Process='0')
    if not process.get('Running'):return result
    program={'nginx':'nginx','apache':'httpd','keepalived':'keepalived'}[service]
    version=read(['exec',container,program,'-v'],check=False)
    match=re.search(r'(?:nginx/|Apache/|Keepalived v)([A-Za-z0-9_.+-]{1,64})',version.stdout+version.stderr)
    if match:result['Version']=match.group(1)
    output=read(['top',container,*(['comm'] if spec['engine']=='podman' else ['-eo','comm'])]).stdout.splitlines()[1:]
    result['Process']=str(sum(1 for line in output if line.strip().split(' ',1)[0] in (program,program+':')))
    return result


def in_network(spec, container, source, payload, *, timeout=15):
    """Execute a fixed stdlib probe in the verified container network namespace."""
    spec, container = validate(spec), name(container)
    def state():
        return json.loads(subprocess.run(argv(spec, ['inspect', container]), check=True,
            capture_output=True, text=True, timeout=10).stdout)[0]
    observed = state()
    ident = observed.get('Id', observed.get('ID', ''))
    pid = int(observed.get('State', {}).get('Pid', 0))
    if (not re.fullmatch(r'[a-f0-9]{64}', ident) or pid <= 0 or not observed['State'].get('Running')
            or ident not in Path('/proc', str(pid), 'cgroup').read_text()):
        raise ValueError('Cannot verify the container network namespace')
    descriptor = os.open('/proc/' + str(pid) + '/ns/net', os.O_RDONLY)
    try:
        current = state()
        if current.get('Id', current.get('ID')) != ident or current.get('State', {}).get('Pid') != pid or not current['State'].get('Running'):
            raise ValueError('Container process changed before the probe')
        result = subprocess.run(['nsenter', '--net=/proc/self/fd/' + str(descriptor), sys.executable, '-c', source],
            check=True, capture_output=True, input=json.dumps(payload).encode(), timeout=timeout, pass_fds=(descriptor,))
        if len(result.stdout) + len(result.stderr) > 2 * 1024 * 1024:
            raise ValueError('Container probe exceeded its output limit')
        return result.stdout.decode()
    finally:
        os.close(descriptor)


def keepalived_state(spec, container):
    spec, container = validate(spec), name(container)
    if spec['owner'] != 'root': raise ValueError('Keepalived requires a rootful host-network container')
    def run(arguments, check=True):
        return subprocess.run(argv(spec, arguments), check=check, capture_output=True, text=True, timeout=10)
    record = json.loads(run(['inspect', container]).stdout)[0]
    if record.get('HostConfig', {}).get('NetworkMode') != 'host':
        raise ValueError('Keepalived requires host networking')
    command = run(['exec', container, 'cat', '/proc/1/cmdline']).stdout.split('\x00')
    if not command or Path(command[0]).name != 'keepalived':
        raise ValueError('Keepalived must run as container PID 1')
    path = '/tmp/keepalived.data'
    run(['exec', container, 'rm', '-f', path])
    run(['kill', '-s', 'USR1', container])
    try:
        for _ in range(10):
            output = run(['exec', container, 'cat', path], check=False).stdout[:1024*1024]
            match = re.search(r'^\s*State\s*=\s*(MASTER|BACKUP|FAULT|INIT)\b', output, re.M)
            if match: return match.group(1)
            time.sleep(.2)
        raise ValueError('Keepalived did not report its VRRP state')
    finally:
        run(['exec', container, 'rm', '-f', path], check=False)
