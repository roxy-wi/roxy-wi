import json

from playhouse.shortcuts import model_to_dict

import app.modules.db.udp as udp_sql
import app.modules.db.server as server_sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common


def create_listener(json_data: json) -> int:
    listener = _validate_form(json_data)
    listener_id = udp_sql.insert_listener(**listener)
    roxywi_common.logging(listener_id, f'UDP listener {listener["name"]} has been created', keep_history=1, roxywi=1, service='UDP Listener')
    return listener_id


def update_listener(json_data: json) -> str:
    listener = _validate_form(json_data)
    listener_id = json_data['listener_id']
    udp_sql.update_listener(listener_id, **listener)
    roxywi_common.logging(listener_id, f'UDP listener {listener["name"]} has been updated', keep_history=1, roxywi=1, service='UDP Listener')
    return 'ok'


def _validate_form(json_data: json) -> dict:
    returned_data = {}
    if not isinstance(json_data, dict):
        raise ValueError("error: Invalid form data")
    returned_data['name'] = common.checkAjaxInput(json_data['new-listener-name'])
    returned_data['desc'] = common.checkAjaxInput(json_data['new-listener-desc'])
    try:
        returned_data['port'] = int(json_data['new-listener-port'])
    except Exception:
        raise ValueError("error: Invalid port number")
    returned_data['group_id'] = int(json_data['group_id'])
    returned_data['config'] = {}
    for k, v in json_data.items():
        if k == 'servers':
            _validate_backend_servers(v)
            for server, value in v.items():
                server_ip = common.is_ip_or_dns(server)
                returned_data['config'][server_ip] = {}
                returned_data['config'][server_ip]['port'] = int(value['port'])
                returned_data['config'][server_ip]['weight'] = int(value['weight'])
    if json_data['new-listener-type'] == 'server':
        returned_data['server_id'] = int(json_data['serv'])
        try:
            returned_data['vip'] = common.is_ip_or_dns(json_data['new-udp-ip'])
        except ValueError:
            raise ValueError("error: Cannot parse Server and IP")
    else:
        try:
            cluster_id = int(json_data['ha-cluster'])
            returned_data['cluster_id'] = cluster_id
        except ValueError:
            raise ValueError("error: Cannot parse Cluster ID")
        returned_data['vip'] = common.is_ip_or_dns(json_data['new-udp-vip'])

    return returned_data


def _validate_backend_servers(serves: dict):
    if not isinstance(serves, dict):
        raise ValueError("error: Invalid backend servers data")
    if len(serves) == 0:
        raise ValueError("error: Empty backend servers")
    for server, value in serves.items():
        server = common.is_ip_or_dns(server)
        if server == '':
            raise ValueError("error: Cannot parse backend server IP")
        try:
            port = int(value['port'])
        except ValueError:
            raise ValueError(f"error: Invalid port for backend server {server}")
        if port > 65535 or port < 1:
            raise Exception(f'error: Port must be 1-65535 for backend server {server}')
        try:
            weight = int(value['weight'])
        except ValueError:
            raise ValueError(f"error: Invalid weight for backend server {server}")
        if weight > 65535 or weight < 1:
            raise Exception(f'error: Weight must be 1-65535 for backend server {server}')


def get_listener_config(listener_id: int) -> dict:
    listener = udp_sql.get_listener(listener_id)
    listener_json = model_to_dict(listener)
    listener_json['config'] = eval(listener_json['config'])
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
    if group_id is not None and int(listener.group_id.group_id) != group_id:
        raise ValueError("error: Invalid group")
    if listener.cluster_id:
        servers = get_slaves_for_udp_listener(listener.cluster_id, listener.vip)
    elif listener.server_id:
        server = server_sql.get_server_by_id(listener.server_id)
        servers.append(server.ip)
    if len(servers) < 1:
        raise ValueError("error: Cannot find server")

    return servers, listener



def listener_actions(listener_id: int, action: str, group_id: int) -> str:
    if action not in ('start', 'stop', 'restart'):
        raise ValueError("error: Invalid action")

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
    return 'ok'


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
