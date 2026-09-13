from __future__ import annotations

import os
from dataclasses import dataclass

import pika

import app.modules.db.sql as sql


@dataclass(frozen=True)
class RabbitConnectionSettings:
    host: str
    port: int
    vhost: str
    username: str
    password: str

    @classmethod
    def load(cls) -> 'RabbitConnectionSettings':
        """Load the existing Roxy-WI RabbitMQ settings with optional container overrides."""
        def setting(env_name: str, db_name: str, default: str = '') -> str:
            if env_name in os.environ:
                return os.environ[env_name]
            database_value = sql.get_setting(db_name)
            return str(database_value if database_value is not None else default)

        return cls(
            host=setting('ROXYWI_RABBITMQ_HOST', 'rabbitmq_host', '127.0.0.1'),
            port=int(setting('ROXYWI_RABBITMQ_PORT', 'rabbitmq_port', '5672')),
            vhost=setting('ROXYWI_RABBITMQ_VHOST', 'rabbitmq_vhost', '/'),
            username=setting('ROXYWI_RABBITMQ_USER', 'rabbitmq_user', 'roxy-wi'),
            password=setting('ROXYWI_RABBITMQ_PASSWORD', 'rabbitmq_password'),
        )

    def parameters(self) -> pika.ConnectionParameters:
        return pika.ConnectionParameters(
            host=self.host,
            port=self.port,
            virtual_host=self.vhost,
            credentials=pika.PlainCredentials(self.username, self.password),
            heartbeat=30,
            blocked_connection_timeout=30,
        )
