"""Run the Roxy-WI scheduler as a single dedicated process."""

import os
import threading


os.environ.setdefault('ROXYWI_SCHEDULER_ENABLED', '1')

from app import scheduler  # noqa: E402


if __name__ == '__main__':
    if not scheduler.running:
        raise RuntimeError('The scheduler did not start')
    threading.Event().wait()
