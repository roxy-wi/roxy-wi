from typing import Union

import app.modules.db.server as server_sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.db.service as service_sql
from app.modules.db.db_model import HaCluster, HaClusterRouter, HaClusterVip, HaClusterVirt
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common
from app.modules.server.ssh import return_ssh_keys_path
from app.modules.roxywi.class_models import HAClusterRequest, HAClusterVIP


def _get_servers_dict(cluster: Union[HAClusterRequest, HAClusterVIP]) -> dict:
    for i, k in cluster.model_dump(mode='json').items():
        if i == 'servers':
            servers = k
    return servers


def _get_services_dict(cluster: HAClusterRequest) -> dict:
    for i, k in cluster.model_dump(mode='json').items():
        if i == 'services':
            services = k
    return services


def create_cluster(cluster: HAClusterRequest, group_id: int) -> int:
    master_ip = None
    servers = _get_servers_dict(cluster)
    services = _get_services_dict(cluster)

    try:
        cluster_id = ha_sql.create_cluster(cluster.name, cluster.syn_flood, group_id, cluster.description)
        roxywi_common.logging(cluster_id, 'New cluster has been created', keep_history=1, roxywi=1, service='HA cluster')
    except Exception as e:
        raise Exception(f'error: Cannot create new HA cluster: {e}')

    try:
        router_id = HaClusterRouter.insert(cluster_id=cluster_id, default=1).on_conflict_ignore().execute()
    except Exception as e:
        raise Exception(f'error: Cannon create router: {e}')

    try:
        vip_id = HaClusterVip.insert(cluster_id=cluster_id, router_id=router_id, vip=cluster.vip, return_master=cluster.return_master).execute()
        roxywi_common.logging(cluster_id, f'New vip {cluster.vip} has been created and added to the cluster', keep_history=1, roxywi=1, service='HA cluster')
    except Exception as e:
        raise Exception(f'error: Cannon add VIP: {e}')


    for value in servers:
        if value['master']:
            master_ip = value['ip']

    for value in servers:
        if value['master']:
            continue
        try:
            ha_sql.update_server_master(master_ip, value['ip'])
        except Exception as e:
            raise Exception(f'error: Cannot update master on slave {value["ip"]: {e}}')

    for value in servers:
        slave_id = value['id']
        if value['master']:
            slave_id = server_sql.select_server_id_by_ip(master_ip)
        try:
            ha_sql.insert_or_update_slave(cluster_id, slave_id, value['eth'], value['master'], router_id)
            roxywi_common.logging(cluster_id, f'New server {value["ip"]} has been added to the cluster', keep_history=1, roxywi=1, service='HA cluster')
        except Exception as e:
            raise Exception(f'error: Cannot update slave server {value["ip"]}: {e}')

    for service, value in services.items():
        if not value['enabled']:
            continue
        try:
            service_id = service_sql.select_service_id_by_slug(service)
            ha_sql.insert_cluster_services(cluster_id, service_id)
            roxywi_common.logging(cluster_id, f'Service {service} has been enabled on the cluster', keep_history=1, roxywi=1, service='HA cluster')
        except Exception as e:
            raise Exception(f'error: Cannot add service {service}: {e}')

    if cluster.virt_server:
        add_or_update_virt(cluster, servers, cluster_id, vip_id, group_id)

    return int(cluster_id)


def update_cluster(cluster: HAClusterRequest, cluster_id: int, group_id: int) -> None:
    servers = _get_servers_dict(cluster)
    services = _get_services_dict(cluster)

    try:
        router_id = ha_sql.get_router_id(cluster_id, default_router=1)
    except Exception as e:
        raise Exception(f'error: Cannot get router: {e}')

    try:
        ha_sql.update_cluster(cluster_id, cluster.name, cluster.description, cluster.syn_flood)
    except Exception as e:
        raise Exception(f'error: Cannot update HA cluster: {e}')

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

    roxywi_common.logging(cluster_id, f'Cluster {cluster.name} has been updated', keep_history=1, roxywi=1, service='HA cluster')


def delete_cluster(cluster_id: int) -> str:
    router_id = ha_sql.get_router_id(cluster_id, default_router=1)
    slaves = ha_sql.select_cluster_slaves(cluster_id, router_id)

    for slave in slaves:
        slave_ip = server_sql.select_server_ip_by_id(slave[0])
        try:
            ha_sql.update_master_server_by_slave_ip(0, slave_ip)
        except Exception as e:
            raise Exception(f'error: Cannot update master on slave {slave_ip}: {e}')

    HaCluster.delete().where(HaCluster.id == cluster_id).execute()
    roxywi_common.logging(cluster_id, 'Cluster has been deleted', roxywi=1, service='HA cluster')

    return 'ok'


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
            raise Exception(f'error: Cannot add server {value["ip"]}: {e}')

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


def insert_vip(cluster_id: int, cluster: HAClusterVIP, group_id: int) -> None:
    vip = cluster.vip
    servers = _get_servers_dict(cluster)

    try:
        router_id = ha_sql.create_ha_router(cluster_id)
    except Exception as e:
        raise Exception(f'error: Cannot create new router: {e}')

    try:
        vip_id = HaClusterVip.insert(cluster_id=cluster_id, router_id=router_id, vip=vip, return_master=cluster.return_master).execute()
    except Exception as e:
        raise Exception(f'error: Cannot save VIP {vip}: {e}')

    for value in servers:
        try:
            ha_sql.insert_or_update_slave(cluster_id, value['id'], value['eth'], value['master'], router_id)
        except Exception as e:
            raise Exception(f'error: Cannot add server {value["ip"]}: {e}')

    if cluster.virt_server:
        add_or_update_virt(cluster, servers, cluster_id, vip_id, group_id)

    roxywi_common.logging(cluster_id, f'New cluster VIP: {vip} has been created', keep_history=1, roxywi=1, service='HA cluster')


def update_slaves(servers: dict, cluster_id: int, router_id: int) -> None:
    master_ip = None
    all_routers_in_cluster = HaClusterRouter.select(HaClusterRouter.id).where(HaClusterRouter.cluster_id == cluster_id).execute()
    server_ids_from_db = ha_sql.select_cluster_slaves(cluster_id, router_id)
    server_ids = []
    server_ids_from_json = []

    for value in servers:
        if value['master']:
            master_ip = value['ip']

    for server in server_ids_from_db:
        server_ids.append(server[0])

    for value in servers:
        slave_id = value['id']
        if value['master']:
            slave_id = server_sql.select_server_id_by_ip(master_ip)
        server_ids_from_json.append(int(slave_id))

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
                        raise Exception(f'error: Cannot add new slave {value["name"]}: {e}')

    for o_s in server_ids_for_deletion:
        ha_sql.delete_master_from_slave(o_s)

        try:
            ha_sql.delete_ha_cluster_delete_slave(o_s)
        except Exception as e:
            raise Exception(f'error: Cannot recreate slaves server: {e}')

    for value in servers:
        if value['master']:
            continue
        try:
            ha_sql.update_server_master(master_ip, value['ip'])
        except Exception as e:
            raise Exception(f'error: Cannot update master on slave {value["ip"]}: {e}')

    for value in servers:
        slave_id = value['id']
        if value['master']:
            slave_id = server_sql.select_server_id_by_ip(master_ip)
        try:
            ha_sql.insert_or_update_slave(cluster_id, slave_id, value['eth'], value['master'], router_id)
        except Exception as e:
            raise Exception(f'error: Cannot update server {value["ip"]}: {e}')


def add_or_update_virt(cluster: Union[HAClusterRequest, HAClusterVIP], servers: dict, cluster_id: int, vip_id: int, group_id: int) -> None:
    haproxy = 0
    nginx = 0
    apache = 0
    master_ip = None
    vip = str(cluster.vip)

    for value in servers:
        if value['master']:
            master_ip = value['ip']

    if ha_sql.check_ha_virt(vip_id):
        try:
            ha_sql.update_ha_virt_ip(vip_id, vip)
            roxywi_common.logging(cluster_id, f'Cluster virtual server for VIP {vip} has been updated', keep_history=1, roxywi=1, service='HA cluster')
        except Exception as e:
            roxywi_common.logging(cluster_id, f'Cannot update cluster virtual server for VIP {vip}: {e}', roxywi=1, service='HA cluster')
    else:
        services = ha_sql.select_cluster_services(cluster_id)
        for service in services:
            haproxy = 1 if service.service_id == '1' else 0
            nginx = 1 if service.service_id == '2' else 0
            apache = 1 if service.service_id == '4' else 0
        try:
            cred_id = ha_sql.get_cred_id_by_server_ip(master_ip)
            firewall = 1 if server_mod.is_service_active(master_ip, 'firewalld') else 0
            ssh_settings = return_ssh_keys_path(master_ip)
            virt_id = server_sql.add_server(
                f'{vip}-VIP', vip, group_id, '1', '1', '0', cred_id, ssh_settings['port'],
                f'VRRP IP for {cluster.name} cluster', haproxy, nginx, apache, firewall
            )
            HaClusterVirt.insert(cluster_id=cluster_id, virt_id=virt_id, vip_id=vip_id).execute()
            roxywi_common.logging(cluster_id, f'New cluster virtual server for VIP: {vip} has been created', keep_history=1, roxywi=1,
                                  service='HA cluster')
        except Exception as e:
            roxywi_common.logging(cluster_id, f'error: Cannot create new cluster virtual server for VIP: {vip}: {e}', roxywi=1, service='HA cluster')
