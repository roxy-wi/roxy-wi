"""Exercise the real CLI in a fresh interpreter, without pytest's TESTING bootstrap."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=['package', 'compose', 'kubernetes'])
def command_environment(tmp_path, request):
    config = tmp_path / 'roxy-wi.cfg'
    config.write_text(f'[main]\nlib_path = {tmp_path.as_posix()}\n', encoding='utf-8')
    return {
        **{key: value for key, value in os.environ.items() if not key.startswith('ROXYWI_')},
        'ROXYWI_CONFIG_FILE': str(config),
        'ROXYWI_DATABASE_ENGINE': 'sqlite',
        'ROXYWI_DB_PATH': str(tmp_path / 'roxy-wi.db'),
        'ROXYWI_TESTING': '0',
        'ROXYWI_DEPLOYMENT_MODE': request.param,
        # Even stale service settings must not start jobs or implicit migrations
        # in a dedicated database command.
        'ROXYWI_SCHEDULER_ENABLED': '1',
        'ROXYWI_AUTO_MIGRATE': '1' if request.param == 'package' else '0',
        'ROXYWI_DATABASE_WAIT_TIMEOUT': '1',
        'ROXYWI_LOG_CONSOLE': '1',
        'ROXYWI_LOG_FILE_ENABLED': '0',
        'ROXYWI_SECRET_KEY': 'bootstrap-test-secret-key-with-at-least-32-characters',
        'ROXYWI_SECRET_PHRASE': 'E2nCq8NnECvPQ5zUQntL_-Nt-qBncYkrEmMkYGzVpyM=',
        'ROXYWI_JWT_ALGORITHM': 'HS256',
        'ROXYWI_BOOTSTRAP_ADMIN_PASSWORD': 'BootstrapTestPassword!',
    }


def run_command(role, environment):
    # Check side effects after running the real entry point, including failures.
    code = '''
import runpy
import sys
import threading
sys.argv = ['roxy_wi.py', sys.argv[1]]
try:
    runpy.run_path('roxy_wi.py', run_name='__main__')
finally:
    import app
    assert not app.scheduler.running
    assert not app.app.blueprints
    assert 'app.login' not in sys.modules
    assert 'app.jobs' not in sys.modules
    assert 'app.modules.process_heartbeat' not in sys.modules
    assert not any(name.startswith('app.routes.') for name in sys.modules)
    assert not any(t.name.endswith('-heartbeat') for t in threading.enumerate())
'''
    return subprocess.run([sys.executable, '-c', code, role], cwd=PROJECT_ROOT,
                          env=environment, capture_output=True, text=True, timeout=30)


def test_migrate_bootstraps_fresh_production_database_and_is_repeatable(command_environment):
    database = command_environment['ROXYWI_DB_PATH']
    assert not Path(database).exists()
    first = run_command('migrate', command_environment)
    assert first.returncode == 0, first.stdout + first.stderr
    assert 'No pending migrations' not in first.stdout  # Initialized exactly once.
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM settings WHERE param='time_zone'").fetchone() == ('UTC',)
        password = connection.execute("SELECT password FROM user WHERE username='admin'").fetchone()
        assert password is not None
        migrations = connection.execute('SELECT name, applied_at FROM migrations ORDER BY name').fetchall()
        assert migrations
        connection.execute("UPDATE settings SET value='Europe/Moscow' WHERE param='time_zone'")

    second = run_command('migrate', command_environment)
    assert second.returncode == 0, second.stdout + second.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM settings WHERE param='time_zone'").fetchone() == ('Europe/Moscow',)
        assert connection.execute("SELECT password FROM user WHERE username='admin'").fetchone() == password
        assert connection.execute('SELECT name, applied_at FROM migrations ORDER BY name').fetchall() == migrations


def test_wait_on_empty_database_does_not_initialize_it(command_environment):
    command_environment['ROXYWI_AUTO_MIGRATE'] = '1'
    result = run_command('wait-for-database', command_environment)
    assert result.returncode != 0
    assert 'Database schema did not become ready' in result.stderr
    assert 'no such table: settings' not in result.stderr
    with sqlite3.connect(command_environment['ROXYWI_DB_PATH']) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


def test_wait_detects_pending_migrations_without_applying_them(command_environment):
    migrated = run_command('migrate', command_environment)
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    ready = run_command('wait-for-database', command_environment)
    assert ready.returncode == 0, ready.stdout + ready.stderr
    with sqlite3.connect(command_environment['ROXYWI_DB_PATH']) as connection:
        latest = connection.execute('SELECT name FROM migrations ORDER BY name DESC LIMIT 1').fetchone()[0]
        connection.execute('DELETE FROM migrations WHERE name=?', (latest,))

    command_environment['ROXYWI_AUTO_MIGRATE'] = '1'
    pending = run_command('wait-for-database', command_environment)
    assert pending.returncode != 0
    assert 'pending migrations: 1' in pending.stderr
    with sqlite3.connect(command_environment['ROXYWI_DB_PATH']) as connection:
        assert connection.execute('SELECT name FROM migrations WHERE name=?', (latest,)).fetchone() is None


def test_migrate_propagates_database_connection_failure(command_environment, tmp_path):
    command_environment['ROXYWI_DB_PATH'] = str(tmp_path)  # Directory, not a database file.
    result = run_command('migrate', command_environment)
    assert result.returncode != 0
    assert 'unable to open database file' in result.stderr
