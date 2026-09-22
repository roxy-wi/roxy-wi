#!/usr/bin/env python3
"""Manage an isolated local evaluation with persistent secrets and HTTPS."""

import argparse
import base64
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / 'docker' / '.env.quickstart'
PROJECT = 'roxywi-quickstart'
KEYS = ('ROXYWI_VERSION', 'ROXYWI_PUBLIC_URL', 'ROXYWI_SECRET_KEY',
        'ROXYWI_SECRET_PHRASE', 'ROXYWI_RABBITMQ_PASSWORD')


def prepare_environment(path=ENV_FILE):
    if path.exists():
        values = dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines()
                      if '=' in line and not line.startswith('#'))
        if not all(values.get(key, '').strip() for key in KEYS):
            raise RuntimeError(f'{path} is incomplete. Restore the existing secrets before starting.')
        return False
    values = dict(zip(KEYS, ('quickstart', 'https://localhost:8443', secrets.token_urlsafe(48),
                           base64.urlsafe_b64encode(os.urandom(32)).decode(), secrets.token_urlsafe(32))))
    # Exclusive creation prevents a second start from replacing persisted keys.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(''.join(f'{key}={value}\n' for key, value in values.items()))
        stream.flush()
        os.fsync(stream.fileno())
    return True


def compose(*args):
    return ['docker', 'compose', '--project-name', PROJECT, '--env-file', str(ENV_FILE),
            '-f', str(ROOT / 'docker' / 'docker-compose.sqlite.yml'),
            '-f', str(ROOT / 'docker' / 'compose.quickstart.yml'), *args]


def run(args, **kwargs):
    # A shell's production settings must not override the local evaluation file.
    environment = {key: value for key, value in os.environ.items() if key not in KEYS}
    return subprocess.run(args, cwd=ROOT, env=environment, check=True, **kwargs)


def check_compose_version():
    version = run(['docker', 'compose', 'version', '--short'], capture_output=True, text=True).stdout.strip()
    parsed = re.match(r'v?(\d+)\.(\d+)\.(\d+)', version)
    if not parsed or tuple(map(int, parsed.groups())) < (2, 24, 4):
        raise RuntimeError('Docker Compose 2.24.4 or newer is required for the isolated HTTPS configuration.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'status', 'logs', 'password', 'stop'))
    action = parser.parse_args().action
    try:
        check_compose_version()
        if action == 'start':
            prepare_environment()
            run(compose('config', '--quiet'))
            run(compose('up', '--build', '--detach', '--wait', '--wait-timeout', '300'))
            print('Open https://localhost:8443 and accept the local evaluation certificate.')
            print('Login: admin. Show the initial password with: python3 docker/quickstart.py password')
        else:
            if not ENV_FILE.exists():
                raise RuntimeError('No quick-start environment exists. Run the start command first.')
            commands = {
                'status': ('ps',),
                'logs': ('logs', '--tail', '100'),
                'password': ('exec', '-T', 'web', 'cat', '/var/lib/roxy-wi/bootstrap-admin-password'),
                'stop': ('down',),  # Keep volumes and encryption keys for the next start.
            }
            run(compose(*commands[action]))
    except FileNotFoundError:
        parser.exit(1, 'Docker was not found. Install Docker with Linux container support and Compose.\n')
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Quick start failed: {error}\n')


if __name__ == '__main__':
    main()
