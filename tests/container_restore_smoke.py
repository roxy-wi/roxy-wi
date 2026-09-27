"""Cold restore of application files, SQLite/MariaDB and a durable RabbitMQ message.

Uses disposable Docker resources and the production image (ROXYWI_TEST_IMAGE).
Optionally import a stopped, synthetic native-upgrade fixture with --source-directory;
pass its encryption key in ROXYWI_REHEARSAL_SECRET_PHRASE. Never supply real data.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4


def docker(*args, check=True):
    result = subprocess.run(['docker', *args], text=True, capture_output=True, timeout=240)
    if check and result.returncode:
        raise RuntimeError(f'Docker {args[0]} failed: {result.stderr}')
    return result


def wait_for(callback, description):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if callback():
            return
        time.sleep(2)
    raise AssertionError(f'Timed out: {description}')


def main(source_directory=None, database='sqlite', source_dump=None):
    if source_dump and (database != 'mysql' or not source_directory):
        raise ValueError('--source-dump requires --database mysql and --source-directory')
    if database == 'mysql' and source_directory and not source_dump:
        raise ValueError('Importing MariaDB requires both application files and a SQL dump')
    if source_dump:
        source_dump = Path(source_dump).resolve(strict=True)
    if source_directory:
        source_directory = Path(source_directory).resolve(strict=True)
        if not (source_directory / 'rehearsal-manifest.json').is_file():
            raise RuntimeError('Only synthetic upgrade fixtures can be imported')
        if not os.environ.get('ROXYWI_REHEARSAL_SECRET_PHRASE'):
            raise RuntimeError('Import requires the original fixture encryption key')
    prefix = 'roxywi-restore-' + uuid4().hex[:10]
    image = os.environ.get('ROXYWI_TEST_IMAGE', 'roxy-wi:test')
    network = prefix + '-net'
    volumes, containers = [], []
    environment = {
        'ROXYWI_DEPLOYMENT_MODE': 'compose', 'ROXYWI_DATABASE_ENGINE': database,
        'ROXYWI_DB_PATH': '/var/lib/roxy-wi/roxy-wi.db',
        'ROXYWI_SECRET_PHRASE': os.environ.get('ROXYWI_REHEARSAL_SECRET_PHRASE') or base64.urlsafe_b64encode(os.urandom(32)).decode(),
        'ROXYWI_JWT_ALGORITHM': 'HS256', 'ROXYWI_REHEARSAL': '1',
        'ROXYWI_BOOTSTRAP_ADMIN_PASSWORD': 'RestoreFixturePassword!',
        'ROXYWI_RABBITMQ_HOST': 'restore-broker', 'ROXYWI_RABBITMQ_USER': 'restore-fixture',
        'ROXYWI_RABBITMQ_PASSWORD': uuid4().hex, 'ROXYWI_RABBITMQ_VHOST': '/',
        'ROXYWI_WEB_WORKERS': '1', 'ROXYWI_WEB_THREADS': '2',
        'ROXYWI_PROCESS_HEARTBEAT_INTERVAL': '5',
    }
    if database == 'mysql':
        environment.update(ROXYWI_MYSQL_HOST='restore-database', ROXYWI_MYSQL_PORT='3306',
                           ROXYWI_MYSQL_DB='roxywi', ROXYWI_MYSQL_USER='restore-fixture',
                           ROXYWI_MYSQL_PASSWORD=uuid4().hex)
    database_password = uuid4().hex
    fixture = Path(__file__).parent / 'fixtures' / 'upgrade_state.py'
    # The complete environment is preserved across both starts. Do not log it.
    env_args = [part for key, value in environment.items() for part in ('--env', f'{key}={value}')]

    def volume(suffix):
        name = prefix + '-' + suffix
        docker('volume', 'create', name)
        volumes.append(name)
        return name

    def mount(name, path, readonly=False):
        return ['--mount', f'type=volume,source={name},target={path},volume-nocopy' + (',readonly' if readonly else '')]

    def app_args(data):
        return ['--init', '--network', network, *mount(data, '/var/lib/roxy-wi'),
                '--volume', f'{fixture.resolve()}:/upgrade_state.py:ro', '--read-only',
                '--tmpfs', '/tmp:rw,nosuid,nodev,mode=1777', *env_args]

    def fixture_run(data, action, check=True, extra=()):
        return docker('run', '--rm', *app_args(data), *extra, '--entrypoint', 'python', image,
                      '/upgrade_state.py', action, check=check)

    def start(name, *args):
        docker('run', '--detach', '--name', name, *args)
        containers.append(name)

    def start_broker(data, suffix):
        name = prefix + '-' + suffix
        start(name, '--network', network, '--network-alias', 'restore-broker',
              '--hostname', 'restore-broker', *mount(data, '/var/lib/rabbitmq'),
              '--env', 'RABBITMQ_DEFAULT_USER=' + environment['ROXYWI_RABBITMQ_USER'],
              '--env', 'RABBITMQ_DEFAULT_PASS=' + environment['ROXYWI_RABBITMQ_PASSWORD'],
              '--env', 'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS=+S 1:1 +A 4', 'rabbitmq:4')
        wait_for(lambda: docker('exec', '--user', 'rabbitmq', name, 'rabbitmq-diagnostics', '-q', 'ping',
                                check=False).returncode == 0, 'RabbitMQ ready')
        return name

    def start_database(data, backup, suffix):
        name = prefix + '-' + suffix
        start(name, '--network', network, '--network-alias', 'restore-database',
              *mount(data, '/var/lib/mysql'), *mount(backup, '/backup'),
              '--env', 'MARIADB_DATABASE=roxywi',
              '--env', 'MARIADB_USER=' + environment['ROXYWI_MYSQL_USER'],
              '--env', 'MARIADB_PASSWORD=' + environment['ROXYWI_MYSQL_PASSWORD'],
              '--env', 'MARIADB_ROOT_PASSWORD=' + database_password, 'mariadb:11.4')
        wait_for(lambda: docker('exec', name, 'healthcheck.sh', '--connect', '--innodb_initialized',
                                check=False).returncode == 0, 'MariaDB ready')
        return name

    def import_database(name):
        docker('exec', name, 'sh', '-ec',
               'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb --user=root < /backup/database.sql')

    def probe(name, check='ready'):
        return docker('exec', name, 'python', 'roxy_wi.py', 'healthcheck', '--check', check,
                      check=False).returncode == 0

    def roles(data, suffix):
        names = []
        for role in ('web', 'scheduler', 'service-events', 'operations'):
            name = prefix + '-' + suffix + '-' + role
            start(name, *app_args(data), image, role)
            names.append(name)
        wait_for(lambda: all(probe(name) for name in names), 'all restored roles ready')
        return names

    def broker_message(data, consume=False):
        code = '''
import pika
from app.modules.operations.queue import OperationQueueSettings
connection = pika.BlockingConnection(OperationQueueSettings.load().parameters())
try:
    channel = connection.channel()
    channel.queue_declare(queue='restore-sentinel', durable=True)
    if CONSUME:
        method, properties, body = channel.basic_get('restore-sentinel', auto_ack=False)
        assert method is not None and body == b'cold-restore-sentinel'
        channel.basic_ack(method.delivery_tag)
        assert channel.basic_get('restore-sentinel', auto_ack=True)[0] is None
    else:
        channel.confirm_delivery()
        channel.basic_publish('', 'restore-sentinel', b'cold-restore-sentinel',
                              properties=pika.BasicProperties(delivery_mode=2), mandatory=True)
finally:
    connection.close()
'''.replace('CONSUME', repr(consume))
        docker('run', '--rm', *app_args(data), '--entrypoint', 'python', image, '-c', code)

    try:
        docker('network', 'create', network)
        original, original_broker, backup = volume('original'), volume('original-broker'), volume('backup')
        if database == 'mysql':
            original_database = volume('original-database')
            database_container = start_database(original_database, backup, 'database-before')
            if source_dump:
                docker('run', '--rm', '--user', '0', '--volume', f'{source_dump}:/source.sql:ro',
                       *mount(backup, '/backup'), '--entrypoint', 'sh', image, '-ec',
                       'umask 077; cp /source.sql /backup/database.sql; chmod 600 /backup/database.sql')
                import_database(database_container)
        # Root is used only for offline archive/ownership operations.
        docker('run', '--rm', '--user', '0', *mount(original, '/state'), '--entrypoint', 'chown',
               image, '10001:10001', '/state')
        if source_directory:
            docker('run', '--rm', '--user', '0', '--volume', f'{source_directory}:/source:ro',
                   *mount(original, '/state'), '--entrypoint', 'sh', image, '-ec',
                   'cp -a /source/. /state/; chown -R 10001:10001 /state')
        docker('run', '--rm', *app_args(original), image, 'migrate')
        if not source_directory:
            fixture_run(original, 'seed')
        fixture_run(original, 'verify-restored')
        # Repeat migration against real data: no duplicate schedules or reset accounts.
        docker('run', '--rm', *app_args(original), image, 'migrate')
        fixture_run(original, 'verify-restored')
        broker = start_broker(original_broker, 'broker-before')
        active = roles(original, 'before')
        broker_message(original)
        if database == 'mysql':
            docker('stop', '--time', '60', database_container)
            wait_for(lambda: all(not probe(name) for name in active), 'roles detect MariaDB outage')
            assert all(probe(name, 'live') for name in active), 'Database outage failed liveness'
            docker('start', database_container)
            wait_for(lambda: all(probe(name) for name in active), 'roles reconnect to MariaDB')
            fixture_run(original, 'verify-restored')
            print('All four roles detected MariaDB outage and recovered without restart.', flush=True)
        print('Source state verified; all four roles ready and a durable message queued.', flush=True)
        docker('stop', '--time', '150', *active)
        docker('stop', '--time', '90', broker)
        stopped = [*active, broker]
        if database == 'mysql':
            # All application writers are stopped, so SQL and application files
            # describe the same state. Never copy a running MariaDB data directory.
            docker('exec', database_container, 'sh', '-ec',
                   'umask 077; MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb-dump --user=root '
                   '--single-transaction --routines --events --triggers --hex-blob '
                   '--databases roxywi > /backup/database.sql')
            docker('stop', '--time', '60', database_container)
            stopped.append(database_container)
        for name in stopped:
            assert docker('inspect', '--format', '{{.State.ExitCode}}', name).stdout.strip() == '0', name
            docker('rm', '--volumes', name)
            containers.remove(name)
        docker('run', '--rm', '--user', '0', *mount(original, '/source', True),
               *mount(original_broker, '/broker', True), *mount(backup, '/backup'),
               '--entrypoint', 'sh', image, '-ec',
               'umask 077; tar --numeric-owner -cpf /backup/app.tar -C /source .; '
               'tar --numeric-owner -cpf /backup/broker.tar -C /broker .; '
               'cd /backup; sha256sum app.tar broker.tar' +
               (' database.sql' if database == 'mysql' else '') + ' > SHA256SUMS')
        # Remove the originals before restoration, proving there is no hidden reuse.
        originals = [original, original_broker]
        if database == 'mysql':
            originals.append(original_database)
        for name in originals:
            docker('volume', 'rm', name)
            volumes.remove(name)
        print('Consistent backups created; all original state volumes removed.', flush=True)
        restored, restored_broker = volume('restored'), volume('restored-broker')
        docker('run', '--rm', '--user', '0', *mount(restored, '/state'),
               *mount(restored_broker, '/broker'), *mount(backup, '/backup', True),
               '--entrypoint', 'sh', image, '-ec',
               'cd /backup; sha256sum --check SHA256SUMS; '
               'tar --numeric-owner -xpf app.tar -C /state; tar --numeric-owner -xpf broker.tar -C /broker')
        if database == 'mysql':
            restored_database = volume('restored-database')
            database_container = start_database(restored_database, backup, 'database-after')
            import_database(database_container)
        fixture_run(restored, 'verify-restored')
        wrong_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        rejected = fixture_run(restored, 'verify-restored', check=False,
                               extra=('--env', 'ROXYWI_SECRET_PHRASE=' + wrong_key))
        assert rejected.returncode != 0 and 'Cannot decrypt password' in rejected.stderr, 'Wrong key was accepted'
        print('Restored files and encrypted state verified; wrong key rejected.', flush=True)
        docker('run', '--rm', *app_args(restored), image, 'migrate')
        start_broker(restored_broker, 'broker-after')
        roles(restored, 'after')
        broker_message(restored, consume=True)
        fixture_run(restored, 'verify-restored')
        print(f'Cold restore passed ({database}): original volumes removed, files and encrypted state preserved, '
              'wrong key rejected, durable message recovered and all four roles ready.')
    except Exception:
        for name in containers:
            logs = docker('logs', '--tail', '30', name, check=False)
            print(f'{name}:\n{logs.stdout}\n{logs.stderr}', file=sys.stderr)
        raise
    finally:
        cleanup_failed = []
        for name in reversed(containers):
            result = docker('rm', '--force', '--volumes', name, check=False)
            if result.returncode:
                cleanup_failed.append(result.stderr)
        for name in reversed(volumes):
            result = docker('volume', 'rm', name, check=False)
            if result.returncode:
                cleanup_failed.append(result.stderr)
        result = docker('network', 'rm', network, check=False)
        if result.returncode:
            cleanup_failed.append(result.stderr)
        if cleanup_failed:
            print('Restore test cleanup failed: ' + '\n'.join(cleanup_failed), file=sys.stderr)
            if sys.exc_info()[0] is None:
                raise RuntimeError('Disposable restore resources could not be removed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-directory')
    parser.add_argument('--database', choices=('sqlite', 'mysql'), default='sqlite')
    parser.add_argument('--source-dump')
    args = parser.parse_args()
    main(args.source_directory, args.database, args.source_dump)
