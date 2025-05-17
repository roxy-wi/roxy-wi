from playhouse.migrate import *
from app.modules.db.db_model import connect

migrator = connect(get_migrator=1)

def up():
    """Apply the migration."""
    # This migration renames the rhost column to rserver in the backups table
    try:
        migrate(
            migrator.rename_column('backups', 'rhost', 'rserver')
        )
    except Exception as e:
        if e.args[0] == 'no such column: "rhost"' or str(e) == '(1060, no such column: "rhost")':
            print("Column already renamed")
        elif e.args[0] == "'bool' object has no attribute 'sql'":
            print("Column already renamed")
        else:
            raise e

def down():
    """Roll back the migration."""
    # This migration renames the rserver column back to rhost in the backups table
    try:
        migrate(
            migrator.rename_column('backups', 'rserver', 'rhost')
        )
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e