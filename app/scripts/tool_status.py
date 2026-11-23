"""Read optional-service status without starting Ansible or changing the host."""
import json
import re
import shutil
import subprocess
import sys
import time


def inspect_service(component):
    """Return only the runtime, version and state needed by the install dialog."""
    if not re.fullmatch(r'[a-z_]+', component):
        raise ValueError('invalid_configuration')
    deadline = time.monotonic() + 5

    def run(arguments):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('command_failed')
        return subprocess.run(arguments, capture_output=True, text=True, timeout=remaining)

    unit = 'roxy-wi-' + component
    containers = []
    if component != 'keep_alive':
        for engine in ('docker', 'podman'):
            if not shutil.which(engine):
                continue
            result = run([engine, 'inspect', '--type', 'container', '--format',
                          '{"image":{{json .Config.Image}},"running":{{.State.Running}}}', unit])
            if result.returncode:
                if re.search(r'no such (object|container)|no container with name', result.stderr, re.I):
                    continue
                raise RuntimeError('command_failed')
            container = json.loads(result.stdout)
            containers.append(dict(engine=engine, installed=True, version=container['image'],
                                   state='active' if container['running'] else 'inactive'))
    if len(containers) > 1:
        raise RuntimeError('engine_conflict')
    if containers:
        return containers[0]

    if shutil.which('dpkg-query'):
        package = unit.replace('keep_alive', 'keep-alive')
        result = run(['dpkg-query', '-W', '-f=${db:Status-Status}\t${Version}', package])
        if result.returncode and not re.search(r'no packages found', result.stderr, re.I):
            raise RuntimeError('command_failed')
        state, _, version = result.stdout.partition('\t')
        installed = not result.returncode and state == 'installed'
    elif shutil.which('rpm'):
        result = run(['rpm', '-q', '--qf', '%{VERSION}', unit])
        if result.returncode and 'is not installed' not in result.stdout:
            raise RuntimeError('command_failed')
        installed = result.returncode == 0
        version = result.stdout.strip()
    else:
        raise RuntimeError('unsupported_os')
    result = run(['systemctl', 'is-active', unit])
    if result.returncode not in (0, 3, 4):
        raise RuntimeError('command_failed')
    return dict(engine='native', installed=installed, version=version if installed else '',
                state='active' if result.stdout.strip() == 'active' else 'inactive')


if __name__ == '__main__':
    try:
        print(json.dumps(inspect_service(sys.argv[1])))
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        # Runtime output can contain host details. Return only known error codes.
        code = str(error) if str(error) in ('engine_conflict', 'unsupported_os') else 'command_failed'
        print(json.dumps({'error_code': code}))
        sys.exit(1)
