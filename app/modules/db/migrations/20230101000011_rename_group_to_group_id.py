from playhouse.migrate import *
from app.modules.db.db_model import connect

migrator = connect(get_migrator=1)


def up():
    """Apply the migration."""
    # This migration renames the group column to group_id in the settings table
    try:
        migrate(
            migrator.rename_column('settings', 'group', 'group_id'),
        )
    except Exception as e:
        if e.args[0] == 'no such column: "group"' or 'column "group" does not exist' in str(e) or str(e) == '(1060, no such column: "group")':
            print("Column already renamed")
        elif e.args[0] == "'bool' object has no attribute 'sql'":
            print("Column already renamed")
        else:
            raise e


def down():
    """Roll back the migration."""
    # This migration renames the group_id column back to group in the settings table
    try:
        migrate(
            migrator.rename_column('settings', 'group_id', 'group'),
        )
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e
