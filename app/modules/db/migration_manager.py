import os
import importlib
from datetime import datetime

from peewee import CharField, DateTimeField, AutoField
from playhouse.migrate import *

from app.modules.db.db_model import BaseModel, connect


# Define the Migration model to track applied migrations
class Migration(BaseModel):
    id = AutoField()
    name = CharField(unique=True)
    applied_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'migrations'


def create_migrations_table():
    """Create the migrations table if it doesn't exist."""
    conn = connect()
    conn.create_tables([Migration], safe=True)


def get_migration_files():
    """Get all migration files from the migrations directory."""
    migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
    migration_files = []

    for filename in os.listdir(migrations_dir):
        if filename.endswith('.py') and not filename.startswith('__'):
            migration_name = filename[:-3]  # Remove .py extension
            migration_files.append(migration_name)

    # Sort migrations by name (which should include a timestamp)
    migration_files.sort()
    return migration_files


def get_applied_migrations():
    """Get all migrations that have been applied."""
    return [m.name for m in Migration.select(Migration.name)]


def apply_migration(migration_name):
    """Apply a single migration."""
    try:
        # Import the migration module
        module = importlib.import_module(f'app.modules.db.migrations.{migration_name}')

        # Apply the migration
        print(f"Applying migration: {migration_name}")
        module.up()

        # Record the migration as applied
        Migration.create(name=migration_name)
        print(f"Migration applied: {migration_name}")
        return True
    except Exception as e:
        print(f"error: applying migration {migration_name}: {str(e)}")
        return False


def rollback_migration(migration_name):
    """Rollback a single migration."""
    try:
        # Import the migration module
        module = importlib.import_module(f'app.modules.db.migrations.{migration_name}')

        # Rollback the migration
        print(f"Rolling back migration: {migration_name}")
        module.down()

        # Remove the migration record
        Migration.delete().where(Migration.name == migration_name).execute()
        print(f"Migration rolled back: {migration_name}")
        return True
    except Exception as e:
        print(f"error: rolling back migration {migration_name}: {str(e)}")
        return False


def migrate():
    """Apply all pending migrations."""
    create_migrations_table()

    # Get all migration files and applied migrations
    migration_files = get_migration_files()
    applied_migrations = get_applied_migrations()

    # Determine which migrations need to be applied
    pending_migrations = [m for m in migration_files if m not in applied_migrations]

    if not pending_migrations:
        print("No pending migrations to apply.")
        return True

    # Apply pending migrations
    success = True
    for migration_name in pending_migrations:
        if not apply_migration(migration_name):
            success = False
            break

    return success


def rollback(steps=1):
    """Rollback the specified number of migrations."""
    create_migrations_table()

    # Get applied migrations in reverse order (most recent first)
    applied_migrations = Migration.select().order_by(Migration.applied_at.desc())

    if not applied_migrations:
        print("No migrations to roll back.")
        return True

    # Rollback the specified number of migrations
    success = True
    for i, migration in enumerate(applied_migrations):
        if i >= steps:
            break

        if not rollback_migration(migration.name):
            success = False
            break

    return success


def create_migration(name):
    """Create a new migration file."""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f"{timestamp}_{name}.py"
    filepath = os.path.join(os.path.dirname(__file__), 'migrations', filename)

    template = """from playhouse.migrate import *
from app.modules.db.db_model import connect, mysql_enable

migrator = connect(get_migrator=1)

def up():
    \"\"\"Apply the migration.\"\"\"
    # Example:
    # migrate(
    #     migrator.add_column('table_name', 'column_name', CharField(default='')),
    # )
    pass

def down():
    \"\"\"Roll back the migration.\"\"\"
    # Example:
    # migrate(
    #     migrator.drop_column('table_name', 'column_name'),
    # )
    pass
"""

    with open(filepath, 'w') as f:
        f.write(template)

    print(f"Created migration file: {filename}")
    return filename


def list_migrations() -> None:
    """
    List all migrations and their status.
    """
    # Get all migration files
    migration_files = get_migration_files()

    # Get applied migrations
    applied_migrations = get_applied_migrations()

    # Print migrations
    print("Migrations:")
    for filename in migration_files:
        migration_name = filename.replace('.py', '')
        status = "Applied" if migration_name in applied_migrations else "Pending"
        print(f"  {migration_name}: {status}")
