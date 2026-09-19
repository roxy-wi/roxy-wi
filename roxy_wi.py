#!/usr/bin/env python3
import argparse
import os
import time


def run_web() -> None:
    from roxy_wi_health import register_web
    register_web()
    bind = os.environ.get('ROXYWI_WEB_BIND', '0.0.0.0:8080')
    workers = os.environ.get('ROXYWI_WEB_WORKERS', '2')
    threads = os.environ.get('ROXYWI_WEB_THREADS', '4')
    timeout = os.environ.get('ROXYWI_WEB_TIMEOUT', '120')
    command = [
        'gunicorn',
        '--bind', bind,
        '--workers', workers,
        '--threads', threads,
        '--timeout', timeout,
        '--access-logfile', '-',
        '--error-logfile', '-',
        'app:app',
    ]
    os.execvp(command[0], command)


def run_migrations() -> None:
    from app import initialize_database
    from app.modules.db.db_model import close_database_connection

    try:
        initialize_database()
    finally:
        close_database_connection()


def wait_for_database() -> None:
    from app.modules.db.db_model import close_database_connection
    from app.modules.db.readiness import database_schema_ready

    timeout = max(1, int(os.environ.get('ROXYWI_DATABASE_WAIT_TIMEOUT', '300')))
    deadline = time.monotonic() + timeout
    detail = 'database unavailable'
    while time.monotonic() < deadline:
        ready, detail = database_schema_ready()
        close_database_connection()
        if ready:
            return
        time.sleep(2)
    raise RuntimeError(f'Database schema did not become ready in {timeout}s: {detail}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Roxy-WI process launcher')
    parser.add_argument(
        'role',
        choices=('web', 'migrate', 'wait-for-database', 'scheduler', 'service-events', 'operations', 'healthcheck',
                 'migrate-backup-cron'),
    )
    parser.add_argument('--role', dest='probe_role', choices=('web', 'scheduler', 'service-events', 'operations'))
    parser.add_argument('--check', choices=('live', 'ready'), default='ready')
    args = parser.parse_args()
    if args.role == 'healthcheck':
        from roxy_wi_health import probe
        healthy, detail = probe(args.check, args.probe_role)
        print(detail)
        raise SystemExit(0 if healthy else 1)
    os.environ['ROXYWI_PROCESS_ROLE'] = args.role

    if args.role == 'web':
        run_web()
    elif args.role == 'migrate':
        run_migrations()
    elif args.role == 'wait-for-database':
        wait_for_database()
    elif args.role == 'migrate-backup-cron':
        from app.modules.service.backup_migration import migrate_legacy_cron
        from app.modules.db.db_model import close_database_connection
        try:
            removed, activated = migrate_legacy_cron()
            print(f'Removed {removed} legacy backup cron entries; activated {activated} schedules')
        finally:
            close_database_connection()
    elif args.role == 'scheduler':
        from scheduler_runner import main as scheduler_main
        scheduler_main()
    elif args.role == 'service-events':
        from service_event_consumer import main as events_main
        events_main()
    else:
        from app.modules.operations.worker import run_worker
        run_worker()


if __name__ == '__main__':
    main()
