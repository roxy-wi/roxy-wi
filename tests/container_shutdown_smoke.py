"""Real SIGTERM/queue recovery checks in disposable Docker resources.

Uses an already built image (ROXYWI_TEST_IMAGE, default roxy-wi:test). The same
file is mounted read-only as a fixture: only the slow operation is synthetic;
process runners, signals, database, RabbitMQ, claims and acknowledgements are real.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

DATA = Path('/var/lib/roxy-wi/shutdown-test')


def gate(role, identifier):
    DATA.mkdir(exist_ok=True)
    (DATA / f'{role}-started-{identifier}').touch()
    deadline = time.monotonic() + 90
    while not (DATA / f'{role}-release').exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Shutdown fixture was not released')
        time.sleep(.1)


def post_worker_init(worker):
    """Gunicorn test config: hold one real HTTP request across SIGTERM."""
    from app import app
    from flask import request
    original = app.view_functions['health.live']

    def live():
        if request.args.get('shutdown-test') == '1':
            gate('web', 1)
            return 'completed'
        return original()

    app.view_functions['health.live'] = live


def fixture(action):
    sys.path.insert(0, '/var/www/haproxy-wi')
    if action == 'web-request':
        import urllib.request
        with urllib.request.urlopen(f'http://{os.environ["SHUTDOWN_WEB_HOST"]}:8080/health/live?shutdown-test=1', timeout=90) as response:
            assert response.status == 200 and response.read() == b'completed'
        (DATA / 'web-response-received').touch()
        return
    if action == 'inspect':
        import roxy_wi_health as health
        snapshots = [json.loads(path.read_text()) for path in health.health_directory().glob('*.json')]
        print(json.dumps({'files': [path.name for path in DATA.glob('*')], 'health': snapshots}))
        return
    if action.startswith('release-'):
        (DATA / (action.removeprefix('release-') + '-release')).touch()
        return
    os.environ['ROXYWI_PROCESS_ROLE'] = action if action in {'operations', 'service-events', 'scheduler'} else 'wait-for-database'
    # Start the real scheduler only after installing the synthetic jobs.
    os.environ['ROXYWI_SCHEDULER_ENABLED'] = '0'
    from app.modules.db.db_model import InstallationTasks, close_database_connection
    from app.modules.common.time import utc_now
    from app.modules.operations import queue
    import pika

    if action == 'seed':
        from app.modules.integrations.rabbitmq_consumer import RabbitConsumerSettings, declare_topology
        from datetime import datetime, timezone
        DATA.mkdir(exist_ok=True)
        for number in (1, 2):
            queue.create_ansible_task(service_name=f'shutdown-{number}', server_ids=[], user_id=None,
                group_id=None, inventory={}, server_ips=[], ansible_role='haproxy')
        assert queue.publish_pending_operations() == 2
        settings = RabbitConsumerSettings.load()
        connection = pika.BlockingConnection(queue.OperationQueueSettings.load().parameters())
        try:
            channel = connection.channel()
            declare_topology(channel, settings)
            channel.confirm_delivery()
            for number in (1, 2):
                event = dict(event_id=str(uuid4()), type='checker.worker.heartbeat', source='checker',
                    worker_id=f'shutdown-{number}', service='checker', heartbeat_at=datetime.now(timezone.utc).isoformat())
                channel.basic_publish(exchange=settings.exchange, routing_key=event['type'], body=json.dumps(event),
                    properties=pika.BasicProperties(delivery_mode=2), mandatory=True)
        finally:
            connection.close()
            close_database_connection()
        return
    if action == 'verify':
        from app.modules.integrations.rabbitmq_consumer import RabbitConsumerSettings
        from app.modules.db.db_model import WorkerState
        tasks = list(InstallationTasks.select().order_by(InstallationTasks.id))
        assert len(tasks) == 2 and all(task.status == 'completed' and task.attempts == 1 for task in tasks)
        assert WorkerState.select().where(WorkerState.worker_id.in_(['shutdown-1', 'shutdown-2'])).count() == 2
        assert (DATA / 'scheduler-done-1').exists() and not (DATA / 'scheduler-unexpected').exists()
        assert (DATA / 'web-response-received').exists()
        connection = pika.BlockingConnection(queue.OperationQueueSettings.load().parameters())
        try:
            channel = connection.channel()
            for name in (queue.OperationQueueSettings.load().queue, RabbitConsumerSettings.load().queue):
                assert channel.queue_declare(queue=name, passive=True).method.message_count == 0
        finally:
            connection.close()
            close_database_connection()
        print('Each operation completed once; both queues drained after restart.')
        return
    if action == 'operations':
        from app.modules.operations import worker
        def execute(operation_id, task_id):
            task = InstallationTasks.get_by_id(task_id)
            identifier = task.service_name.rsplit('-', 1)[1]
            try:
                gate('operations', identifier)
                InstallationTasks.update(status='completed', finish_date=utc_now(), updated_at=utc_now()).where(
                    InstallationTasks.id == task_id).execute()
                (DATA / f'operations-done-{identifier}').touch()
                return 'completed'
            finally:
                close_database_connection()
        worker.execute_operation = execute
        worker.run_worker()
    elif action == 'service-events':
        from app.modules.integrations import rabbitmq_consumer as worker
        original = worker.process_event
        def process(body):
            identifier = json.loads(body)['worker_id'].rsplit('-', 1)[1]
            gate('service-events', identifier)
            result = original(body)
            (DATA / f'service-events-done-{identifier}').touch()
            return result
        worker.process_event = process
        worker.run_consumer()
    elif action == 'scheduler':
        from datetime import datetime, timedelta, timezone
        from app import scheduler
        import scheduler_runner
        scheduler.remove_all_jobs()
        def blocking():
            gate('scheduler', 1)
            (DATA / 'scheduler-done-1').touch()
        scheduler.add_job('shutdown-blocking', blocking, trigger='date',
                          run_date=datetime.now(timezone.utc) + timedelta(seconds=1))
        scheduler.add_job('must-not-start', lambda: (DATA / 'scheduler-unexpected').touch(),
                          trigger='date', run_date=datetime.now(timezone.utc) + timedelta(seconds=5))
        scheduler.start()
        scheduler_runner.main()
    else:
        raise ValueError('Unknown fixture action')


def docker(*args, check=True):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=180)
    if check and result.returncode:
        raise RuntimeError(f'Docker {args[0]} failed: {result.stderr}')
    return result


def wait_for(callback, description, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if callback():
            return
        time.sleep(1)
    raise AssertionError(f'Timed out: {description}')


def main(database='sqlite'):
    prefix = 'roxy-wi-shutdown-' + uuid4().hex[:10]
    image = os.environ.get('ROXYWI_TEST_IMAGE', 'roxy-wi:test')
    network, volume, broker = prefix + '-net', prefix + '-data', prefix + '-broker'
    containers, resources = [], []
    environment = {
        'ROXYWI_DEPLOYMENT_MODE': 'compose', 'ROXYWI_DATABASE_ENGINE': database,
        'ROXYWI_DB_PATH': '/var/lib/roxy-wi/roxy-wi.db',
        'ROXYWI_SECRET_KEY': 'shutdown-test-secret-with-at-least-32-characters',
        'ROXYWI_SECRET_PHRASE': 'E2nCq8NnECvPQ5zUQntL_-Nt-qBncYkrEmMkYGzVpyM=',
        'ROXYWI_JWT_ALGORITHM': 'HS256', 'ROXYWI_BOOTSTRAP_ADMIN_PASSWORD': 'ShutdownTestPassword!',
        'ROXYWI_RABBITMQ_HOST': broker, 'ROXYWI_RABBITMQ_USER': 'test',
        'ROXYWI_RABBITMQ_PASSWORD': 'shutdown-test-password', 'ROXYWI_RABBITMQ_VHOST': '/',
        'ROXYWI_PROCESS_HEARTBEAT_INTERVAL': '5',
    }
    if database == 'mysql':
        environment.update(ROXYWI_MYSQL_HOST=prefix + '-database', ROXYWI_MYSQL_PORT='3306',
                           ROXYWI_MYSQL_DB='roxywi', ROXYWI_MYSQL_USER='test',
                           ROXYWI_MYSQL_PASSWORD=uuid4().hex)
    common = ['--init', '--network', network, '--volume', f'{volume}:/var/lib/roxy-wi',
              '--volume', f'{Path(__file__).resolve()}:/shutdown_test.py:ro',
              '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,mode=1777']
    for key, value in environment.items():
        common += ['--env', f'{key}={value}']

    def start(name, *args):
        docker('run', '--detach', '--name', name, *args)
        containers.append(name)

    def inspect(name):
        return json.loads(docker('exec', name, 'python', '/shutdown_test.py', '--fixture', 'inspect').stdout)

    def files(name):
        return inspect(name)['files']

    def exited(name):
        return docker('inspect', '--format', '{{.State.Status}}', name).stdout.strip() == 'exited'

    def finish(name):
        wait_for(lambda: exited(name), 'graceful exit', timeout=30)
        assert docker('inspect', '--format', '{{.State.ExitCode}}', name).stdout.strip() == '0'

    try:
        docker('network', 'create', network)
        resources.append(('network', network))
        docker('volume', 'create', volume)
        resources.append(('volume', volume))
        if database == 'mysql':
            db_volume, db_name = prefix + '-mysql', environment['ROXYWI_MYSQL_HOST']
            docker('volume', 'create', db_volume)
            resources.append(('volume', db_volume))
            start(db_name, '--network', network, '--volume', f'{db_volume}:/var/lib/mysql',
                  '--env', 'MARIADB_DATABASE=roxywi', '--env', 'MARIADB_USER=test',
                  '--env', 'MARIADB_PASSWORD=' + environment['ROXYWI_MYSQL_PASSWORD'],
                  '--env', 'MARIADB_ROOT_PASSWORD=' + uuid4().hex, 'mariadb:11.4')
            wait_for(lambda: docker('exec', db_name, 'healthcheck.sh', '--connect', '--innodb_initialized',
                                    check=False).returncode == 0, 'MariaDB readiness')
        start(broker, '--network', network, '--env', 'RABBITMQ_DEFAULT_USER=test',
              '--env', 'RABBITMQ_DEFAULT_PASS=shutdown-test-password', 'rabbitmq:4')
        wait_for(lambda: docker('exec', '--user', 'rabbitmq', broker, 'rabbitmq-diagnostics', '-q', 'ping',
                                check=False).returncode == 0, 'RabbitMQ readiness')
        docker('run', '--rm', '--no-healthcheck', *common, image, 'migrate')
        docker('run', '--rm', '--no-healthcheck', *common, '--entrypoint', 'python', image, '/shutdown_test.py', '--fixture', 'seed')
        for role in ('operations', 'service-events', 'scheduler'):
            name = prefix + '-' + role
            start(name, *common, '--entrypoint', 'python', image, '/shutdown_test.py', '--fixture', role)
            wait_for(lambda: f'{role}-started-1' in files(name), f'{role}: first job running')
            docker('kill', '--signal=TERM', name)
            wait_for(lambda: any(item['status'] == 'draining' for item in inspect(name)['health']), f'{role}: draining')
            assert docker('exec', name, 'python', 'roxy_wi.py', 'healthcheck', '--role', role, '--check', 'live').returncode == 0
            assert docker('exec', name, 'python', 'roxy_wi.py', 'healthcheck', '--role', role, '--check', 'ready', check=False).returncode == 1
            docker('kill', '--signal=TERM', name)  # Repeated termination is harmless.
            current = files(name)
            assert f'{role}-started-2' not in current and f'{role}-done-1' not in current
            assert 'scheduler-unexpected' not in current
            docker('exec', name, 'python', '/shutdown_test.py', '--fixture', f'release-{role}')
            finish(name)
            if role != 'scheduler':
                docker('start', name)
                wait_for(lambda: f'{role}-done-2' in files(name), f'{role}: pending delivery recovered')
                docker('kill', '--signal=TERM', name)
                finish(name)
            print(f'{role}: finishes in-flight work, rejects new work, exits cleanly')
        web, client = prefix + '-web', prefix + '-http-client'
        start(web, *common, '--env', 'ROXYWI_WEB_WORKERS=1',
              '--env', 'GUNICORN_CMD_ARGS=--config /shutdown_test.py', image, 'web')
        wait_for(lambda: docker('exec', web, 'python', 'roxy_wi.py', 'healthcheck', '--role', 'web',
                                 '--check', 'live', check=False).returncode == 0, 'web readiness')
        start(client, *common, '--no-healthcheck', '--env', f'SHUTDOWN_WEB_HOST={web}',
              '--entrypoint', 'python', image, '/shutdown_test.py', '--fixture', 'web-request')
        wait_for(lambda: 'web-started-1' in files(web), 'HTTP request in progress')
        docker('kill', '--signal=TERM', web)
        assert not exited(web), 'Web exited before completing the request'
        docker('exec', web, 'python', '/shutdown_test.py', '--fixture', 'release-web')
        finish(web)
        finish(client)
        print('web: completes the active HTTP request and exits cleanly')
        docker('run', '--rm', '--no-healthcheck', *common, '--entrypoint', 'python', image, '/shutdown_test.py', '--fixture', 'verify')
        print('SIGTERM, repeated SIGTERM, readiness/liveness and queued-work recovery passed.')
    except Exception:
        for name in containers:
            result = docker('logs', '--tail', '50', name, check=False)
            print(f'{name}:\n{result.stdout}\n{result.stderr}')
        raise
    finally:
        for name in reversed(containers):
            result = docker('rm', '--force', '--volumes', name, check=False)
            if result.returncode:
                print(f'Cannot remove test container {name}: {result.stderr}')
        for kind, name in reversed(resources):
            result = docker(kind, 'rm', name, check=False)
            if result.returncode:
                print(f'Cannot remove test {kind} {name}: {result.stderr}')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--fixture':
        fixture(sys.argv[2])
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--database', choices=('sqlite', 'mysql'), default='sqlite')
        main(parser.parse_args().database)
