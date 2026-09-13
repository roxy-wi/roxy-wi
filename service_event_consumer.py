"""Consume events and worker heartbeats from independently deployed services."""

import os

os.environ['ROXYWI_PROCESS_ROLE'] = 'service-events'

from app.modules.integrations.rabbitmq_consumer import run_consumer


def main() -> None:
    run_consumer()


if __name__ == '__main__':
    main()
