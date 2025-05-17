from playhouse.migrate import *
from app.modules.db.db_model import connect

migrator = connect(get_migrator=1)

def up():
    """Apply the migration."""
    # This migration renames the period column to time in the git_setting table
    try:
        migrate(
            migrator.rename_column('git_setting', 'period', 'time')
        )
    except Exception as e:
        if e.args[0] == 'no such column: "period"' or str(e) == '(1060, no such column: "period")':
            print("Column already renamed")
        elif e.args[0] == "'bool' object has no attribute 'sql'":
            print("Column already renamed")
        else:
            raise e

def down():
    """Roll back the migration."""
    # This migration renames the time column back to period in the git_setting table
    try:
        migrate(
            migrator.rename_column('git_setting', 'time', 'period')
        )
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e