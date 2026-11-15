"""Register Corosync access and the installed-service flag on each server."""
import json

from app.modules.db.db_model import (
    ConfigChange, HaMaintenancePlan, PacemakerCluster, PacemakerEvent, Server,
    Services, User,
)


def up():
    """Preserve existing cluster access and confirmed installations once."""
    database = Server._meta.database
    if 'corosync' not in {column.name for column in database.get_columns('servers')}:
        # Both supported databases can add this constant default directly.
        # Avoid a SQLite table rebuild, which can cascade into child records.
        database.execute_sql('ALTER TABLE servers ADD COLUMN corosync INTEGER NOT NULL DEFAULT 0')
    with database.atomic():
        existing = Services.get_or_none(Services.service_id == 7)
        if existing is not None:
            if existing.slug != 'corosync':
                raise RuntimeError('Service ID 7 is already assigned to another service')
            return
        for user in User.select():
            services = user.user_services.split()
            if '5' in services and '7' not in services:
                User.update(user_services=' '.join([*services, '7'])).where(User.user_id == user.user_id).execute()
        for cluster in PacemakerCluster.select():
            installed = json.loads(cluster.corosync_settings).get('adopted') or PacemakerEvent.select().where(
                (PacemakerEvent.cluster == cluster.id) & (PacemakerEvent.action == 'bootstrap')
                & (PacemakerEvent.status == 'completed')).exists()
            if installed:
                ids = [member['server_id'] for member in json.loads(cluster.servers)]
                Server.update(corosync=1).where(
                    Server.server_id.in_(ids) & (Server.group_id == str(cluster.group_id))
                    & (Server.type_ip == 0)).execute()
        ConfigChange.update(service='corosync').where(ConfigChange.id.in_(
            HaMaintenancePlan.select(HaMaintenancePlan.change_id).where(HaMaintenancePlan.provider == 'pacemaker')
        ) & (ConfigChange.action == 'ha-maintenance')).execute()
        Services.create(service_id=7, service='Corosync / Pacemaker', slug='corosync')


def down():
    """Retain explicit service permissions and installation metadata."""
    raise RuntimeError('Corosync permissions and server metadata must be retained')
