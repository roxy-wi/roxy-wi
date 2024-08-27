from app.modules.db.db_model import connect, HaCluster, HaClusterVirt, HaClusterVip, HaClusterService, HaClusterSlave, Server, HaClusterRouter
from app.modules.db.common import out_error
from app.modules.roxywi.exception import RoxywiResourceNotFound


def select_clusters(group_id: int):
	try:
		return HaCluster.select().where(HaCluster.group_id == group_id).execute()
	except Exception as e:
		out_error(e)


def create_cluster(name: str, syn_flood: int, group_id: int, desc: str) -> int:
	try:
		last_id = HaCluster.insert(
			name=name, syn_flood=syn_flood, group_id=group_id, description=desc
		).execute()
		return last_id
	except Exception as e:
		out_error(e)


def select_cluster(cluster_id: int):
	try:
		return HaCluster.select().where(HaCluster.id == cluster_id).execute()
	except Exception as e:
		out_error(e)


def get_cluster(cluster_id: int):
	try:
		return HaCluster.get(HaCluster.id == cluster_id)
	except Exception as e:
		out_error(e)


def select_cluster_name(cluster_id: int) -> str:
	try:
		return HaCluster.get(HaCluster.id == cluster_id).name
	except Exception as e:
		out_error(e)


def select_clusters_virts():
	try:
		return HaClusterVirt.select().execute()
	except Exception as e:
		out_error(e)


def select_cluster_vips(cluster_id: int) -> HaClusterVip:
	try:
		return HaClusterVip.select().where(HaClusterVip.cluster_id == cluster_id).execute()
	except Exception as e:
		out_error(e)


def select_cluster_vip(cluster_id: int, router_id: int) -> HaClusterVip:
	try:
		return HaClusterVip.get((HaClusterVip.cluster_id == cluster_id) & (HaClusterVip.router_id == router_id))
	except Exception as e:
		out_error(e)


def select_cluster_vip_by_vip_id(cluster_id: int, vip_id: int) -> HaClusterVip:
	try:
		return HaClusterVip.get((HaClusterVip.cluster_id == cluster_id) & (HaClusterVip.id == vip_id))
	except Exception as e:
		out_error(e)


def select_clusters_vip_id(cluster_id: int, router_id):
	try:
		return HaClusterVip.get((HaClusterVip.cluster_id == cluster_id) & (HaClusterVip.router_id == router_id)).id
	except Exception as e:
		out_error(e)


def delete_cluster_services(cluster_id: int):
	try:
		return HaClusterService.delete().where(HaClusterService.cluster_id == cluster_id).execute()
	except Exception as e:
		out_error(e)


def insert_cluster_services(cluster_id: int, service_id: int):
	try:
		return HaClusterService.insert(cluster_id=cluster_id, service_id=service_id).execute()
	except Exception as e:
		out_error(e)


def select_count_cluster_slaves(cluster_id: int) -> int:
	try:
		return HaClusterSlave.select().where(HaClusterSlave.cluster_id == cluster_id).count()
	except HaClusterSlave.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def select_cluster_master_slaves(cluster_id: int, group_id: int, router_id: int):
	conn = connect()
	cursor = conn.cursor()
	sql = f"select * from servers left join ha_cluster_slaves on (servers.id = ha_cluster_slaves.server_id) " \
		  f"where servers.group_id = {group_id} and ha_cluster_slaves.cluster_id = {cluster_id} and ha_cluster_slaves.router_id = {router_id};"
	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		return cursor.fetchall()


def select_cluster_slaves(cluster_id: int, router_id: int):
	conn = connect()
	cursor = conn.cursor()
	sql = f"select * from servers left join ha_cluster_slaves on (servers.id = ha_cluster_slaves.server_id) " \
		  f"where ha_cluster_slaves.cluster_id = {cluster_id} and ha_cluster_slaves.router_id = {router_id};"
	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		return cursor.fetchall()


def select_cluster_slaves_for_inv(router_id: int):
	try:
		return HaClusterSlave.select().where(HaClusterSlave.router_id == router_id).execute()
	except Exception as e:
		out_error(e)


def delete_ha_cluster_delete_slave(server_id: int) -> None:
	try:
		HaClusterSlave.delete().where(HaClusterSlave.server_id == server_id).execute()
	except Exception as e:
		out_error(e)


def delete_master_from_slave(server_id: int) -> None:
	try:
		Server.update(master=0).where(Server.server_id == server_id).execute()
	except Exception as e:
		out_error(e)


def select_ha_cluster_not_masters_not_slaves(group_id: int):
	"""
	Method for selecting HA clusters excluding masters and slaves.

	:param group_id: The ID of the group.
	:return: The query result.
	"""
	try:
		query = Server.select().where(
			(Server.type_ip == 0) &
			(Server.server_id.not_in(HaClusterSlave.select(HaClusterSlave.server_id))) &
			(Server.group_id == group_id)
		)
		return query.execute()
	except Exception as e:
		out_error(e)


def get_router_id(cluster_id: int, default_router=0) -> int:
	"""
	:param cluster_id: The ID of the cluster to get the router ID from.
	:param default_router: The default router ID to retrieve. Default value is 0.
	:return: The ID of the router associated with the given cluster ID and default router ID.

	"""
	try:
		return HaClusterRouter.get((HaClusterRouter.cluster_id == cluster_id) & (HaClusterRouter.default == default_router)).id
	except HaClusterRouter.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def get_router(router_id: int) -> HaClusterRouter:
	try:
		return HaClusterRouter.get(HaClusterRouter.id == router_id)
	except Exception as e:
		out_error(e)


def create_ha_router(cluster_id: int, default: int = 0) -> int:
	"""
    Create HA Router

    This method is used to create a HA (High Availability) router for a given cluster.

    :param default:
    :param cluster_id: The ID of the cluster for which the HA router needs to be created.
    :return: The ID of the created HA router.
    :rtype: int

    :raises Exception: If an error occurs while creating the HA router.

    """
	try:
		last_id = HaClusterRouter.insert(cluster_id=cluster_id, default=default).on_conflict_ignore().execute()
		return last_id
	except Exception as e:
		out_error(e)


def delete_ha_router(router_id: int) -> int:
	try:
		last_id = HaClusterRouter.delete().where(HaClusterRouter.id == router_id).execute()
		return last_id
	except Exception as e:
		out_error(e)


def insert_or_update_slave(cluster_id: int, server_id: int, eth: str, master: int, router_id) -> None:
	try:
		HaClusterSlave.insert(cluster_id=cluster_id, server_id=server_id, eth=eth, master=master, router_id=router_id).on_conflict('replace').execute()
	except Exception as e:
		out_error(e)


def update_slave(cluster_id: int, server_id: int, eth: str, master: int, router_id) -> None:
	try:
		HaClusterSlave.update(
			cluster_id=cluster_id, server_id=server_id, eth=eth, master=master, router_id=router_id
		).where((HaClusterSlave.server_id == server_id) & (HaClusterSlave.router_id == router_id)).execute()
	except Exception as e:
		out_error(e)


def update_cluster(cluster_id: int, name: str, desc: str, syn_flood: int) -> None:
	try:
		HaCluster.update(name=name, description=desc, syn_flood=syn_flood).where(HaCluster.id == cluster_id).execute()
	except Exception as e:
		out_error(e)


def update_ha_cluster_vip(cluster_id: int, router_id: int, vip: str, return_master: int, use_src: int) -> None:
	try:
		HaClusterVip.update(vip=vip, return_master=return_master, use_src=use_src).where(
			(HaClusterVip.cluster_id == cluster_id) & (HaClusterVip.router_id == router_id)
		).execute()
	except Exception as e:
		out_error(e)


def update_ha_virt_ip(vip_id: int, vip: str) -> None:
	try:
		Server.update(ip=vip).where(Server.server_id == HaClusterVirt.get(HaClusterVirt.vip_id == vip_id).virt_id).execute()
	except Exception as e:
		out_error(e)


def delete_ha_virt(vip_id: int) -> None:
	try:
		Server.delete().where(Server.server_id == HaClusterVirt.get(HaClusterVirt.vip_id == vip_id).virt_id).execute()
	except Exception:
		pass


def check_ha_virt(vip_id: int) -> bool:
	try:
		HaClusterVirt.get(HaClusterVirt.vip_id == vip_id).virt_id
	except Exception:
		return False
	return True


def select_ha_cluster_name_and_slaves() -> object:
	try:
		return HaCluster.select(HaCluster.id, HaCluster.name, HaClusterSlave.server_id).join(HaClusterSlave).execute()
	except Exception as e:
		out_error(e)


def select_cluster_services(cluster_id: int):
	try:
		return HaClusterService.select().where(HaClusterService.cluster_id == cluster_id).execute()
	except Exception as e:
		out_error(e)


def update_master_server_by_slave_ip(master_id: int, slave_ip: str) -> None:
	try:
		Server.update(master=master_id).where(Server.ip == slave_ip).execute()
	except Exception as e:
		out_error(e)


def get_cred_id_by_server_ip(server_ip):
	try:
		cred = Server.get(Server.ip == server_ip)
	except Exception as e:
		return out_error(e)
	else:
		return cred.cred_id
