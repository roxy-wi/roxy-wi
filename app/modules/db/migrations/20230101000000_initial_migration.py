from playhouse.migrate import *
from app.modules.db.db_model import connect, Version

migrator = connect(get_migrator=1)


def up():
    """Apply the migration."""
    # Insert version record with version '1.0'
    try:
        Version.insert(version='1.0').execute()
        print("Inserted version record with version '1.0'")
    except Exception as e:
        print(f"Error inserting version record: {e}")


def down():
    """Roll back the migration."""
    # This is the initial migration, so rolling back would mean dropping all tables
    # This is dangerous and not recommended, so we'll just pass
    pass
