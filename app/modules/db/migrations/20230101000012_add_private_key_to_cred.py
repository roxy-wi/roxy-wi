from playhouse.migrate import *
from app.modules.db.db_model import connect, TextField

migrator = connect(get_migrator=1)


def up():
    """Apply the migration."""
    # This migration adds a private_key column to the cred table
    try:
        migrate(
            migrator.add_column('cred', 'private_key', TextField(null=True)),
        )
    except Exception as e:
        if (e.args[0] == 'duplicate column name: private_key' or 'column "private_key" of relation "cred" already exists'
                or str(e) == '(1060, "Duplicate column name \'private_key\'")'):
            print('Column already exists')
        else:
            raise e


def down():
    """Roll back the migration."""
    # This migration removes the private_key column from the cred table
    try:
        migrate(
            migrator.drop_column('cred', 'private_key'),
        )
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e
