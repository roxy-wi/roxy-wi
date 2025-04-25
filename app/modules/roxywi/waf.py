from flask import render_template

import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
import app.modules.db.user as user_sql
import app.modules.db.server as server_sql
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common


def waf_overview(serv: str, waf_service: str, claims: dict) -> str:
    server = server_sql.get_server_by_ip(serv)
    role = user_sql.get_user_role_in_group(claims['user_id'], claims['group'])
    returned_servers = []
    waf = ''
    metrics_en = 0
    waf_process = ''
    waf_mode = ''
    is_waf_on_server = 0

    if waf_service == 'haproxy':
        is_waf_on_server = server.haproxy
    elif waf_service == 'nginx':
        is_waf_on_server = server.nginx

    if is_waf_on_server == 1:
        config_path = sql.get_setting(f'{waf_service}_dir')
        if waf_service == 'haproxy':
            waf = waf_sql.select_waf_servers(server.ip)
            metrics_en = waf_sql.select_waf_metrics_enable_server(server.ip)
        elif waf_service == 'nginx':
            waf = waf_sql.select_waf_nginx_servers(server.ip)
        try:
            waf_len = len(waf)
        except Exception:
            waf_len = 0

        if waf_len >= 1:
            if waf_service == 'haproxy':
                command = "ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l"
            elif waf_service == 'nginx':
                command = f"grep 'modsecurity on' {common.return_nice_path(config_path)}* --exclude-dir=waf -Rs |wc -l"
            commands1 = f"grep SecRuleEngine {config_path}/waf/modsecurity.conf |grep -v '#' |awk '{{print $2}}'"
            waf_process = server_mod.ssh_command(server.ip, command)
            waf_mode = server_mod.ssh_command(server.ip, commands1).strip()

            server_status = (server.hostname,
                             server.ip,
                             waf_process,
                             waf_mode,
                             metrics_en,
                             waf_len,
                             server.server_id)
        else:
            server_status = (server.hostname,
                             server.ip,
                             waf_process,
                             waf_mode,
                             metrics_en,
                             waf_len,
                             server.server_id)
    returned_servers.append(server_status)

    lang = roxywi_common.get_user_lang_for_flask()
    servers_sorted = sorted(returned_servers, key=common.get_key)

    return render_template('ajax/overviewWaf.html', service_status=servers_sorted, role=role, waf_service=waf_service, lang=lang)


def change_waf_mode(waf_mode: str, server_id: int, service: str):
    serv = server_sql.get_server(server_id)

    if service == 'haproxy':
        config_dir = sql.get_setting('haproxy_dir')
    elif service == 'nginx':
        config_dir = sql.get_setting('nginx_dir')

    commands = f"sudo sed -i 's/^SecRuleEngine.*/SecRuleEngine {waf_mode}/' {config_dir}/waf/modsecurity.conf"

    try:
        server_mod.ssh_command(serv.ip, commands)
    except Exception as e:
        return str(e)

    roxywi_common.logging(serv.hostname, f'Has been changed WAF mod to {waf_mode}')


def switch_waf_rule(serv: str, enable: int, rule_id: int):
    haproxy_path = sql.get_setting('haproxy_dir')
    rule_file = waf_sql.select_waf_rule_by_id(rule_id)
    conf_file_path = haproxy_path + '/waf/modsecurity.conf'
    rule_file_path = f'Include {haproxy_path}/waf/rules/{rule_file}'

    if enable == '0':
        cmd = "sudo sed -i 's!" + rule_file_path + "!#" + rule_file_path + "!' " + conf_file_path
        en_for_log = 'disabled'
    else:
        cmd = "sudo sed -i 's!#" + rule_file_path + "!" + rule_file_path + "!' " + conf_file_path
        en_for_log = 'enabled'

    try:
        roxywi_common.logging('WAF', f' Has been {en_for_log} WAF rule: {rule_file} for the server {serv}')
    except Exception:
        pass

    waf_sql.update_enable_waf_rules(rule_id, serv, enable)
    server_mod.ssh_command(serv, cmd)


def create_waf_rule(serv: str, service: str, json_data: dict) -> int:
    new_waf_rule = common.checkAjaxInput(json_data['new_waf_rule'])
    new_rule_desc = common.checkAjaxInput(json_data['new_rule_description'])
    rule_file = common.checkAjaxInput(json_data['new_rule_file'])
    rule_file = f'{rule_file}.conf'
    waf_path = ''

    if service == 'haproxy':
        waf_path = common.return_nice_path(sql.get_setting('haproxy_dir'))
    elif service == 'nginx':
        waf_path = common.return_nice_path(sql.get_setting('nginx_dir'))

    conf_file_path = f'{waf_path}waf/modsecurity.conf'
    rule_file_path = f'{waf_path}waf/rules/{rule_file}'

    cmd = f"sudo echo Include {rule_file_path} >> {conf_file_path} && sudo touch {rule_file_path}"
    server_mod.ssh_command(serv, cmd)
    last_id = waf_sql.insert_new_waf_rule(new_waf_rule, rule_file, new_rule_desc, service, serv)

    try:
        roxywi_common.logging('WAF', f'A new rule has been created {rule_file} on the server {serv}')
    except Exception:
        pass

    return last_id
