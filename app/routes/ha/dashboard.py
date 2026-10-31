"""One inventory for registered Keepalived and Corosync/Pacemaker clusters."""
from flask import g, render_template

from app.modules.common import common
from app.modules.db import ha_cluster as ha_sql, service as service_sql
from app.modules.db.db_model import HaCluster, HaClusterVirt, PacemakerCluster, Server
from app.modules.pacemaker import service
from app.modules.roxywi import common as roxywi_common
from app.modules.roxywi.exception import RoxywiInputError, RoxywiResourceNotFound
from app.modules.subscription.access import CHANGE_CENTER, is_feature_available
from app.routes.ha import bp
from app.routes.ha.readiness import access


def cluster_card(cluster: HaCluster | PacemakerCluster, provider: str) -> dict:
    """Read card metadata without contacting cluster members or exposing secrets."""
    card = dict(id=cluster.id, provider=provider, name=cluster.name, description=cluster.description,
                members=[], vips=[], services=[], virtuals=[], error='', status_vip='')
    if provider == 'pacemaker':
        try:
            saved = service.serialize(cluster)
            card['members'] = [dict(id=node['server_id'], name=node['name'], ip=node['address'], master=False)
                               for node in saved['members']]
        except (RoxywiInputError, RoxywiResourceNotFound) as error:
            card['error'] = error.public_message
        installations = service.installation_history(cluster)
        card['installation'] = installations[0].status if installations else None
        return card

    try:
        router_id = ha_sql.get_router_id(cluster.id, default_router=1)
    except RoxywiResourceNotFound:
        router_id = None
    if router_id:
        rows = ha_sql.cluster_slaves_query(cluster.id, router_id).where(Server.group_id == str(cluster.group_id))
        card['members'] = [dict(id=row[0], name=row[1], ip=row[2], master=bool(row[31])) for row in rows.tuples()]
    card['vips'] = list(ha_sql.select_cluster_vips(cluster.id))
    card['status_vip'] = next((vip.vip.split('/')[0] for vip in card['vips'] if vip.router_id_id == router_id), '')
    enabled = {row.service_id for row in ha_sql.select_cluster_services(cluster.id)}
    card['services'] = [row for row in service_sql.select_services() if str(row.service_id) in enabled]
    card['virtuals'] = list(Server.select(Server.hostname, Server.ip).join(
        HaClusterVirt, on=(Server.server_id == HaClusterVirt.virt_id)
    ).where((HaClusterVirt.cluster_id == cluster.id) & (Server.group_id == str(cluster.group_id))))
    return card


@bp.get('/cluster')
@access
def cluster_index():
    subscription = roxywi_common.return_user_subscription()
    return render_template('ha_cluster.html', lang=g.user_params['lang'],
                           is_needed_tool=common.is_tool('ansible'),
                           user_subscription=subscription,
                           maintenance_enabled=is_feature_available(CHANGE_CENTER, subscription))


@bp.get('/cluster/cards')
@access
def cluster_cards():
    cards = [cluster_card(cluster, provider) for provider, model in
             [('keepalived', HaCluster), ('pacemaker', PacemakerCluster)]
             for cluster in model.select().where(model.group_id == g.user_params['group_id'])]
    cards.sort(key=lambda card: (card['name'].casefold(), card['provider'], card['id']))
    return render_template('ajax/ha/clusters.html', cards=cards, lang=g.user_params['lang'])
