from typing import Union

import app.modules.db.server as server_sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.db.service as service_sql
from app.modules.db.db_model import HaCluster, HaClusterRouter, HaClusterVip, HaClusterVirt
import app.modules.roxywi.common as roxywi_common
from app.modules.roxywi.class_models import HAClusterRequest, HAClusterVIP, HAClusterServersRequest
from app.modules.roxywi.exception import RoxywiResourceNotFound


def _get_servers_dict(cluster: Union[HAClusterRequest, HAClusterVIP, HAClusterServersRequest]) -> Union[dict, None]:
    for i, k in cluster.model_dump(mode='json').items():
        if i == 'servers':
            if k is None:
                return None
            servers = k
    return servers


def get_services_dict(cluster: HAClusterRequest) -> dict:
    for i, k in cluster.model_dump(mode='json').items():
        if i == 'services':
            services = k
    return services


def create_cluster(cluster: HAClusterRequest, group_id: int) -> int:
    servers = _get_servers_dict(cluster)
    services = get_services_dict(cluster)

    try:
        cluster_id = ha_sql.create_cluster(cluster.name, cluster.syn_flood, group_id, cluster.description)
        roxywi_common.logging(cluster_id, 'New cluster has been created', keep_history=1, roxywi=1, service='HA cluster')
    except Exception as e:
        raise Exception(f'error: Cannot create new HA cluster: {e}')

    for service, value in services.items():
        if not value['enabled']:
            continue
        try:
            service_id = service_sql.select_service_id_by_slug(service)
            ha_sql.insert_cluster_services(cluster_id, service_id)
            roxywi_common.logging(cluster_id, f'Service {service} has been enabled on the cluster', keep_history=1, roxywi=1, service='HA cluster')
        except Exception as e:
            raise Exception(f'error: Cannot add service {service}: {e}')

    if servers is not None:
        try:
            router_id = ha_sql.create_ha_router(cluster_id, default=1)
        except Exception as e:
            raise Exception(f'error: Cannon create router: {e}')

        _create_or_update_master_slaves_servers(cluster_id, servers, router_id, True)

        if cluster.vip:
            try:
                vip_id = HaClusterVip.insert(cluster_id=cluster_id, router_id=router_id, vip=cluster.vip,
                                             return_master=cluster.return_master).execute()
                roxywi_common.logging(cluster_id, f'New vip {cluster.vip} has been created and added to the cluster',
                                      keep_history=1, roxywi=1, service='HA cluster')
            except Exception as e:
                raise Exception(f'error: Cannon add VIP: {e}')

            if cluster.virt_server and servers is not None:
                add_or_update_virt(cluster, servers, cluster_id, vip_id, group_id)

    return int(cluster_id)


def update_cluster(cluster: HAClusterRequest, cluster_id: int, group_id: int) -> None:
    servers = _get_servers_dict(cluster)
    services = get_services_dict(cluster)

    try:
        ha_sql.update_cluster(cluster_id, cluster.name, cluster.description, cluster.syn_flood)
    except Exception as e:
        raise Exception(f'error: Cannot update HA cluster: {e}')

    if servers:
        try:
            router_id = ha_sql.get_router_id(cluster_id, default_router=1)
        except Exception as e:
            raise Exception(f'error: Cannot get router: {e}')

        try:
            update_slaves(servers, cluster_id, router_id)
        except Exception as e:
            raise Exception(e)

        try:
            update_vip(cluster_id, router_id, cluster, group_id)
        except Exception as e:
            raise Exception(e)

    try:
        ha_sql.delete_cluster_services(cluster_id)
    except Exception as e:
        raise Exception(f'error: Cannot delete old services: {e}')

    for service, value in services.items():
        if not value['enabled']:
            continue
        try:
            service_id = service_sql.select_service_id_by_slug(service)
            ha_sql.insert_cluster_services(cluster_id, service_id)
        except Exception as e:
            raise Exception(f'error: Cannot add service {service}: {e}')

    virts = ha_sql.select_ha_virts(cluster_id)
    if virts:
        for virt in virts:
            try:
                add_or_update_virt(cluster, servers, cluster_id, virt.vip_id, group_id)
            except Exception as e:
                roxywi_common.logging(cluster_id, f'Cannot update cluster virtual server for VIP {virt.vip}: {e}', roxywi=1, service='HA cluster')

    roxywi_common.logging(cluster_id, f'Cluster {cluster.name} has been updated', keep_history=1, roxywi=1, service='HA cluster')


def delete_cluster(cluster_id: int) -> None:
    router_id = ha_sql.get_router_id(cluster_id, default_router=1)
    slaves = ha_sql.select_cluster_slaves(cluster_id, router_id)

    for slave in slaves:
        slave_ip = server_sql.select_server_ip_by_id(slave[0])
        try:
            ha_sql.update_master_server_by_slave_ip(0, slave_ip)
        except Exception as e:
            raise Exception(f'error: Cannot update master on slave {slave_ip}: {e}')

    try:
        HaCluster.delete().where(HaCluster.id == cluster_id).execute()
    except HaCluster.DoesNotExist:
        raise RoxywiResourceNotFound
    roxywi_common.logging(cluster_id, 'Cluster has been deleted', roxywi=1, service='HA cluster')


def update_vip(cluster_id: int, router_id: int, cluster: Union[HAClusterRequest, HAClusterVIP], group_id: int) -> None:
    vip_id = ha_sql.select_clusters_vip_id(cluster_id, router_id)
    servers = _get_servers_dict(cluster)

    try:
        ha_sql.update_ha_cluster_vip(cluster_id, router_id, str(cluster.vip), cluster.return_master, cluster.use_src)
    except Exception as e:
        raise Exception(f'error: Cannot update VIP: {e}')

    for value in servers:
        try:
            ha_sql.update_slave(cluster_id, value['id'], value['eth'], value['master'], router_id)
        except Exception as e:
            s = server_sql.get_server_by_id(value['id'])
            raise Exception(f'error: Cannot add server {s.hostname}: {e}')

    if cluster.virt_server:
        add_or_update_virt(cluster, servers, cluster_id, vip_id, group_id)
    else:
        try:
            if ha_sql.check_ha_virt(vip_id):
                ha_sql.delete_ha_virt(vip_id)
                roxywi_common.logging(cluster_id, f'Cluster virtual server for VIP: {cluster.vip} has been deleted', keep_history=1, roxywi=1, service='HA cluster')
        except Exception as e:
            roxywi_common.logging(cluster_id, f'Cannot delete cluster virtual server for VIP {cluster.vip}: {e}', keep_history=1, roxywi=1, service='HA cluster')

    roxywi_common.logging(cluster_id, f'Cluster VIP {cluster.vip} has been updated', keep_history=1, roxywi=1, service='HA cluster')


def insert_vip(cluster_id: int, cluster: HAClusterVIP, group_id: int) -> int:
    try:
        slaves_count = ha_sql.select_count_cluster_slaves(cluster_id)
        if slaves_count == 0:
            try:
                router_id = ha_sql.create_ha_router(cluster_id, default=1)
            except Exception as e:
                raise Exception(f'error: Cannon create a new default router: {e}')
        else:
            try:
                router_id = ha_sql.create_ha_router(cluster_id)
            except Exception as e:
                raise Exception(f'error: Cannot create new router: {e}')
    except Exception as e:
        raise e

    try:
        vip = cluster.vip
    except Exception as e:
        raise Exception(f'Cannot get VIP: {e}')
    try:
        servers = _get_servers_dict(cluster)
    except Exception as e:
        raise Exception(f'Cannot get servers: {e}')

    try:
        vip_id = HaClusterVip.insert(cluster_id=cluster_id, router_id=router_id, vip=vip, use_src=cluster.use_src, return_master=cluster.return_master).execute()
    except Exception as e:
        raise Exception(f'error: Cannot save VIP {vip}: {e}')

    for value in servers:
        try:
            ha_sql.insert_or_update_slave(cluster_id, value['id'], value['eth'], value['master'], router_id)
        except Exception as e:
            s = server_sql.get_server_by_id(value['id'])
            raise Exception(f'error: Cannot add server {s.hostname}: {e}')

    if cluster.virt_server:
        add_or_update_virt(cluster, servers, cluster_id, vip_id, group_id)

    roxywi_common.logging(cluster_id, f'New cluster VIP: {vip} has been created', keep_history=1, roxywi=1, service='HA cluster')
    return vip_id


def update_slaves(servers: dict, cluster_id: int, router_id: int) -> None:
    all_routers_in_cluster = HaClusterRouter.select(HaClusterRouter.id).where(HaClusterRouter.cluster_id == cluster_id).execute()
    server_ids_from_db = ha_sql.select_cluster_slaves(cluster_id, router_id)
    server_ids = []
    server_ids_from_json = []

    for server in server_ids_from_db:
        server_ids.append(server[0])

    for value in servers:
        server_ids_from_json.append(int(value['id']))

    server_ids_for_deletion = set(server_ids) - set(server_ids_from_json)
    server_ids_for_adding = set(server_ids_from_json) - set(server_ids)

    for router in all_routers_in_cluster:
        for value in servers:
            slave_id = value['id']
            for server_id_add in server_ids_for_adding:
                if int(slave_id) == int(server_id_add):
                    try:
                        ha_sql.insert_or_update_slave(cluster_id, slave_id, value['eth'], value['master'], router)
                    except Exception as e:
                        raise Exception(f'error: Cannot add new slave {value["ip"]}: {e}')

    for o_s in server_ids_for_deletion:
        ha_sql.delete_master_from_slave(o_s)

        try:
            ha_sql.delete_ha_cluster_delete_slave(o_s)
        except Exception as e:
            raise Exception(f'error: Cannot recreate slaves server: {e}')

    _create_or_update_master_slaves_servers(cluster_id, servers, router_id)


def add_or_update_virt(cluster: Union[HAClusterRequest, HAClusterVIP], servers: dict, cluster_id: int, vip_id: int, group_id: int) -> None:
    haproxy = 0
    nginx = 0
    apache = 0
    master_id = None
    vip = str(cluster.vip)

    for value in servers:
        if value['master']:
            master_id = value['id']

    services = ha_sql.select_cluster_services(cluster_id)
    for service in services:
        haproxy = 1 if service.service_id == '1' else 0
        nginx = 1 if service.service_id == '2' else 0
        apache = 1 if service.service_id == '4' else 0

    kwargs = {
        'haproxy': haproxy,
        'nginx': nginx,
        'apache': apache,
        'ip': vip,
    }

    if ha_sql.check_ha_virt(vip_id):
        vip_from_db = ha_sql.select_cluster_vip_by_vip_id(cluster_id, vip_id)
        vip = vip_from_db.vip
        kwargs['ip'] = vip
        try:
            ha_sql.update_ha_virt_ip(vip_id, **kwargs)
            roxywi_common.logging(cluster_id, f'Cluster virtual server for VIP {vip} has been updated', keep_history=1, roxywi=1, service='HA cluster')
        except Exception as e:
            roxywi_common.logging(cluster_id, f'Cannot update cluster virtual server for VIP {vip}: {e}', roxywi=1, service='HA cluster')
    else:
        try:
            server = server_sql.get_server_by_id(master_id)
            c = ha_sql.get_cluster(cluster_id)
            kwargs.setdefault('cred_id', server.cred_id)
            kwargs.setdefault('hostname', f'{vip}-VIP')
            kwargs.setdefault('type_ip', 1)
            kwargs.setdefault('enabled', 1)
            kwargs.setdefault('master', 0)
            kwargs.setdefault('port', server.port)
            kwargs.setdefault('description', f'VRRP IP for {c.name} cluster')
            kwargs.setdefault('firewall_enable', server.firewall_enable)
            kwargs.setdefault('group_id', group_id)
            virt_id = server_sql.add_server(**kwargs)
            roxywi_common.logging(cluster_id, f'New cluster virtual server for VIP: {vip} has been created', keep_history=1, roxywi=1,
                                  service='HA cluster')
        except Exception as e:
            roxywi_common.logging(cluster_id, f'error: Cannot create new cluster virtual server for VIP: {vip}: {e}', roxywi=1, service='HA cluster')
        try:
            HaClusterVirt.insert(cluster_id=cluster_id, virt_id=virt_id, vip_id=vip_id).execute()
        except Exception as e:
            roxywi_common.logging(cluster_id, f'error: Cannot save cluster virtual server for VIP: {vip}: {e}', roxywi=1, service='HA cluster')


def _create_or_update_master_slaves_servers(cluster_id: int, servers: dict, router_id: int, create: bool = False) -> None:
    for server in servers:
        s = server_sql.get_server_by_id(server['id'])
        try:
            ha_sql.insert_or_update_slave(cluster_id, server['id'], server['eth'], server['master'], router_id)
            if create:
                roxywi_common.logging(cluster_id, f'New server {s.hostname} has been added to the cluster', keep_history=1,
                                  roxywi=1, service='HA cluster')
        except Exception as e:
            raise Exception(f'error: Cannot update slave server {s.hostname}: {e}')

        if server['master']:
            continue
        try:
            ha_sql.update_master_server_by_slave_ip(server['id'], s.ip)
        except Exception as e:
            raise Exception(f'error: Cannot update master on slave {s.hostname: {e}}')
