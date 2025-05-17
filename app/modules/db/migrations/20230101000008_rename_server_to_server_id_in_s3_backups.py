from playhouse.migrate import *
from app.modules.db.db_model import connect

migrator = connect(get_migrator=1)

def up():
    """Apply the migration."""
    # This migration renames the server column to server_id in the s3_backups table
    try:
        migrate(
            migrator.rename_column('s3_backups', 'server', 'server_id')
        )
    except Exception as e:
        if e.args[0] == 'no such column: "server"' or str(e) == '(1060, no such column: "server")':
            print("Column already renamed")
        elif e.args[0] == "'bool' object has no attribute 'sql'":
            print("Column already renamed")
        else:
            raise e

def down():
    """Roll back the migration."""
    # This migration renames the server_id column back to server in the s3_backups table
    try:
        migrate(
            migrator.rename_column('s3_backups', 'server_id', 'server')
        )
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e