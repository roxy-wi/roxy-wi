import app.modules.db.sql as sql
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.service.common as service_common


def common_action(server_ip: str, action: str, service: str) -> str:
    action_functions = {
        'haproxy': action_haproxy,
        'nginx': action_nginx,
        'keepalived': action_keepalived,
        'apache': action_apache,
        'waf_haproxy': action_haproxy_waf,
        'waf_nginx': action_nginx_waf
    }

    return action_functions[service](server_ip, action)


def get_action_command(service: str, action: str, server_id: int) -> str:
    """
    :param service: The name of the service for which the action command is needed.
    :param action: The action to be performed on the service (e.g. start, stop, restart).
    :param server_id: The ID of the server.

    :return: A list containing the action command that needs to be executed.
    """
    is_docker = sql.select_service_setting(server_id, service, 'dockerized')
    if is_docker == '1':
        container_name = sql.get_setting(f'{service}_container_name')
        if action == 'reload':
            action = 'kill -S HUP'
        commands = f"sudo docker {action} {container_name}"
    else:
        service_name = service_common.get_correct_service_name(service, server_id)
        commands = f"sudo systemctl {action} {service_name}"

    return commands


def action_haproxy(server_ip: str, action: str) -> str:
    try:
        service_common.is_protected(server_ip, action)
    except Exception as e:
        return str(e)

    if not service_common.check_haproxy_config(server_ip):
        return "error: Bad config, check please"

    server_id = sql.select_server_id_by_ip(server_ip=server_ip)

    if service_common.is_not_allowed_to_restart(server_id, 'haproxy', action):
        return f'error: This server is not allowed to be restarted'

    commands = [get_action_command('haproxy', action, server_id)]
    server_mod.ssh_command(server_ip, commands, timeout=5)
    roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='haproxy')
    return f"success: HAProxy has been {action}"


def action_nginx(server_ip: str, action: str) -> str:
    try:
        service_common.is_protected(server_ip, action)
    except Exception as e:
        return str(e)

    check_config = service_common.check_nginx_config(server_ip)
    if check_config != 'ok':
        return f"error: Bad config, check please {check_config}"

    server_id = sql.select_server_id_by_ip(server_ip=server_ip)

    if service_common.is_not_allowed_to_restart(server_id, 'nginx', action):
        return f'error: This server is not allowed to be restarted'

    commands = [get_action_command('nginx', action, server_id)]
    server_mod.ssh_command(server_ip, commands, timeout=5)
    roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='nginx')
    return f"success: NGINX has been {action}"


def action_keepalived(server_ip: str, action: str) -> str:
    try:
        service_common.is_protected(server_ip, action)
    except Exception as e:
        return str(e)

    commands = [f"sudo systemctl {action} keepalived"]
    server_mod.ssh_command(server_ip, commands)
    roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='keepalived')
    return f"success: Keepalived has been {action}"


def action_apache(server_ip: str, action: str) -> str:
    try:
        service_common.is_protected(server_ip, action)
    except Exception as e:
        return str(e)

    server_id = sql.select_server_id_by_ip(server_ip)

    if service_common.is_not_allowed_to_restart(server_id, 'apache', action):
        return f'error: This server is not allowed to be restarted'

    commands = [get_action_command('apache', action, server_id)]
    server_mod.ssh_command(server_ip, commands, timeout=5)
    roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='apache')
    return f"success: Apache has been {action}"


def action_haproxy_waf(server_ip: str, action: str) -> str:
    try:
        service_common.is_protected(server_ip, action)
    except Exception as e:
        return str(e)

    roxywi_common.logging(
        server_ip, f'HAProxy WAF service has been {action}ed', roxywi=1, login=1, keep_history=1, service='haproxy'
    )
    commands = [f"sudo systemctl {action} waf"]
    server_mod.ssh_command(server_ip, commands)
    return f"success: WAF has been {action}"


def action_nginx_waf(server_ip: str, action: str) -> str:
    config_dir = common.return_nice_path(sql.get_setting('nginx_dir'))

    try:
        service_common.is_protected(server_ip, action)
    except Exception as e:
        return str(e)

    waf_new_state = 'on' if action == 'start' else 'off'
    waf_old_state = 'off' if action == 'start' else 'on'

    roxywi_common.logging(server_ip, f'NGINX WAF service has been {action}ed', roxywi=1, login=1, keep_history=1,
                          service='nginx')
    commands = [f"sudo sed -i 's/modsecurity {waf_old_state}/modsecurity {waf_new_state}/g' {config_dir}nginx.conf"
                f" && sudo systemctl reload nginx"]
    server_mod.ssh_command(server_ip, commands)

    return f"success: Apache has been {action}"


def check_service(server_ip: str, user_uuid: str, service: str) -> str:
    import socket
    from contextlib import closing

    user_id = sql.get_user_id_by_uuid(user_uuid)
    user_services = sql.select_user_services(user_id)

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
    if '2' in user_services:
        if service == 'nginx':
            nginx_stats_port = sql.get_setting('nginx_stats_port')

            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(5)

                try:
                    if sock.connect_ex((server_ip, nginx_stats_port)) == 0:
                        return 'up'
                    else:
                        return 'down'
                except Exception as e:
                    return 'down' + str(e)
    if '4' in user_services:
        if service == 'apache':
            apache_stats_port = sql.get_setting('apache_stats_port')

            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(5)

                try:
                    if sock.connect_ex((server_ip, apache_stats_port)) == 0:
                        return 'up'
                    else:
                        return 'down'
                except Exception as e:
                    return 'down' + str(e)
