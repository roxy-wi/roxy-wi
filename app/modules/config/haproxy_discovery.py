"""Read HAProxy startup sources on a managed host. Standard library only.

Executed remotely with sudo python3. Never executes startup commands or exports
environment values: only configuration paths and diagnostic codes leave the host.
"""
import glob
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
from pathlib import Path


class DiscoveryError(Exception):
    pass


def run(args):
    result = subprocess.run(args, universal_newlines=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=15, check=False)
    if result.returncode:
        denied = any(word in result.stderr.lower() for word in ('permission denied', 'access denied', 'not authorized'))
        raise DiscoveryError('permission_denied' if denied else 'inspection_failed')
    return result.stdout


def words(value):
    # systemctl show escapes non-printable characters and spaces in some fields.
    value = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: '\\' + chr(int(m[1], 16)), value)
    try:
        return shlex.split(value)
    except ValueError as exc:
        raise DiscoveryError('unsupported_startup') from exc


def absolute(value, cwd='/'):
    if not value or any(c in value for c in '\x00\r\n'):
        raise DiscoveryError('unsupported_startup')
    return posixpath.normpath(value if value.startswith('/') else posixpath.join(cwd, value))


def sources_from_argv(argv, cwd='/'):
    if not argv or posixpath.basename(argv[0]) != 'haproxy':
        raise DiscoveryError('unsupported_startup')
    sources = []
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg in ('-f', '-C'):
            index += 1
            if index == len(argv):
                raise DiscoveryError('unsupported_startup')
            if arg == '-C':
                cwd = absolute(argv[index], cwd)
            else:
                sources.append(argv[index])
        elif arg == '--':
            sources.extend(argv[index + 1:])
            break
        index += 1
    if not sources:
        raise DiscoveryError('unsupported_startup')
    return [absolute(path, cwd) for path in sources]


def expand_environment(argv, environment):
    expanded = []
    for arg in argv:
        if re.fullmatch(r'\$[A-Za-z_][A-Za-z_0-9]*', arg):
            expanded.extend(words(environment.get(arg[1:], '')))
        else:
            value = re.sub(r'\$\{([A-Za-z_][A-Za-z_0-9]*)\}', lambda m: environment.get(m[1], ''), arg)
            if re.search(r'\$(?!\$)', value):
                raise DiscoveryError('unsupported_startup')
            expanded.append(value.replace('$$', '$'))
    return expanded


def environment_file(path):
    # EnvironmentFile is data, not a shell script. In particular, never source it.
    result = {}
    text = Path(path).read_text(encoding='utf-8').replace('\\\n', '')
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        match = re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*)\s*=(.*)', line)
        if not match:
            raise DiscoveryError('unsupported_startup')
        value = match[2].strip()
        if value.startswith(('"', "'")):
            parts = words(value)
            if len(parts) != 1:
                raise DiscoveryError('unsupported_startup')
            value = parts[0]
        result[match[1]] = value
    return result


def process_argv(pid):
    if not pid:
        return None
    # Docker entrypoints may leave a parent shell. Search only its descendants,
    # never unrelated HAProxy instances on the same host.
    pending = [int(pid)]
    seen = set()
    while pending and len(seen) < 64:
        current = pending.pop(0)
        if current in seen:
            continue
        seen.add(current)
        try:
            executable = os.readlink('/proc/%s/exe' % current)
            if executable.endswith(' (deleted)'):
                executable = executable[:-10]
            if posixpath.basename(executable) == 'haproxy':
                args = Path('/proc/%s/cmdline' % current).read_bytes().rstrip(b'\0').split(b'\0')
                argv = [part.decode('utf-8') for part in args]
                # Use the verified executable rather than a process title.
                if len(argv) > 1:
                    argv[0] = executable
                    return argv
            children = Path('/proc/%s/task/%s/children' % (current, current)).read_text().split()
            pending.extend(int(child) for child in children)
        except FileNotFoundError:
            continue  # A worker may exit during a graceful reload.
    raise DiscoveryError('unsupported_startup')


def systemd_sources(name):
    properties = ['LoadState', 'ExecStart', 'Environment', 'EnvironmentFiles', 'MainPID', 'WorkingDirectory']
    output = run(['systemctl', 'show', name, '--no-pager', '--property=' + ','.join(properties)])
    fields = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
    if fields.get('LoadState') != 'loaded':
        raise DiscoveryError('service_missing')
    commands = re.findall(r'argv\[\]=(.*?) ; ignore_errors=', fields.get('ExecStart', ''))
    if len(commands) != 1:
        raise DiscoveryError('unsupported_startup')
    environment = dict(item.split('=', 1) for item in words(fields.get('Environment', '')) if '=' in item)
    files = fields.get('EnvironmentFiles', '')
    for match in re.finditer(r'(.+?) \(ignore_errors=(yes|no)\)(?: |$)', files):
        paths = words(match[1].strip())
        if len(paths) != 1:
            raise DiscoveryError('unsupported_startup')
        matches = sorted(glob.glob(paths[0]))
        if not matches and match[2] != 'yes':
            raise DiscoveryError('source_missing')
        for path in matches:
            environment.update(environment_file(path))
    if files and not re.search(r'\(ignore_errors=(yes|no)\)', files):
        raise DiscoveryError('unsupported_startup')
    cwd = fields.get('WorkingDirectory') or '/'
    configured = sources_from_argv(expand_environment(words(commands[0]), environment), cwd)
    active = process_argv(int(fields.get('MainPID', '0')))
    if active and sources_from_argv(active, cwd) != configured:
        raise DiscoveryError('startup_changed')
    return configured, [], bool(active)


def docker_sources(name):
    data = json.loads(run(['docker', 'inspect', '--type', 'container', name]))[0]
    config = data['Config']
    entrypoint, command = config.get('Entrypoint') or [], config.get('Cmd') or []
    if not isinstance(entrypoint, list) or not isinstance(command, list):
        raise DiscoveryError('unsupported_startup')
    argv = entrypoint + command
    if entrypoint and posixpath.basename(entrypoint[0]) in ('docker-entrypoint.sh', 'docker-entrypoint'):
        argv = command
        if argv and argv[0].startswith('-'):
            argv = ['haproxy'] + argv
    cwd = config.get('WorkingDir') or '/'
    configured = sources_from_argv(argv, cwd)
    active = process_argv(data.get('State', {}).get('Pid', 0))
    if active and sources_from_argv(active, cwd) != configured:
        raise DiscoveryError('startup_changed')
    return configured, data.get('Mounts', []), bool(active)


def host_path(path, mounts):
    matches = [mount for mount in mounts if path == mount['Destination'].rstrip('/')
               or path.startswith(mount['Destination'].rstrip('/') + '/')]
    if not matches:
        raise DiscoveryError('mount_missing')
    mount = max(matches, key=lambda item: len(item['Destination']))
    if not mount.get('Source'):
        raise DiscoveryError('mount_missing')
    return mount['Source'].rstrip('/') + path[len(mount['Destination'].rstrip('/')):]


def describe_sources(paths, mounts, root, main, docker=False):
    sources, files, seen = [], [], set()
    root, main = os.path.realpath(root), os.path.realpath(main)
    for runtime_path in paths:
        path = host_path(runtime_path, mounts) if docker else runtime_path
        canonical = os.path.realpath(path)
        directory = os.path.isdir(canonical)
        if canonical != main and not (canonical == root and directory or canonical.startswith(root.rstrip('/') + '/')):
            raise DiscoveryError('path_outside_root')
        if not os.path.exists(canonical):
            raise DiscoveryError('source_missing')
        entry = {'path': path, 'runtime_path': runtime_path, 'kind': 'directory' if directory else 'file'}
        sources.append(entry)
        children = sorted(os.listdir(path), key=os.fsencode) if directory else [None]
        for child in children:
            if child is not None and (child.startswith('.') or not child.endswith('.cfg')):
                continue
            file = posixpath.join(path, child) if child is not None else path
            if not os.path.isfile(file):
                continue
            real = os.path.realpath(file)
            if real != main and (not real.startswith(root.rstrip('/') + '/') or not real.endswith('.cfg')):
                raise DiscoveryError('path_outside_root')
            if real in seen:
                raise DiscoveryError('overlapping_sources')
            seen.add(real)
            files.append(file)
    multiple = len(sources) > 1 or any(source['kind'] == 'directory' for source in sources)
    return {'state': 'ready' if multiple else 'single', 'code': 'ready' if multiple else 'not_configured',
            'sources': sources, 'files': files}


def discover(mode, name, root, main):
    try:
        paths, mounts, active = docker_sources(name) if mode == 'docker' else systemd_sources(name)
        result = describe_sources(paths, mounts, root, main, docker=mode == 'docker')
        result.update(mode=mode, verified_running=active)
        return result
    except DiscoveryError as exc:
        code = str(exc)
    except PermissionError:
        code = 'permission_denied'
    except FileNotFoundError:
        code = 'tool_missing'
    except subprocess.TimeoutExpired:
        code = 'inspection_timeout'
    except (ValueError, KeyError, IndexError, UnicodeError, OSError):
        code = 'inspection_failed'
    return {'state': 'error', 'code': code, 'mode': mode, 'sources': [], 'files': [], 'verified_running': False}


if __name__ == '__main__':
    print(json.dumps(discover(*sys.argv[1:5])))
