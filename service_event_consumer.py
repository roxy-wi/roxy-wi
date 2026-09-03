"""Consume events and worker heartbeats from independently deployed services."""

from app.modules.integrations.rabbitmq_consumer import run_consumer


if __name__ == '__main__':
    run_consumer()
