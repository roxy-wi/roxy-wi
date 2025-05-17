from playhouse.migrate import *
from app.modules.db.db_model import connect, Version

migrator = connect(get_migrator=1)

def up():
    """Apply the migration."""
    # This migration updates the version in the database to 8.2.0
    try:
        Version.update(version='8.2.0').execute()
    except Exception as e:
        print(f"Error updating version: {str(e)}")
        raise e

def down():
    """Roll back the migration."""
    # This migration sets the version back to 8.1.6
    try:
        Version.update(version='8.1.6').execute()
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e