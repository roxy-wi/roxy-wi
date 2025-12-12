from playhouse.migrate import *
from app.modules.db.db_model import connect, Version

migrator = connect(get_migrator=1)


def up():
    """Apply the migration."""
    try:
        Version.update(version='8.2.6').execute()
    except Exception as e:
        print(f"Error updating version: {str(e)}")
        raise e


def down():
    """Roll back the migration."""
    try:
        Version.update(version='8.2.5').execute()
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e
