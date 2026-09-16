"""Run isolated, real Docker health/recovery checks against an already built image."""

import subprocess
import time
from uuid import uuid4


def docker(*args, check=True):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=180)
    if check and result.returncode:
        raise RuntimeError(f'Docker command failed: {result.stderr}')
    return result


def wait_for(callback, description, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if callback():
            return
        time.sleep(2)
    raise AssertionError(f'Timed out: {description}')


def main():
    prefix = f'roxy-wi-health-{uuid4().hex[:10]}'
    network = f'{prefix}-network'
    volume = f'{prefix}-data'
    broker = f'{prefix}-broker'
    containers = []
    resources = []
    environment = {
        'ROXYWI_DEPLOYMENT_MODE': 'compose',
        'ROXYWI_DATABASE_ENGINE': 'sqlite',
        'ROXYWI_DB_PATH': '/var/lib/roxy-wi/roxy-wi.db',
        'ROXYWI_SECRET_KEY': 'health-smoke-secret-key-with-at-least-32-characters',
        'ROXYWI_SECRET_PHRASE': 'E2nCq8NnECvPQ5zUQntL_-Nt-qBncYkrEmMkYGzVpyM=',
        'ROXYWI_JWT_ALGORITHM': 'HS256',
        'ROXYWI_BOOTSTRAP_ADMIN_PASSWORD': 'HealthSmokeAdminPassword!',
        'ROXYWI_RABBITMQ_HOST': broker,
        'ROXYWI_RABBITMQ_USER': 'health-test',
        'ROXYWI_RABBITMQ_PASSWORD': 'health-test-password',
        'ROXYWI_RABBITMQ_VHOST': '/',
        'ROXYWI_PROCESS_HEARTBEAT_INTERVAL': '5',
    }
    common_args = ['--network', network, '--volume', f'{volume}:/var/lib/roxy-wi',
                   '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,mode=1777']
    for key, value in environment.items():
        common_args.extend(['--env', f'{key}={value}'])

    def start(name, *args):
        docker('run', '--detach', '--name', name, *args)
        containers.append(name)

    def probe(name, check='ready'):
        return docker('exec', name, 'python', '/var/www/haproxy-wi/roxy_wi.py',
                      'healthcheck', '--check', check, check=False).returncode == 0

    def assert_workers_unready(workers):
        wait_for(lambda: all(not probe(name) for name in workers), 'workers become unready')
        for name in workers:
            assert probe(name, 'live'), f'{name}: dependency outage failed liveness'

    try:
        docker('network', 'create', network)
        resources.append(('network', network))
        docker('volume', 'create', volume)
        resources.append(('volume', volume))
        start(broker, '--network', network,
              '--env', 'RABBITMQ_DEFAULT_USER=health-test',
              '--env', 'RABBITMQ_DEFAULT_PASS=health-test-password', 'rabbitmq:4')
        wait_for(lambda: docker('exec', broker, 'rabbitmq-diagnostics', '-q', 'ping',
                                check=False).returncode == 0, 'RabbitMQ starts')
        docker('run', '--rm', '--no-healthcheck', *common_args, 'roxy-wi:test', 'migrate')
        workers = []
        for role in ('scheduler', 'service-events', 'operations', 'web'):
            name = f'{prefix}-{role}'
            start(name, *common_args, 'roxy-wi:test', role)
            if role != 'web':
                workers.append(name)
        wait_for(lambda: all(probe(name) for name in containers if name != broker), 'all roles ready')
        for name in workers:
            wait_for(lambda: docker('inspect', '--format', '{{.State.Health.Status}}', name).stdout.strip()
                     == 'healthy', f'{name}: image HEALTHCHECK is healthy')

        docker('stop', '--time', '10', broker)
        assert_workers_unready(workers)
        assert probe(f'{prefix}-web'), 'Web uses the durable DB outbox and must not require RabbitMQ'
        docker('start', broker)
        wait_for(lambda: all(probe(name) for name in workers), 'workers recover after RabbitMQ restart')

        # Keep the existing SQLite database readable but prevent writes. A
        # SELECT-only probe would miss this failure; worker readiness must not.
        lock = f'{prefix}-db-lock'
        start(lock, '--init', '--volume', f'{volume}:/var/lib/roxy-wi',
              '--entrypoint', 'python', 'roxy-wi:test', '-u', '-c',
              'import sqlite3,time; db=sqlite3.connect("/var/lib/roxy-wi/roxy-wi.db"); '
              'db.execute("BEGIN IMMEDIATE"); print("locked", flush=True); time.sleep(180)')
        wait_for(lambda: 'locked' in docker('logs', lock).stdout, 'SQLite write lock acquired')
        assert_workers_unready(workers)
        docker('stop', '--time', '5', lock)
        wait_for(lambda: all(probe(name) for name in workers), 'workers recover after DB writes resume')
        print('All roles: ready; DB/RabbitMQ failure and recovery checks passed.')
    except Exception:
        for name in containers:
            result = docker('logs', '--tail', '80', name, check=False)
            print(f'{name}:\n{result.stdout}\n{result.stderr}')
        raise
    finally:
        for name in reversed(containers):
            result = docker('rm', '--force', name, check=False)
            if result.returncode:
                print(f'Cannot remove test container {name}: {result.stderr}')
        for kind, name in reversed(resources):
            result = docker(kind, 'rm', name, check=False)
            if result.returncode:
                print(f'Cannot remove test {kind} {name}: {result.stderr}')


if __name__ == '__main__':
    main()
