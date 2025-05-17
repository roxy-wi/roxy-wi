from playhouse.migrate import *
from app.modules.db.db_model import connect, mysql_enable
from peewee import IntegerField, SQL

migrator = connect(get_migrator=1)


def up():
    """Apply the migration."""
    # This migration adds an is_checker column to the udp_balancers table
    try:
        if mysql_enable:
            migrate(
                migrator.add_column('udp_balancers', 'is_checker', IntegerField(default=0)),
            )
        else:
            migrate(
                migrator.add_column('udp_balancers', 'is_checker', IntegerField(constraints=[SQL('DEFAULT 0')])),
            )
    except Exception as e:
        if (e.args[0] == 'duplicate column name: is_checker' or 'column "is_checker" of relation "udp_balancers" already exists'
                or str(e) == '(1060, "Duplicate column name \'is_checker\'")'):
            print('Column already exists')
        else:
            raise e


def down():
    """Roll back the migration."""
    # This migration removes the is_checker column from the udp_balancers table
    try:
        migrate(
            migrator.drop_column('udp_balancers', 'is_checker'),
        )
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e
