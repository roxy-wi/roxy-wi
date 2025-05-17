from playhouse.migrate import *
from app.modules.db.db_model import connect, mysql_enable
from peewee import IntegerField, SQL

migrator = connect(get_migrator=1)


def up():
    """Apply the migration."""
    # This migration adds a use_src column to the ha_cluster_vips table
    try:
        if mysql_enable:
            migrate(
                migrator.add_column('ha_cluster_vips', 'use_src', IntegerField(default=0)),
            )
        else:
            migrate(
                migrator.add_column('ha_cluster_vips', 'use_src', IntegerField(constraints=[SQL('DEFAULT 0')])),
            )
    except Exception as e:
        if e.args[0] == 'duplicate column name: use_src' or str(e) == '(1060, "Duplicate column name \'use_src\'")':
            print('Column already exists')
        else:
            raise e


def down():
    """Roll back the migration."""
    # This migration removes the use_src column from the ha_cluster_vips table
    try:
        migrate(
            migrator.drop_column('ha_cluster_vips', 'use_src'),
        )
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e
