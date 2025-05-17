from playhouse.migrate import *
from app.modules.db.db_model import connect

migrator = connect(get_migrator=1)

def up():
    """Apply the migration."""
    # This migration renames columns in the backups table
    try:
        migrate(
            migrator.rename_column('backups', 'cred', 'cred_id'),
            migrator.rename_column('backups', 'backup_type', 'type'),
        )
    except Exception as e:
        if e.args[0] == 'no such column: "cred"' or str(e) == '(1060, no such column: "cred")':
            print("Columns already renamed")
        elif e.args[0] == "'bool' object has no attribute 'sql'":
            print("Columns already renamed")
        else:
            raise e

def down():
    """Roll back the migration."""
    # This migration renames columns back to their original names
    try:
        migrate(
            migrator.rename_column('backups', 'cred_id', 'cred'),
            migrator.rename_column('backups', 'type', 'backup_type'),
        )
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e