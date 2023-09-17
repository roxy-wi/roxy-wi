import os
import sys

import distro
from flask import render_template, request, jsonify, redirect, url_for
from flask_login import login_required

from app.routes.metric import bp

sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app'))

import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxywi.metrics as metric
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('/<service>')
def metrics(service):
    try:
        user_params = roxywi_common.get_users_params()
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    service_desc = sql.select_service(service)
    roxywi_common.check_user_group_for_flask()

    is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id)

    if is_redirect != 'ok':
        return redirect(url_for(f'{is_redirect}'))

    try:
        if distro.id() == 'ubuntu':
            cmd = "apt list --installed 2>&1 |grep roxy-wi-metrics"
        else:
            cmd = "rpm -q roxy-wi-metrics-* |awk -F\"metrics\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
        service_ver, stderr = server_mod.subprocess_execute(cmd)
        services = '0'

        if not stderr:
            if service_ver[0] == ' is not installed' or service_ver == '':
                servers = ''
            else:
                services = '1'
                if service == 'nginx':
                    user_params['servers'] = sql.select_nginx_servers_metrics_for_master()
                elif service == 'apache':
                    user_params['servers'] = sql.select_apache_servers_metrics_for_master()
                else:
                    group_id = roxywi_common.get_user_group(id=1)
                    user_params['servers'] = sql.select_servers_metrics(group_id)
    except Exception as e:
        return f'error: on Metrics page: {e}', 500

    user_subscription = roxywi_common.return_user_subscription()

    return render_template(
        'metrics.html', h2=1, autorefresh=1, role=user_params['role'], user=user, servers=user_params['servers'],
        services=services, user_services=user_params['user_services'], service=service,
        user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'],
        token=user_params['token'], lang=user_params['lang'], service_desc=service_desc
    )


@bp.route('/cpu', methods=['POST'])
def metrics_cpu():
    metrics_type = common.checkAjaxInput(request.form.get('ip'))

    return jsonify(metric.show_cpu_metrics(metrics_type))


@bp.route('/ram', methods=['POST'])
def metrics_ram():
    metrics_type = common.checkAjaxInput(request.form.get('ip'))

    return jsonify(metric.show_ram_metrics(metrics_type))


@bp.route('/<service>/table-metrics')
def table_metrics(service):
    roxywi_common.check_user_group_for_flask()
    lang = roxywi_common.get_user_lang_for_flask()
    group_id = roxywi_common.get_user_group(id=1)

    if service in ('nginx', 'apache'):
        metrics = sql.select_service_table_metrics(service, group_id)
    else:
        metrics = sql.select_table_metrics(group_id)

    return render_template('ajax/table_metrics.html', table_stat=metrics, service=service, lang=lang)


@bp.route('/<service>/<server_ip>', methods=['POST'])
def show_metric(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    hostname = sql.get_hostname_by_server_ip(server_ip)
    time_range = common.checkAjaxInput(request.form.get('time_range'))

    if service in ('nginx', 'apache', 'waf'):
        return jsonify(metric.service_metrics(server_ip, hostname, service, time_range))
    elif service == 'haproxy':
        return jsonify(metric.haproxy_metrics(server_ip, hostname, time_range))

    return 'error: Wrong service'


@bp.route('/<service>/<server_ip>/http', methods=['POST'])
def show_http_metric(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    hostname = sql.get_hostname_by_server_ip(server_ip)
    time_range = common.checkAjaxInput(request.form.get('time_range'))

    if service == 'haproxy':
        return jsonify(metric.haproxy_http_metrics(server_ip, hostname, time_range))

    return 'error: Wrong service'
