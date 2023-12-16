import modules.db.sql as sql
from modules.db.db_model import HaCluster, HaClusterRouter, HaClusterVip, HaClusterVirt
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common
from modules.server.ssh import return_ssh_keys_path


def create_cluster(cluster: object, group_id: int) -> str:
    master_ip = None
    vip = common.is_ip_or_dns(cluster['vip'])
    syn_flood = int(cluster['syn_flood'])
    return_master = int(cluster['return_to_master'])

    try:
        cluster_id = sql.create_cluster(cluster['name'], syn_flood, group_id, cluster['desc'])
        roxywi_common.logging(cluster_id, 'New cluster has been created', keep_history=1, roxywi=1, service='HA cluster')
    except Exception as e:
        return f'error: Cannot create new HA cluster: {e}'

    try:
        router_id = HaClusterRouter.insert(cluster_id=cluster_id, default=1).on_conflict_ignore().execute()
    except Exception as e:
        return f'error: Cannon create router: {e}'

    try:
        vip_id = HaClusterVip.insert(cluster_id=cluster_id, router_id=router_id, vip=vip, return_master=return_master).execute()
        roxywi_common.logging(cluster_id, f'New vip {vip} has been created and added to the cluster', keep_history=1, roxywi=1, service='HA cluster')
    except Exception as e:
        return f'error: Cannon add VIP: {e}'

    for slave_id, value in cluster['servers'].items():
        if value['master']:
            master_ip = value['ip']

    for slave_id, value in cluster['servers'].items():
        if value['master']:
            continue
        try:
            sql.update_server_master(master_ip, value['ip'])
        except Exception as e:
            raise Exception(f'error: Cannot update master on slave {value["ip"]: {e}}')

    for slave_id, value in cluster['servers'].items():
        if value['master']:
            slave_id = sql.select_server_id_by_ip(master_ip)
        try:
            sql.insert_or_update_slave(cluster_id, slave_id, value['eth'], value['master'], router_id)
            roxywi_common.logging(cluster_id, f'New server {value["ip"]} has been added to the cluster', keep_history=1, roxywi=1, service='HA cluster')
        except Exception as e:
            raise Exception(f'error: Cannot update slave server {value["ip"]}: {e}')

    for service, value in cluster['services'].items():
        if not value['enabled']:
            continue
        try:
            service_id = sql.select_service_id_by_slug(service)
            sql.insert_cluster_services(cluster_id, service_id)
            roxywi_common.logging(cluster_id, f'Service {service} has been enabled on the cluster', keep_history=1, roxywi=1, service='HA cluster')
        except Exception as e:
            raise Exception(f'error: Cannot add service {service}: {e}')

    if cluster['virt_server']:
        add_or_update_virt(cluster, cluster_id, vip_id, group_id)

    return str(cluster_id)


def update_cluster(cluster: object, group_id: int) -> str:
    cluster_id = int(cluster['cluster_id'])
    syn_flood = int(cluster['syn_flood'])
    cluster_name = cluster['name']

    try:
        router_id = sql.get_router_id(cluster_id, default_router=1)
    except Exception as e:
        raise Exception(f'error: Cannot get router: {e}')

    try:
        sql.update_cluster(cluster_id, cluster['name'], cluster['desc'], syn_flood)
    except Exception as e:
        raise Exception(f'error: Cannot update HA cluster: {e}')

    try:
        update_slaves(cluster, router_id)
    except Exception as e:
        raise Exception(e)

    try:
        update_vip(cluster_id, router_id, cluster, group_id)
    except Exception as e:
        raise Exception(e)

    try:
        sql.delete_cluster_services(cluster_id)
    except Exception as e:
        raise Exception(f'error: Cannot delete old services: {e}')

    for service, value in cluster['services'].items():
        if not value['enabled']:
            continue
        try:
            service_id = sql.select_service_id_by_slug(service)
            sql.insert_cluster_services(cluster_id, service_id)
        except Exception as e:
            raise Exception(f'error: Cannot add service {service}: {e}')

    roxywi_common.logging(cluster_id, f'Cluster {cluster_name} has been updated', keep_history=1, roxywi=1, service='HA cluster')

    return 'ok'


def delete_cluster(cluster_id: int) -> str:
    HaCluster.delete().where(HaCluster.id == cluster_id).execute()
    slaves = sql.select_cluster_slaves(cluster_id)

    for slave in slaves:
        slave_ip = sql.select_server_ip_by_id(slave.server_id)
        try:
            sql.update_server_master(0, slave_ip)
        except Exception as e:
            raise Exception(f'error: Cannot update master on slave {slave_ip}: {e}')

    roxywi_common.logging(cluster_id, f'Cluster has been deleted', keep_history=1, roxywi=1, service='HA cluster')

    return 'ok'


def update_vip(cluster_id: int, router_id: int, json_data: object, group_id: int) -> None:
    return_master = int(json_data['return_to_master'])
    vip = common.is_ip_or_dns(json_data['vip'])
    vip_id = sql.select_clusters_vip_id(cluster_id, router_id)

    try:
        sql.update_ha_cluster_vip(cluster_id, router_id, vip, return_master)
    except Exception as e:
        raise Exception(f'error: Cannot update VIP: {e}')

    for slave_id, value in json_data['servers'].items():
        try:
            sql.update_slave(cluster_id, slave_id, value['eth'], value['master'], router_id)
        except Exception as e:
            raise Exception(f'error: Cannot add server {value["ip"]}: {e}')

    if json_data['virt_server']:
        add_or_update_virt(json_data, cluster_id, vip_id, group_id)
    else:
        try:
            if sql.check_ha_virt(vip_id):
                sql.delete_ha_virt(vip_id)
                roxywi_common.logging(cluster_id, f'Cluster virtual server for VIP: {vip} has been deleted', keep_history=1, roxywi=1, service='HA cluster')
        except Exception as e:
            roxywi_common.logging(cluster_id, f'Cannot delete cluster virtual server for VIP {vip}: {e}', keep_history=1, roxywi=1, service='HA cluster')

    roxywi_common.logging(cluster_id, f'Cluster VIP {vip} has been updated', keep_history=1, roxywi=1, service='HA cluster')


def insert_vip(cluster_id: int, json_data: object, group_id: int) -> None:
    vip = common.is_ip_or_dns(json_data['vip'])
    return_master = int(json_data['return_to_master'])

    try:
        router_id = sql.create_ha_router(cluster_id)
    except Exception as e:
        raise Exception(f'error: Cannot create new router: {e}')

    try:
        vip_id = HaClusterVip.insert(cluster_id=cluster_id, router_id=router_id, vip=vip, return_master=return_master).execute()
    except Exception as e:
        raise Exception(f'error: Cannot save VIP {vip}: {e}')

    for slave_id, value in json_data['servers'].items():
        try:
            sql.insert_or_update_slave(cluster_id, slave_id, value['eth'], value['master'], router_id)
        except Exception as e:
            raise Exception(f'error: Cannot add server {value["ip"]}: {e}')

    if json_data['virt_server']:
        add_or_update_virt(json_data, cluster_id, vip_id, group_id)

    roxywi_common.logging(cluster_id, f'New cluster VIP: {vip} has been created', keep_history=1, roxywi=1, service='HA cluster')


def update_slaves(json_data: object, router_id: int) -> None:
    master_ip = None
    cluster = json_data
    cluster_id = int(json_data['cluster_id'])
    all_routers_in_cluster = HaClusterRouter.select(HaClusterRouter.id).where(HaClusterRouter.cluster_id == cluster_id).execute()
    server_ids_from_db = sql.select_cluster_slaves(cluster_id, router_id)
    server_ids = []
    server_ids_from_json = []

    for slave_id, value in cluster['servers'].items():
        if value['master']:
            master_ip = value['ip']

    for server in server_ids_from_db:
        server_ids.append(server[0])

    for slave_id, value in cluster['servers'].items():
        if value['master']:
            slave_id = sql.select_server_id_by_ip(master_ip)
        server_ids_from_json.append(int(slave_id))

    server_ids_for_deletion = set(server_ids) - set(server_ids_from_json)
    server_ids_for_adding = set(server_ids_from_json) - set(server_ids)

    for router in all_routers_in_cluster:
        for slave_id, value in cluster['servers'].items():
            for server_id_add in server_ids_for_adding:
                if int(slave_id) == int(server_id_add):
                    try:
                        sql.insert_or_update_slave(cluster_id, slave_id, value['eth'], value['master'], router)
                    except Exception as e:
                        raise Exception(f'error: Cannot add new slave {value["name"]}: {e}')

    for o_s in server_ids_for_deletion:
        sql.delete_master_from_slave(o_s)

        try:
            sql.delete_ha_cluster_delete_slave(o_s)
        except Exception as e:
            raise Exception(f'error: Cannot recreate slaves server: {e}')

    for slave_id, value in cluster['servers'].items():
        if value['master']:
            continue
        try:
            sql.update_server_master(master_ip, value['ip'])
        except Exception as e:
            raise Exception(f'error: Cannot update master on slave {value["ip"]}: {e}')

    for slave_id, value in cluster['servers'].items():
        if value['master']:
            slave_id = sql.select_server_id_by_ip(master_ip)
        try:
            sql.insert_or_update_slave(cluster_id, slave_id, value['eth'], value['master'], router_id)
        except Exception as e:
            raise Exception(f'error: Cannot update server {value["ip"]}: {e}')


def add_or_update_virt(cluster: object, cluster_id: int, vip_id: int, group_id: int) -> None:
    haproxy = 0
    nginx = 0
    apache = 0
    master_ip = None
    vip = common.is_ip_or_dns(cluster['vip'])
    cluster_name = common.checkAjaxInput(cluster['name'])

    for slave_id, value in cluster['servers'].items():
        if value['master']:
            master_ip = common.is_ip_or_dns(value['ip'])

    if sql.check_ha_virt(vip_id):
        try:
            sql.update_ha_virt_ip(vip_id, vip)
            roxywi_common.logging(cluster_id, f'Cluster virtual server for VIP {vip} has been updated', keep_history=1, roxywi=1, service='HA cluster')
        except Exception as e:
            roxywi_common.logging(cluster_id, f'Cannot update cluster virtual server for VIP {vip}: {e}', roxywi=1, service='HA cluster')
    else:
        services = sql.select_cluster_services(cluster_id)
        for service in services:
            haproxy = 1 if service.service_id == '1' else 0
            nginx = 1 if service.service_id == '2' else 0
            apache = 1 if service.service_id == '4' else 0
        try:
            cred_id = sql.get_cred_id_by_server_ip(master_ip)
            firewall = 1 if server_mod.is_service_active(master_ip, 'firewalld') else 0
            ssh_settings = return_ssh_keys_path(master_ip)
            virt_id = sql.add_server(
                f'{vip}-VIP', vip, group_id, '1', '1', '0', cred_id, ssh_settings['port'],
                f'VRRP IP for {cluster_name} cluster', haproxy, nginx, apache, firewall
            )
            HaClusterVirt.insert(cluster_id=cluster_id, virt_id=virt_id, vip_id=vip_id).execute()
            roxywi_common.logging(cluster_id, f'New cluster virtual server for VIP: {vip} has been created', keep_history=1, roxywi=1,
                                  service='HA cluster')
        except Exception as e:
            roxywi_common.logging(cluster_id, f'error: Cannot create new cluster virtual server for VIP: {vip}: {e}', roxywi=1, service='HA cluster')
