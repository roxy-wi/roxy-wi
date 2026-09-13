from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.modules.roxy_wi_tools import GetConfigVar


@dataclass(frozen=True)
class DatabaseSettings:
    """Bootstrap database settings.

    Database connection parameters cannot come from the settings table because
    they are required before that table can be read. Their precedence is ENV,
    then roxy-wi.cfg, then the package-compatible defaults below.
    """

    engine: str
    sqlite_path: str
    mysql_database: str
    mysql_user: str
    mysql_password: str
    mysql_host: str
    mysql_port: int

    @classmethod
    def load(cls, config: GetConfigVar | None = None) -> 'DatabaseSettings':
        config = config or GetConfigVar()
        configured_engine = config.get_config_var('database', 'engine')
        if configured_engine is None:
            mysql_enabled = str(config.get_config_var('mysql', 'enable', '0')).lower()
            configured_engine = 'mysql' if mysql_enabled in {'1', 'true', 'yes', 'on'} else 'sqlite'

        engine = str(configured_engine).strip().lower()
        if engine == 'mariadb':
            engine = 'mysql'
        if engine not in {'sqlite', 'mysql'}:
            raise RuntimeError('Database engine must be sqlite, mysql or mariadb')

        lib_path = config.get_config_var('main', 'lib_path', '/var/lib/roxy-wi')
        sqlite_path = config.get_config_var(
            'sqlite',
            'path',
            str(Path(lib_path) / 'roxy-wi.db'),
        )
        # ROXYWI_DB_PATH is retained for package upgrades and existing tests.
        import os
        if 'ROXYWI_DB_PATH' in os.environ:
            sqlite_path = os.environ['ROXYWI_DB_PATH']

        return cls(
            engine=engine,
            sqlite_path=str(sqlite_path),
            mysql_database=str(config.get_config_var('mysql', 'mysql_db', 'roxywi')),
            mysql_user=str(config.get_config_var('mysql', 'mysql_user', 'roxy-wi')),
            mysql_password=str(config.get_config_var('mysql', 'mysql_password', '')),
            mysql_host=str(config.get_config_var('mysql', 'mysql_host', '127.0.0.1')),
            mysql_port=int(config.get_config_var('mysql', 'mysql_port', '3306')),
        )
