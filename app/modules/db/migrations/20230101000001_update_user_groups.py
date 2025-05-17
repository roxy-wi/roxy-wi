from playhouse.migrate import *
from app.modules.db.db_model import connect, User, UserGroups

migrator = connect(get_migrator=1)

def up():
    """Apply the migration."""
    # This migration updates user groups
    # It inserts user_id and group_id from User table into UserGroups table
    try:
        UserGroups.insert_from(
            User.select(User.user_id, User.group_id), fields=[UserGroups.user_id, UserGroups.user_group_id]
        ).on_conflict_ignore().execute()
    except Exception as e:
        if e.args[0] == 'duplicate column name: haproxy' or str(e) == '(1060, "Duplicate column name \'haproxy\'")':
            print('Migration already applied')
        else:
            raise e

def down():
    """Roll back the migration."""
    # This migration adds data, not schema changes, so rolling back would mean deleting data
    # This is potentially dangerous, so we'll just pass
    pass