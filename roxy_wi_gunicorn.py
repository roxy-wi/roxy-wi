"""Gunicorn worker hooks; loading this config must not initialize Flask."""


def post_worker_init(worker):
    # Import only after the worker has forked and loaded the application.
    from app.routes.health.routes import database_readiness

    worker.roxywi_database_readiness = database_readiness
    database_readiness.start()


def worker_exit(server, worker):
    monitor = getattr(worker, 'roxywi_database_readiness', None)
    if monitor is not None:
        monitor.close()
