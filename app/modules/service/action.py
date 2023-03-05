import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common
import modules.service.common as service_common


def action_haproxy(server_ip: str, action: str) -> None:
    haproxy_service_name = "haproxy"

    if action not in ('start', 'stop', 'reload', 'restart'):
        print('error: wrong action')
        return

    service_common.is_restarted(server_ip, action)

    if service_common.check_haproxy_config(server_ip):
        server_id = sql.select_server_id_by_ip(server_ip=server_ip)
        is_docker = sql.select_service_setting(server_id, 'haproxy', 'dockerized')

        if action == 'restart':
            service_common.is_not_allowed_to_restart(server_id, 'haproxy')

        if is_docker == '1':
            container_name = sql.get_setting('haproxy_container_name')
            commands = [f"sudo docker {action} {container_name}"]
        else:
            haproxy_enterprise = sql.select_service_setting(server_id, 'haproxy', 'haproxy_enterprise')
            if haproxy_enterprise == '1':
                haproxy_service_name = "hapee-2.0-lb"
            commands = [f"sudo systemctl {action} {haproxy_service_name}"]

        server_mod.ssh_command(server_ip, commands)
        roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='haproxy')
        print(f"success: HAProxy has been {action}")
    else:
        print("error: Bad config, check please")


def action_nginx(server_ip: str, action: str) -> None:
    if action not in ('start', 'stop', 'reload', 'restart'):
        print('error: wrong action')
        return

    service_common.is_restarted(server_ip, action)

    if service_common.check_nginx_config(server_ip):
        server_id = sql.select_server_id_by_ip(server_ip=server_ip)

        if action == 'restart':
            service_common.is_not_allowed_to_restart(server_id, 'nginx')
        is_docker = sql.select_service_setting(server_id, 'nginx', 'dockerized')

        if is_docker == '1':
            container_name = sql.get_setting('nginx_container_name')
            commands = [f"sudo docker {action} {container_name}"]
        else:
            commands = [f"sudo systemctl {action} nginx"]
        server_mod.ssh_command(server_ip, commands)
        roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='nginx')
        print(f"success: NGINX has been {action}")
    else:
        print("error: Bad config, check please")


def action_keepalived(server_ip: str, action: str) -> None:
    if action not in ('start', 'stop', 'reload', 'restart'):
        print('error: wrong action')
        return

    service_common.is_restarted(server_ip, action)

    commands = [f"sudo systemctl {action} keepalived"]
    server_mod.ssh_command(server_ip, commands)
    roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='keepalived')
    print(f"success: Keepalived has been {action}")


def action_apache(server_ip: str, action: str) -> None:
    if action not in ('start', 'stop', 'reload', 'restart'):
        print('error: wrong action')
        return

    service_common.is_restarted(server_ip, action)

    server_id = sql.select_server_id_by_ip(server_ip)

    if action == 'restart':
        service_common.is_not_allowed_to_restart(server_id, 'apache')

    is_docker = sql.select_service_setting(server_id, 'apache', 'dockerized')
    if is_docker == '1':
        container_name = sql.get_setting('apache_container_name')
        commands = [f"sudo docker {action} {container_name}"]
    else:
        service_apache_name = service_common.get_correct_apache_service_name(None, server_id)

        commands = [f"sudo systemctl {action} {service_apache_name}"]
    server_mod.ssh_command(server_ip, commands)
    roxywi_common.logging(server_ip, f'Service has been {action}ed', roxywi=1, login=1, keep_history=1, service='apache')
    print(f"success: Apache has been {action}")


def action_haproxy_waf(server_ip: str, action: str) -> None:
    if action not in ('start', 'stop', 'reload', 'restart'):
        print('error: wrong action')
        return

    service_common.is_restarted(server_ip, action)

    roxywi_common.logging(server_ip, f'HAProxy WAF service has been {action}ed', roxywi=1, login=1, keep_history=1,
                  service='haproxy')
    commands = [f"sudo systemctl {action} waf"]
    server_mod.ssh_command(server_ip, commands)


def action_nginx_waf(server_ip: str, action: str) -> None:
    config_dir = common.return_nice_path(sql.get_setting('nginx_dir'))

    if action not in ('start', 'stop'):
        print('error: wrong action')
        return

    service_common.is_restarted(server_ip, action)

    waf_new_state = 'on' if action == 'start' else 'off'
    waf_old_state = 'off' if action == 'start' else 'on'

    roxywi_common.logging(server_ip, f'NGINX WAF service has been {action}ed', roxywi=1, login=1, keep_history=1,
                          service='nginx')
    commands = [f"sudo sed -i 's/modsecurity {waf_old_state}/modsecurity {waf_new_state}/g' {config_dir}nginx.conf"
                f" && sudo systemctl reload nginx"]
    server_mod.ssh_command(server_ip, commands)
