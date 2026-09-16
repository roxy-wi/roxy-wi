"""Run the Roxy-WI scheduler as a single dedicated process."""

import os
import threading

import roxy_wi_health as local_health
from apscheduler.executors.pool import ThreadPoolExecutor


# This entry point is the dedicated scheduler by definition. Override a stale
# service-level value instead of silently starting a process without any jobs.
os.environ['ROXYWI_SCHEDULER_ENABLED'] = '1'
os.environ['ROXYWI_PROCESS_ROLE'] = 'scheduler'

from app import scheduler  # noqa: E402


def main() -> None:
    if not scheduler.running:
        raise RuntimeError('The scheduler did not start')
    # A dedicated executor keeps slow DB/network jobs from starving the local
    # watchdog, while a stuck scheduling loop still stops its progress signal.
    scheduler.scheduler.add_executor(ThreadPoolExecutor(1), alias='process-health')
    scheduler.add_job(
        id='process-health', func=local_health.pulse, trigger='interval', seconds=5,
        executor='process-health', max_instances=1, coalesce=True,
    )
    local_health.pulse()
    threading.Event().wait()


if __name__ == '__main__':
    main()
