"""Run the Roxy-WI scheduler as a single dedicated process."""

import os
import signal
import threading

import roxy_wi_health as local_health
from apscheduler.executors.pool import ThreadPoolExecutor


def run_scheduler(scheduler, stop_event: threading.Event) -> None:
    from app.modules.db.db_model import close_database_connection
    from app.modules.process_heartbeat import set_process_heartbeat_status

    if not scheduler.running:
        raise RuntimeError('The scheduler did not start')
    local_health.watch_shutdown(stop_event)
    # A dedicated executor keeps slow DB/network jobs from starving the local
    # watchdog, while a stuck scheduling loop still stops its progress signal.
    scheduler.scheduler.add_executor(ThreadPoolExecutor(1), alias='process-health')
    scheduler.add_job(
        id='process-health', func=local_health.pulse, trigger='interval', seconds=5,
        executor='process-health', max_instances=1, coalesce=True,
    )
    local_health.pulse()
    try:
        stop_event.wait()
    finally:
        # Stop submissions, then finish jobs already accepted by the executors.
        scheduler.pause()
        local_health.draining()
        set_process_heartbeat_status('draining')
        finished = threading.Event()
        errors = []

        def shutdown():
            try:
                scheduler.shutdown(wait=True)
            except Exception as error:
                errors.append(error)
            finally:
                finished.set()

        thread = threading.Thread(target=shutdown, name='scheduler-shutdown')
        thread.start()
        while not finished.wait(1):
            local_health.pulse()
        thread.join()
        close_database_connection()
        if errors:
            raise errors[0]


def main() -> None:
    # Register before importing the application, which can take time. Signal
    # handlers only request a stop, without entering DB, Pika or health locks.
    stop_event = threading.Event()
    def stop(*_args):
        stop_event.set()
    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        # This entry point owns scheduling, regardless of a stale setting.
        os.environ['ROXYWI_SCHEDULER_ENABLED'] = '1'
        os.environ['ROXYWI_PROCESS_ROLE'] = 'scheduler'
        from app import scheduler
        run_scheduler(scheduler, stop_event)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    main()
