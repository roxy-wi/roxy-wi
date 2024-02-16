from flask import render_template, abort

import app.modules.db.smon as smon_sql
import app.modules.common.common as common
import app.modules.tools.smon_agent as smon_agent
import app.modules.roxywi.common as roxywi_common


def create_smon(json_data, user_group, show_new=1) -> bool:
    name = common.checkAjaxInput(json_data['name'])
    hostname = common.checkAjaxInput(json_data['ip'])
    port = common.checkAjaxInput(json_data['port'])
    enable = common.checkAjaxInput(json_data['enabled'])
    url = common.checkAjaxInput(json_data['url'])
    body = common.checkAjaxInput(json_data['body'])
    group = common.checkAjaxInput(json_data['group'])
    desc = common.checkAjaxInput(json_data['desc'])
    telegram = common.checkAjaxInput(json_data['tg'])
    slack = common.checkAjaxInput(json_data['slack'])
    pd = common.checkAjaxInput(json_data['pd'])
    resolver = common.checkAjaxInput(json_data['resolver'])
    record_type = common.checkAjaxInput(json_data['record_type'])
    packet_size = common.checkAjaxInput(json_data['packet_size'])
    http_method = common.checkAjaxInput(json_data['http_method'])
    interval = common.checkAjaxInput(json_data['interval'])
    agent_id = common.checkAjaxInput(json_data['agent_id'])
    check_type = common.checkAjaxInput(json_data['check_type'])

    if agent_id == '':
        raise Exception('warning: Select an Agent first')

    if check_type == 'tcp':
        try:
            port = int(port)
        except Exception:
            raise Exception('SMON error: port must be a number')
        if port > 65535 or port < 0:
            raise Exception('SMON error: port must be 0-65535')

    if check_type == 'ping':
        if int(packet_size) < 16:
            raise Exception('SMON error: a packet size cannot be less than 16')

    last_id = smon_sql.insert_smon(name, enable, group, desc, telegram, slack, pd, user_group, check_type)

    if check_type == 'ping':
        smon_sql.insert_smon_ping(last_id, hostname, packet_size, interval, agent_id)
    elif check_type == 'tcp':
        smon_sql.insert_smon_tcp(last_id, hostname, port, interval, agent_id)
    elif check_type == 'http':
        smon_sql.insert_smon_http(last_id, url, body, http_method, interval, agent_id)
    elif check_type == 'dns':
        smon_sql.insert_smon_dns(last_id, hostname, port, resolver, record_type, interval, agent_id)

    if last_id:
        roxywi_common.logging('SMON', f' A new server {name} to SMON has been add ', roxywi=1, login=1)

    try:
        api_path = f'check/{last_id}'
        check_json = create_check_json(json_data)
        server_ip = smon_sql.select_server_ip_by_agent_id(agent_id)
        smon_agent.send_post_request_to_agent(agent_id, server_ip, api_path, check_json)
    except Exception as e:
        roxywi_common.logging('SMON', f'Cannot add check to the agent {server_ip}: {e}', roxywi=1, login=1)

    if last_id and show_new:
        return last_id
    else:
        return False


def update_smon(smon_id, json_data) -> str:
    name = common.checkAjaxInput(json_data['name'])
    hostname = common.checkAjaxInput(json_data['ip'])
    port = common.checkAjaxInput(json_data['port'])
    enabled = common.checkAjaxInput(json_data['enabled'])
    url = common.checkAjaxInput(json_data['url'])
    body = common.checkAjaxInput(json_data['body'])
    group = common.checkAjaxInput(json_data['group'])
    desc = common.checkAjaxInput(json_data['desc'])
    telegram = common.checkAjaxInput(json_data['tg'])
    slack = common.checkAjaxInput(json_data['slack'])
    pd = common.checkAjaxInput(json_data['pd'])
    resolver = common.checkAjaxInput(json_data['resolver'])
    record_type = common.checkAjaxInput(json_data['record_type'])
    packet_size = common.checkAjaxInput(json_data['packet_size'])
    http_method = common.checkAjaxInput(json_data['http_method'])
    interval = common.checkAjaxInput(json_data['interval'])
    agent_id = common.checkAjaxInput(json_data['agent_id'])
    check_type = common.checkAjaxInput(json_data['check_type'])
    is_edited = False

    if agent_id == '':
        raise Exception('warning: Select an Agent first')

    if check_type == 'tcp':
        try:
            port = int(port)
        except Exception:
            raise Exception('SMON error: port must number')
        if port > 65535 or port < 0:
            raise Exception('SMON error: port must be 0-65535')

    if check_type == 'ping':
        if int(packet_size) < 16:
            raise Exception('SMON error: a packet size cannot be less than 16')

    try:
        agent_id_old = smon_sql.get_agent_id_by_check_id(smon_id)
        agent_ip = smon_sql.get_agent_ip_by_id(agent_id_old)
        smon_agent.delete_check(agent_id_old, agent_ip, smon_id)
    except Exception as e:
        return f'{e}'

    try:
        if smon_sql.update_smon(smon_id, name, telegram, slack, pd, group, desc, enabled):
            if check_type == 'http':
                is_edited = smon_sql.update_smonHttp(smon_id, url, body, http_method, interval, agent_id)
            elif check_type == 'tcp':
                is_edited = smon_sql.update_smonTcp(smon_id, hostname, port, interval, agent_id)
            elif check_type == 'ping':
                is_edited = smon_sql.update_smonPing(smon_id, hostname, packet_size, interval, agent_id)
            elif check_type == 'dns':
                is_edited = smon_sql.update_smonDns(smon_id, hostname, port, resolver, record_type, interval, agent_id)

            if is_edited:
                roxywi_common.logging('SMON', f' The SMON server {name} has been update ', roxywi=1, login=1)
                try:
                    api_path = f'check/{smon_id}'
                    check_json = create_check_json(json_data)
                    server_ip = smon_sql.select_server_ip_by_agent_id(agent_id)
                    smon_agent.send_post_request_to_agent(agent_id, server_ip, api_path, check_json)
                except Exception as e:
                    roxywi_common.logging('SMON', f'error: Cannot add check to the agent {agent_ip}: {e}', roxywi=1, login=1)

                return "Ok"
    except Exception as e:
        raise Exception(f'error: Cannot update the server: {e}')


def create_check_json(json_data: dict) -> dict:
    check_type = json_data['check_type']
    check_json = {
        'check_type': check_type,
        'name': json_data['name'],
        'server_ip': json_data['ip'],
        'interval': json_data['interval'],
    }
    if check_type == 'ping':
        check_json.setdefault('packet_size', json_data['packet_size'])
    elif check_type == 'tcp':
        check_json.setdefault('port', json_data['port'])
    elif check_type == 'http':
        check_json.setdefault('url', json_data['url'])
        check_json.setdefault('body', json_data['body'])
        check_json.setdefault('http_method', json_data['http_method'])
    elif check_type == 'dns':
        check_json.setdefault('port', json_data['port'])
        check_json.setdefault('resolver', json_data['resolver'])
        check_json.setdefault('record_type', json_data['record_type'])

    return check_json


def show_smon(sort: str) -> str:
    user_group = roxywi_common.get_user_group(id=1)
    lang = roxywi_common.get_user_lang_for_flask()

    return render_template('ajax/smon/smon_dashboard.html', smon=smon_sql.smon_list(user_group), sort=sort, lang=lang, update=1)


def delete_smon(smon_id, user_group) -> str:
    try:
        agent_id = smon_sql.get_agent_id_by_check_id(smon_id)
        server_ip = smon_sql.get_agent_ip_by_id(agent_id)
        smon_agent.delete_check(agent_id, server_ip, smon_id)
    except Exception as e:
        roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'error: Cannot delete check: {e}', roxywi=1, login=1)
    try:
        if smon_sql.delete_smon(smon_id, user_group):
            roxywi_common.logging('SMON', ' The server from SMON has been delete ', roxywi=1, login=1)
            return 'Ok'
    except Exception as e:
        raise Exception(f'error: Cannot delete the server {e}')


def history_metrics(server_id: int) -> dict:
    metric = smon_sql.select_smon_history(server_id)

    metrics = {'chartData': {}}
    metrics['chartData']['labels'] = {}
    labels = ''
    curr_con = ''

    for i in reversed(metric):
        labels += f'{i.date.time()},'
        curr_con += f'{i.response_time},'

    metrics['chartData']['labels'] = labels
    metrics['chartData']['curr_con'] = curr_con

    return metrics


def history_statuses(dashboard_id: int) -> str:
    smon_statuses = smon_sql.select_smon_history(dashboard_id)

    return render_template('ajax/smon/history_status.html', smon_statuses=smon_statuses)


def history_cur_status(dashboard_id: int, check_id: int) -> str:
    cur_status = smon_sql.get_last_smon_status_by_check(dashboard_id)
    smon = smon_sql.select_one_smon(dashboard_id, check_id)

    return render_template('ajax/smon/cur_status.html', cur_status=cur_status, smon=smon)


def check_uptime(smon_id: int) -> int:
    count_checks = smon_sql.get_smon_history_count_checks(smon_id)

    try:
        uptime = round(count_checks['up'] * 100 / count_checks['total'], 2)
    except Exception:
        uptime = 0

    return uptime


def create_status_page(name: str, slug: str, desc: str, checks: list) -> str:
    group_id = roxywi_common.get_user_group(id=1)

    try:
        page_id = smon_sql.add_status_page(name, slug, desc, group_id, checks)
    except Exception as e:
        raise Exception(f'{e}')

    pages = smon_sql.select_status_page_by_id(page_id)

    return render_template('ajax/smon/status_pages.html', pages=pages)


def edit_status_page(page_id: int, name: str, slug: str, desc: str, checks: list) -> str:
    smon_sql.delete_status_page_checks(page_id)

    try:
        smon_sql.add_status_page_checks(page_id, checks)
        smon_sql.edit_status_page(page_id, name, slug, desc)
    except Exception as e:
        return f'error: Cannot update update status page: {e}'

    pages = smon_sql.select_status_page_by_id(page_id)

    return render_template('ajax/smon/status_pages.html', pages=pages)


def show_status_page(slug: str) -> str:
    page = smon_sql.select_status_page(slug)
    checks_status = {}
    if not page:
        abort(404, 'Not found status page')

    for p in page:
        page_id = p.id

    checks = smon_sql.select_status_page_checks(page_id)

    for check in checks:
        name = ''
        desc = ''
        group = ''
        check_type = ''
        check_id = str(check.check_id)
        smon = smon_sql.select_smon_by_id(check_id)
        uptime = check_uptime(check_id)
        en = ''
        for s in smon:
            name = s.name
            desc = s.desc
            check_type = s.check_type
            en = s.en
            group = s.group if s.group else 'No group'

        checks_status[check_id] = {'uptime': uptime, 'name': name, 'desc': desc, 'group': group, 'check_type': check_type, 'en': en}

    return render_template('smon/status_page.html', page=page, checks_status=checks_status)


def avg_status_page_status(page_id: int) -> str:
    page_id = int(page_id)
    checks = smon_sql.select_status_page_checks(page_id)

    for check in checks:
        check_id = str(check.check_id)
        if not smon_sql.get_last_smon_status_by_check(check_id):
            return '0'

    return '1'
