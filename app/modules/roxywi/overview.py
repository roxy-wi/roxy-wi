import os
import http.cookies

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.common as roxywi_common
import modules.server.server as server_mod
import modules.service.common as service_common


def user_ovw() -> None:
    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
    template = env.get_template('/show_users_ovw.html')

    user_params = roxywi_common.get_users_params()
    users_groups = sql.select_user_groups_with_names(1, all=1)
    user_group = roxywi_common.get_user_group(id=1)

    if (user_params['role'] == 2 or user_params['role'] == 3) and int(user_group) != 1:
        users = sql.select_users(group=user_group)
    else:
        users = sql.select_users()

    template = template.render(users=users, users_groups=users_groups)
    print(template)


def show_sub_ovw() -> None:
    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    template = env.get_template('ajax/show_sub_ovw.html')
    template = template.render(sub=sql.select_user_all())
    print(template)


def show_overview(serv) -> None:
    import asyncio

    async def async_get_overview(serv1, serv2, user_uuid, server_id):
        user_id = sql.get_user_id_by_uuid(user_uuid)
        user_services = sql.select_user_services(user_id)

        haproxy = sql.select_haproxy(serv) if '1' in user_services else 0
        nginx = sql.select_nginx(serv) if '2' in user_services else 0
        keepalived = sql.select_keepalived(serv) if '3' in user_services else 0
        apache = sql.select_apache(serv) if '4' in user_services else 0

        waf = sql.select_waf_servers(serv2)
        haproxy_process = ''
        keepalived_process = ''
        nginx_process = ''
        apache_process = ''
        waf_process = ''

        try:
            waf_len = len(waf)
        except Exception:
            waf_len = 0

        if haproxy:
            cmd = f'echo "show info" |nc {serv2} {sql.get_setting("haproxy_sock_port")} -w 1|grep -e "Process_num"'
            haproxy_process = service_common.server_status(server_mod.subprocess_execute(cmd))

        if nginx:
            nginx_cmd = f'echo "something" |nc {serv2} {sql.get_setting("nginx_stats_port")} -w 1'
            nginx_process = service_common.server_status(server_mod.subprocess_execute(nginx_cmd))

        if apache:
            apache_cmd = f'echo "something" |nc {serv2} {sql.get_setting("apache_stats_port")} -w 1'
            apache_process = service_common.server_status(server_mod.subprocess_execute(apache_cmd))

        if keepalived:
            command = ["ps ax |grep keepalived|grep -v grep|wc -l|tr -d '\n'"]
            try:
                keepalived_process = server_mod.ssh_command(serv2, command)
            except Exception as e:
                print(f'error: {e} for server {serv2}')
                return

        if waf_len >= 1:
            command = ["ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l"]
            try:
                waf_process = server_mod.ssh_command(serv2, command)
            except Exception as e:
                print(f'error: {e} for server {serv2}')
                return

        server_status = (serv1,
                         serv2,
                         haproxy,
                         haproxy_process,
                         waf_process,
                         waf,
                         keepalived,
                         keepalived_process,
                         nginx,
                         nginx_process,
                         server_id,
                         apache,
                         apache_process)
        return server_status

    async def get_runner_overview():
        env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True,
                          extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'])

        servers = []
        template = env.get_template('overview.html')
        cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
        user_uuid = cookie.get('uuid')
        futures = [async_get_overview(server[1], server[2], user_uuid.value, server[0]) for server in
                   sql.select_servers(server=serv)]
        for i, future in enumerate(asyncio.as_completed(futures)):
            result = await future
            servers.append(result)
        servers_sorted = sorted(servers, key=common.get_key)
        template = template.render(service_status=servers_sorted, role=sql.get_user_role_by_uuid(user_uuid.value))
        print(template)

    ioloop = asyncio.get_event_loop()
    ioloop.run_until_complete(get_runner_overview())
    ioloop.close()
