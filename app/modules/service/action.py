import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common
import modules.service.common as service_common


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


def action_haproxy(server_ip: str, action: str) -> str:
    haproxy_service_name = "haproxy"

    try:
        service_common.is_restarted(server_ip, action)
    except Exception as e:
        return str(e)

    if service_common.check_haproxy_config(server_ip):
        server_id = sql.select_server_id_by_ip(server_ip=server_ip)
        is_docker = sql.select_service_setting(server_id, 'haproxy', 'dockerized')

        if action == 'restart':
            try:
                service_common.is_not_allowed_to_restart(server_id, 'haproxy')
            except Exception as e:
                return str(e)

        if is_docker == '1':
            container_name = sql.get_setting('haproxy_container_name')
            commands = [f"sudo docker {action} {container_name}"]
        else:
            haproxy_enterprise = sql.select_service_setting(server_id, 'haproxy', 'haproxy_enterprise')
            if haproxy_enterprise == '1':
                haproxy_service_name = "hapee-2.0-lb"
            commands = [f"sudo systemctl {action} {haproxy_service_name}"]
        server_mod.ssh_command(server_ip, commands, timeout=5)
        roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='haproxy')
        return f"success: HAProxy has been {action}"
    else:
        return "error: Bad config, check please"


def action_nginx(server_ip: str, action: str) -> str:
    try:
        service_common.is_restarted(server_ip, action)
    except Exception as e:
        return str(e)

    if service_common.check_nginx_config(server_ip):
        server_id = sql.select_server_id_by_ip(server_ip=server_ip)

        if action == 'restart':
            try:
                service_common.is_not_allowed_to_restart(server_id, 'nginx')
            except Exception as e:
                return str(e)
        is_docker = sql.select_service_setting(server_id, 'nginx', 'dockerized')

        if is_docker == '1':
            container_name = sql.get_setting('nginx_container_name')
            commands = [f"sudo docker {action} {container_name}"]
        else:
            commands = [f"sudo systemctl {action} nginx"]
        server_mod.ssh_command(server_ip, commands, timeout=5)
        roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='nginx')
        return f"success: NGINX has been {action}"
    else:
        return "error: Bad config, check please"


def action_keepalived(server_ip: str, action: str) -> str:
    try:
        service_common.is_restarted(server_ip, action)
    except Exception as e:
        return str(e)

    commands = [f"sudo systemctl {action} keepalived"]
    server_mod.ssh_command(server_ip, commands)
    roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='keepalived')
    return f"success: Keepalived has been {action}"


def action_apache(server_ip: str, action: str) -> str:
    try:
        service_common.is_restarted(server_ip, action)
    except Exception as e:
        return str(e)

    server_id = sql.select_server_id_by_ip(server_ip)

    if action == 'restart':
        try:
            service_common.is_not_allowed_to_restart(server_id, 'apache')
        except Exception as e:
            return str(e)

    is_docker = sql.select_service_setting(server_id, 'apache', 'dockerized')
    if is_docker == '1':
        container_name = sql.get_setting('apache_container_name')
        commands = [f"sudo docker {action} {container_name}"]
    else:
        service_apache_name = service_common.get_correct_apache_service_name(None, server_id)

        commands = [f"sudo systemctl {action} {service_apache_name}"]
    server_mod.ssh_command(server_ip, commands, timeout=5)
    roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='apache')
    return f"success: Apache has been {action}"


def action_haproxy_waf(server_ip: str, action: str) -> str:
    try:
        service_common.is_restarted(server_ip, action)
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
        service_common.is_restarted(server_ip, action)
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
