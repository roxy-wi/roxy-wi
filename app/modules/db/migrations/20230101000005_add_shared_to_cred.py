from playhouse.migrate import *
from app.modules.db.db_model import connect, mysql_enable
from peewee import IntegerField, SQL

migrator = connect(get_migrator=1)

def up():
    """Apply the migration."""
    # This migration adds a shared column to the cred table
    try:
        if mysql_enable:
            migrate(
                migrator.add_column('cred', 'shared', IntegerField(default=0)),
            )
        else:
            migrate(
                migrator.add_column('cred', 'shared', IntegerField(constraints=[SQL('DEFAULT 0')])),
            )
    except Exception as e:
        if e.args[0] == 'duplicate column name: shared' or str(e) == '(1060, "Duplicate column name \'shared\'")':
            print('Column already exists')
        else:
            raise e

def down():
    """Roll back the migration."""
    # This migration removes the shared column from the cred table
    try:
        migrate(
            migrator.drop_column('cred', 'shared'),
        )
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e