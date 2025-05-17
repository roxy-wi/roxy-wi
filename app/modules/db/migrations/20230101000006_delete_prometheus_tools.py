from playhouse.migrate import *
from app.modules.db.db_model import connect, RoxyTool

migrator = connect(get_migrator=1)

def up():
    """Apply the migration."""
    # This migration deletes rows from the RoxyTool table
    try:
        RoxyTool.delete().where(RoxyTool.name == 'prometheus').execute()
        RoxyTool.delete().where(RoxyTool.name == 'grafana-server').execute()
    except Exception as e:
        print(f"Error applying migration: {str(e)}")
        raise e

def down():
    """Roll back the migration."""
    # This migration adds back the deleted rows to the RoxyTool table
    try:
        RoxyTool.insert(
            name='prometheus',
            current_version='1.0',
            new_version='1.0',
            is_roxy=0,
            desc='Prometheus monitoring system'
        ).on_conflict_ignore().execute()
        
        RoxyTool.insert(
            name='grafana-server',
            current_version='1.0',
            new_version='1.0',
            is_roxy=0,
            desc='Grafana visualization tool'
        ).on_conflict_ignore().execute()
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e