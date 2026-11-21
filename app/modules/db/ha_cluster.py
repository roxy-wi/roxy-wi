from peewee import SqliteDatabase

from app.modules.db.db_model import HaCluster, HaClusterVirt, HaClusterVip, HaClusterService, HaClusterSlave, Server, HaClusterRouter
from app.modules.db.common import out_error
from app.modules.roxywi.exception import RoxywiResourceNotFound, RoxywiConflictError, RoxywiValidationError


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
	except HaCluster.DoesNotExist:
		raise RoxywiResourceNotFound(f'HA cluster {cluster_id} not found')
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
	except HaClusterVip.DoesNotExist:
		raise RoxywiResourceNotFound
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
	try:
		return cluster_slaves_query(cluster_id, router_id).where(Server.group_id == group_id).tuples().execute()
	except Exception as e:
		out_error(e)


def cluster_slaves_query(cluster_id: int, router_id: int):
	"""Keep legacy tuple offsets stable when new server fields are added."""
	server_fields = (
		Server.server_id, Server.hostname, Server.ip, Server.group_id,
		Server.type_ip, Server.enabled, Server.master, Server.cred_id,
		Server.haproxy_alert, Server.haproxy_metrics, Server.port, Server.description,
		Server.haproxy_active, Server.keepalived, Server.nginx, Server.haproxy,
		Server.pos, Server.nginx_active, Server.firewall_enable, Server.nginx_alert,
		Server.protected, Server.nginx_metrics, Server.keepalived_active,
		Server.keepalived_alert, Server.apache, Server.apache_active,
		Server.apache_alert, Server.apache_metrics,
	)
	return Server.select(*server_fields, *HaClusterSlave._meta.sorted_fields).join(HaClusterSlave).where(
		(HaClusterSlave.cluster_id == cluster_id) & (HaClusterSlave.router_id == router_id)
	)


def select_cluster_slaves(cluster_id: int, router_id: int):
	try:
		return cluster_slaves_query(cluster_id, router_id).tuples().execute()
	except Exception as e:
		out_error(e)


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


def _validate_vrid(vrid):
    if vrid is not None and (type(vrid) is not int or not 1 <= vrid <= 255):
        raise RoxywiValidationError('VRID must be an integer between 1 and 255')


def _lock_vrid_pool(cluster_id):
    """Lock the parent even when this cluster has no router rows yet."""
    query = HaCluster.select(HaCluster.id).where(HaCluster.id == cluster_id)
    if not isinstance(HaCluster._meta.database, SqliteDatabase):
        query = query.for_update()
    if query.get_or_none() is None:
        raise RoxywiResourceNotFound('HA cluster not found')


def create_ha_router(cluster_id: int, default: int = 0, vrid: int = None) -> int:
    """Allocate a free wire VRID independently of the database primary key.

    The service's topology lock serializes writers across controller workers.
    Database locking and the unique index also prevent duplicate reservations.
    Reservations belong to this cluster, including manually selected values.
    """
    database = HaClusterRouter._meta.database
    transaction_args = ('IMMEDIATE',) if isinstance(database, SqliteDatabase) else ()
    with database.atomic(*transaction_args):
        _validate_vrid(vrid)
        _lock_vrid_pool(cluster_id)
        query = HaClusterRouter.select(HaClusterRouter.vrid).where(
            HaClusterRouter.cluster_id == cluster_id).order_by(HaClusterRouter.vrid)
        if not isinstance(database, SqliteDatabase):
            query = query.for_update()
        used = {row.vrid for row in query}
        if vrid is not None and vrid in used:
            raise RoxywiConflictError(f'VRID {vrid} is already used in this cluster')
        if vrid is None:
            vrid = next((value for value in range(1, 256) if value not in used), None)
        if vrid is None:
            raise RoxywiConflictError(
                'No free Keepalived VRID: all 255 values are reserved in this cluster'
            )
        return HaClusterRouter.insert(cluster_id=cluster_id, default=default, vrid=vrid).execute()


def update_router_vrid(cluster_id: int, router_id: int, vrid: int = None) -> None:
    """Keep the current assignment unless an explicit unused VRID is requested."""
    _validate_vrid(vrid)
    database = HaClusterRouter._meta.database
    transaction_args = ('IMMEDIATE',) if isinstance(database, SqliteDatabase) else ()
    with database.atomic(*transaction_args):
        _lock_vrid_pool(cluster_id)
        router = HaClusterRouter.get_or_none(
            (HaClusterRouter.cluster_id == cluster_id) & (HaClusterRouter.id == router_id))
        if router is None:
            raise RoxywiResourceNotFound('HA router not found in this cluster')
        if vrid is None or vrid == router.vrid:
            return
        query = HaClusterRouter.select().where(
            (HaClusterRouter.cluster_id == cluster_id) & (HaClusterRouter.vrid == vrid))
        if not isinstance(database, SqliteDatabase):
            query = query.for_update()
        if query.exists():
            raise RoxywiConflictError(f'VRID {vrid} is already used in this cluster')
        HaClusterRouter.update(vrid=vrid).where(HaClusterRouter.id == router.id).execute()


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


def update_ha_virt_ip(vip_id: int, **kwargs) -> None:
	try:
		Server.update(**kwargs).where(Server.server_id == HaClusterVirt.get(HaClusterVirt.vip_id == vip_id).virt_id).execute()
	except Exception as e:
		out_error(e)


def delete_ha_virt(vip_id: int) -> None:
	try:
		Server.delete().where(Server.server_id == HaClusterVirt.get(HaClusterVirt.vip_id == vip_id).virt_id).execute()
	except Exception:
		pass


def check_ha_virt(vip_id: int) -> int:
	try:
		_ = HaClusterVirt.get(HaClusterVirt.vip_id == vip_id).virt_id
		return 1
	except HaClusterVirt.DoesNotExist:
		return 0
	except Exception as e:
		out_error(e)


def select_ha_virts(cluster_id: int) -> HaClusterVirt:
	try:
		return HaClusterVirt.select().where(HaClusterVirt.cluster_id == cluster_id).execute()
	except HaClusterVirt.DoesNotExist:
		pass
	except Exception as e:
		out_error(e)


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
