from flask import render_template, abort

import modules.db.sql as sql
import modules.roxywi.common as roxywi_common
import modules.server.server as server_mod


def create_smon(name: str, hostname: str, port: int, enable: int, url: str, body: str, group: int, desc: str, telegram: int,
                slack: int, pd: int, packet_size: int, check_type: int, resolver: str, record_type: str, user_group: int,
                http_method: str, show_new=1) -> bool:
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

    last_id = sql.insert_smon(name, enable, group, desc, telegram, slack, pd, user_group, check_type)

    if check_type == 'ping':
        sql.insert_smon_ping(last_id, hostname, packet_size)
    elif check_type == 'tcp':
        sql.insert_smon_tcp(last_id, hostname, port)
    elif check_type == 'http':
        sql.insert_smon_http(last_id, url, body, http_method)
    elif check_type == 'dns':
        sql.insert_smon_dns(last_id, hostname, port, resolver, record_type)

    if last_id:
        roxywi_common.logging('SMON', f' A new server {name} to SMON has been add ', roxywi=1, login=1)

    if last_id and show_new:
        return last_id
    else:
        return False


def update_smon(smon_id, name, ip, port, en, url, body, telegram, slack, pd, group, desc, check_type,
                resolver, record_type, packet_size, http_method) -> str:
    is_edited = False

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
        if sql.update_smon(smon_id, name, telegram, slack, pd, group, desc, en):
            if check_type == 'http':
                is_edited = sql.update_smonHttp(smon_id, url, body, http_method)
            elif check_type == 'tcp':
                is_edited = sql.update_smonTcp(smon_id, ip, port)
            elif check_type == 'ping':
                is_edited = sql.update_smonPing(smon_id, ip, packet_size)
            elif check_type == 'dns':
                is_edited = sql.update_smonDns(smon_id, ip, port, resolver, record_type)

            if is_edited:
                roxywi_common.logging('SMON', f' The SMON server {name} has been update ', roxywi=1, login=1)
                return "Ok"
    except Exception as e:
        raise Exception(f'error: Cannot update the server: {e}')


def show_smon(sort: str) -> str:
    user_group = roxywi_common.get_user_group(id=1)
    lang = roxywi_common.get_user_lang_for_flask()

    return render_template('ajax/smon/smon_dashboard.html', smon=sql.smon_list(user_group), sort=sort, lang=lang, update=1)


def delete_smon(smon_id, user_group) -> str:
    try:
        if sql.delete_smon(smon_id, user_group):
            roxywi_common.logging('SMON', ' The server from SMON has been delete ', roxywi=1, login=1)
            return 'Ok'
    except Exception as e:
        raise Exception(f'error: Cannot delete the server {e}')


def history_metrics(server_id: int) -> dict:
    metric = sql.select_smon_history(server_id)

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


def history_statuses(dashboard_id: int) -> None:
    smon_statuses = sql.select_smon_history(dashboard_id)

    return render_template('ajax/smon/history_status.html', smon_statuses=smon_statuses)


def history_cur_status(dashboard_id: int, check_id: int) -> None:
    cur_status = sql.get_last_smon_status_by_check(dashboard_id)
    smon = sql.select_one_smon(dashboard_id, check_id)

    return render_template('ajax/smon/cur_status.html', cur_status=cur_status, smon=smon)


def return_smon_status():
    cmd = "systemctl is-active roxy-wi-smon"
    smon_status, stderr = server_mod.subprocess_execute(cmd)

    return smon_status, stderr


def check_uptime(smon_id: str) -> int:
    count_checks = sql.get_smon_history_count_checks(smon_id)

    try:
        uptime = round(count_checks['up'] * 100 / count_checks['total'], 2)
    except Exception:
        uptime = 0

    return uptime


def create_status_page(name: str, slug: str, desc: str, checks: list) -> str:
    group_id = roxywi_common.get_user_group(id=1)

    try:
        page_id = sql.add_status_page(name, slug, desc, group_id, checks)
    except Exception as e:
        raise Exception(f'{e}')

    pages = sql.select_status_page_by_id(page_id)

    return render_template('ajax/smon/status_pages.html', pages=pages)


def edit_status_page(page_id: int, name: str, slug: str, desc: str, checks: list) -> str:
    sql.delete_status_page_checks(page_id)

    try:
        sql.add_status_page_checks(page_id, checks)
        sql.edit_status_page(page_id, name, slug, desc)
    except Exception as e:
        return f'error: Cannot update update status page: {e}'

    pages = sql.select_status_page_by_id(page_id)

    return render_template('ajax/smon/status_pages.html', pages=pages)


def show_status_page(slug: str) -> str:
    page = sql.select_status_page(slug)
    checks_status = {}
    if not page:
        abort(404, 'Not found status page')

    for p in page:
        page_id = p.id

    checks = sql.select_status_page_checks(page_id)

    for check in checks:
        name = ''
        desc = ''
        group = ''
        check_type = ''
        check_id = str(check.check_id)
        smon = sql.select_smon_by_id(check_id)
        for s in smon:
            name = s.name
            desc = s.desc
            group = s.group
            check_type = s.check_type
            en = s.en
        uptime = check_uptime(check_id)

        checks_status[check_id] = {'uptime': uptime, 'name': name, 'desc': desc, 'group': group, 'check_type': check_type, 'en': en}

    return render_template('smon/status_page.html', page=page, checks_status=checks_status)
