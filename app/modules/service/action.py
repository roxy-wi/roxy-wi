import socket
from contextlib import closing

import app.modules.db.sql as sql
import app.modules.db.user as user_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.service.common as service_common


def common_action(server_ip: str, action: str, service: str) -> str:
    action_functions = {
        'haproxy': service_action,
        'nginx': service_action,
        'keepalived': service_action,
        'apache': service_action,
        'waf_haproxy': action_haproxy_waf,
        'waf_nginx': action_nginx_waf
    }

    return action_functions[service](server_ip, action, service)



def service_action(server_ip: str, action: str, service: str) -> str:
    """
    :param server_ip: The IP address of the server on which the action will be performed.
    :param action: The action to be performed on the service (e.g., "start", "stop").
    :param service: The name of the service on which the action will be performed.
    :return: A string indicating the success or failure of the action.
    """
    try:
        service_common.is_protected(server_ip, action)
    except Exception as e:
        return str(e)
    server_id = server_sql.select_server_id_by_ip(server_ip=server_ip)

    if service_common.is_not_allowed_to_restart(server_id, service, action):
        return 'error: This server is not allowed to be restarted'

    try:
        if service != 'keepalived':
            service_common.check_service_config(server_ip, server_id, service)
    except Exception as e:
        return f'error: Cannot check config: {e}'

    command = get_action_command(service, action, server_id)
    try:
        server_mod.ssh_command(server_ip, command)
        roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service=service)
        return f"success: {service.title()} has been {action}"
    except Exception as e:
        return f"error: Cannot {action} {service.title()}: {e}"


def get_action_command(service: str, action: str, server_id: int) -> str:
    """
    :param service: The name of the service for which the action command is needed.
    :param action: The action to be performed on the service (e.g. start, stop, restart).
    :param server_id: The ID of the server.

    :return: A list containing the action command that needs to be executed.
    """
    is_docker = service_sql.select_service_setting(server_id, service, 'dockerized')
    if is_docker == '1':
        container_name = sql.get_setting(f'{service}_container_name')
        if action == 'reload':
            action = 'kill -S HUP'
        commands = f"sudo docker {action} {container_name}"
    else:
        service_name = service_common.get_correct_service_name(service, server_id)
        commands = f"sudo systemctl {action} {service_name}"

    return commands


def action_haproxy_waf(server_ip: str, action: str, service: str) -> str:
    try:
        service_common.is_protected(server_ip, action)
    except Exception as e:
        return str(e)

    roxywi_common.logging(
        server_ip, f'HAProxy WAF service has been {action}ed', roxywi=1, login=1, keep_history=1, service='haproxy'
    )
    command = f"sudo systemctl {action} waf"
    try:
        server_mod.ssh_command(server_ip, command)
        return f"success: WAF has been {action}"
    except Exception as e:
        return f"error: Cannot {action} WAF service: {e}"

def action_nginx_waf(server_ip: str, action: str, service: str) -> str:
    config_dir = common.return_nice_path(sql.get_setting('nginx_dir'))

    try:
        service_common.is_protected(server_ip, action)
    except Exception as e:
        return str(e)

    waf_new_state = 'on' if action == 'start' else 'off'
    waf_old_state = 'off' if action == 'start' else 'on'

    roxywi_common.logging(server_ip, f'NGINX WAF service has been {action}ed', roxywi=1, login=1, keep_history=1, service='nginx')
    command = (f"sudo sed -i 's/modsecurity {waf_old_state}/modsecurity {waf_new_state}/g' {config_dir}nginx.conf "
               f"&& sudo systemctl reload nginx")

    try:
        server_mod.ssh_command(server_ip, command)
        return f"success: WAF has been {action}"
    except Exception as e:
        return f"error: Cannot {action} WAF service: {e}"


def check_service(server_ip: str, user_uuid: str, service: str) -> str:
    user_id = user_sql.get_user_id_by_uuid(user_uuid)
    user_services = user_sql.select_user_services(user_id)

    if '1' in user_services:
        if service == 'haproxy':
            haproxy_sock_port = sql.get_setting('haproxy_sock_port')
            cmd = 'echo "show info" |nc %s %s -w 1 -v|grep Name' % (server_ip, haproxy_sock_port)
            out = server_mod.subprocess_execute(cmd)
            for k in out[0]:
                if "Name" in k:
                    return 'up'
            else:
                return 'down'
    if ('2' in user_services and service == 'nginx') or ('4' in user_services and service == 'apache'):
        stats_port = sql.get_setting(f'{service}_stats_port')

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(5)

            try:
                if sock.connect_ex((server_ip, stats_port)) == 0:
                    return 'up'
                else:
                    return 'down'
            except Exception as e:
                return f'down {e}'
