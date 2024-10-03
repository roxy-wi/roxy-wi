import ast

from playhouse.shortcuts import model_to_dict

import app.modules.db.udp as udp_sql
import app.modules.db.server as server_sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common


def get_listener_config(listener_id: int) -> dict:
    listener = udp_sql.get_listener(listener_id)
    listener_json = model_to_dict(listener, recurse=False)
    listener_json['config'] = ast.literal_eval(listener_json['config'])
    return listener_json


def get_slaves_for_udp_listener(cluster_id: int, vip: str) -> list:
    servers = []
    vips = ha_sql.select_cluster_vips(cluster_id)
    for v in vips:
        if v.vip == vip:
            router_id = v.router_id
            break
    else:
        raise ValueError("error: Cannot find VIP")
    slaves = ha_sql.select_cluster_slaves(cluster_id, router_id)
    for slave in slaves:
        servers.append(slave[2])
    return servers


def _return_listener_servers(listener_id: int, group_id=None):
    servers = []
    listener = udp_sql.get_listener(listener_id)
    if group_id is not None and int(listener.group_id.group_id) != int(group_id):
        raise ValueError("error: Invalid group")
    if listener.cluster_id:
        servers = get_slaves_for_udp_listener(listener.cluster_id, listener.vip)
    elif listener.server_id:
        server = server_sql.get_server_by_id(listener.server_id)
        servers.append(server.ip)
    if len(servers) < 1:
        raise ValueError("error: Cannot find server")

    return servers, listener


def listener_actions(listener_id: int, action: str, group_id: int) -> None:
    cmd = f'sudo systemctl {action} keepalived-udp-{listener_id}.service'
    try:
        servers, listener = _return_listener_servers(listener_id, group_id)
    except Exception as e:
        raise e

    for server_ip in servers:
        try:
            server_mod.ssh_command(server_ip, cmd)
            roxywi_common.logging(listener.id, f'UDP listener {listener.name} has been {action} on {server_ip}', keep_history=1, roxywi=1, service='UDP Listener')
        except Exception as e:
            roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot {action} for UDP balancer {listener.name}', roxywi=1)


def check_is_listener_active(listener_id: int) -> str:
    try:
        servers, listener = _return_listener_servers(listener_id)
    except Exception as e:
        raise Exception(e)
    statuses = []
    cmd = f'systemctl is-active keepalived-udp-{listener_id}.service'
    for server_ip in servers:
        status = server_mod.ssh_command(server_ip, cmd)
        statuses.append(status.replace('\n', '').replace('\r', ''))
    if 'inactive' in statuses and 'active' in statuses:
        return 'warning'
    elif 'inactive' in statuses and 'active' not in statuses:
        return 'error'
    return 'ok'
