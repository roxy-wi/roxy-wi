from __future__ import annotations

from app.modules.db.db_model import BaseModel
from app.modules.db.migration_manager import Migration, get_migration_files


def database_schema_ready() -> tuple[bool, str]:
    database = BaseModel._meta.database
    try:
        with database.connection_context():
            database.execute_sql('SELECT 1')
            tables = set(database.get_tables())
            required_tables = {'user', 'servers', 'settings', 'migrations'}
            missing_tables = sorted(required_tables - tables)
            if missing_tables:
                return False, f'missing tables: {", ".join(missing_tables)}'
            applied = {migration.name for migration in Migration.select(Migration.name)}
            pending = sorted(set(get_migration_files()) - applied)
            if pending:
                return False, f'pending migrations: {len(pending)}'
    except Exception as error:
        return False, str(error)
    return True, 'ready'
