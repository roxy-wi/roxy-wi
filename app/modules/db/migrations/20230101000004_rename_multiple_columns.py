from playhouse.migrate import *
from app.modules.db.db_model import connect

migrator = connect(get_migrator=1)

def up():
    """Apply the migration."""
    # This migration renames multiple columns across different tables
    try:
        migrate(
            migrator.rename_column('telegram', 'groups', 'group_id'),
            migrator.rename_column('slack', 'groups', 'group_id'),
            migrator.rename_column('mattermost', 'groups', 'group_id'),
            migrator.rename_column('pd', 'groups', 'group_id'),
            migrator.rename_column('servers', 'groups', 'group_id'),
            migrator.rename_column('udp_balancers', 'desc', 'description'),
            migrator.rename_column('ha_clusters', 'desc', 'description'),
            migrator.rename_column('cred', 'enable', 'key_enabled'),
            migrator.rename_column('cred', 'groups', 'group_id'),
            migrator.rename_column('servers', 'desc', 'description'),
            migrator.rename_column('servers', 'active', 'haproxy_active'),
            migrator.rename_column('servers', 'metrics', 'haproxy_metrics'),
            migrator.rename_column('servers', 'alert', 'haproxy_alert'),
            migrator.rename_column('servers', 'cred', 'cred_id'),
            migrator.rename_column('servers', 'enable', 'enabled'),
            migrator.rename_column('servers', 'groups', 'group_id'),
            migrator.rename_column('user', 'activeuser', 'enabled'),
            migrator.rename_column('user', 'groups', 'group_id'),
            migrator.rename_column('user', 'role', 'role_id'),
        )
    except Exception as e:
        if e.args[0] == 'no such column: "groups"' or str(e) == '(1060, no such column: "groups")':
            print("Columns already renamed")
        elif e.args[0] == "'bool' object has no attribute 'sql'":
            print("Columns already renamed")
        else:
            raise e

def down():
    """Roll back the migration."""
    # This migration renames columns back to their original names
    try:
        migrate(
            migrator.rename_column('telegram', 'group_id', 'groups'),
            migrator.rename_column('slack', 'group_id', 'groups'),
            migrator.rename_column('mattermost', 'group_id', 'groups'),
            migrator.rename_column('pd', 'group_id', 'groups'),
            migrator.rename_column('servers', 'group_id', 'groups'),
            migrator.rename_column('udp_balancers', 'description', 'desc'),
            migrator.rename_column('ha_clusters', 'description', 'desc'),
            migrator.rename_column('cred', 'key_enabled', 'enable'),
            migrator.rename_column('cred', 'group_id', 'groups'),
            migrator.rename_column('servers', 'description', 'desc'),
            migrator.rename_column('servers', 'haproxy_active', 'active'),
            migrator.rename_column('servers', 'haproxy_metrics', 'metrics'),
            migrator.rename_column('servers', 'haproxy_alert', 'alert'),
            migrator.rename_column('servers', 'cred_id', 'cred'),
            migrator.rename_column('servers', 'enabled', 'enable'),
            migrator.rename_column('servers', 'group_id', 'groups'),
            migrator.rename_column('user', 'enabled', 'activeuser'),
            migrator.rename_column('user', 'group_id', 'groups'),
            migrator.rename_column('user', 'role_id', 'role'),
        )
    except Exception as e:
        print(f"Error rolling back migration: {str(e)}")
        raise e