import distro
from flask import render_template, request, jsonify, g
from flask_login import login_required

from app.routes.metric import bp
import app.modules.db.sql as sql
from middleware import check_services, get_user_params
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.roxywi.metrics as metric
import app.modules.roxywi.common as roxywi_common


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('/<service>')
@check_services
@get_user_params()
def metrics(service):
    roxywi_common.check_user_group_for_flask()
    servers = ''
    services = '0'

    try:
        if distro.id() == 'ubuntu':
            cmd = "apt list --installed 2>&1 |grep roxy-wi-metrics"
        else:
            cmd = "rpm -q roxy-wi-metrics-* |awk -F\"metrics\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
        service_ver, stderr = server_mod.subprocess_execute(cmd)

        if not stderr:
            if len(service_ver) > 0:
                if 'is not installed' in service_ver[0]:
                    servers = ''
                else:
                    services = '1'
                    if service == 'nginx':
                        servers = sql.select_nginx_servers_metrics_for_master()
                    elif service == 'apache':
                        servers = sql.select_apache_servers_metrics_for_master()
                    else:
                        group_id = roxywi_common.get_user_group(id=1)
                        servers = sql.select_servers_metrics(group_id)
            else:
                servers = ''
    except Exception as e:
        return f'error: on Metrics page: {e}', 500

    kwargs = {
        'autorefresh': 1,
        'servers': servers,
        'service': service,
        'services': services,
        'service_desc': sql.select_service(service),
        'user_subscription': roxywi_common.return_user_subscription(),
        'lang': g.user_params['lang']
    }

    return render_template('metrics.html', **kwargs)


@bp.route('/cpu', methods=['POST'])
def metrics_cpu():
    metrics_type = common.checkAjaxInput(request.form.get('ip'))

    return jsonify(metric.show_cpu_metrics(metrics_type))


@bp.route('/ram', methods=['POST'])
def metrics_ram():
    metrics_type = common.checkAjaxInput(request.form.get('ip'))

    return jsonify(metric.show_ram_metrics(metrics_type))


@bp.route('/<service>/table-metrics')
@check_services
def table_metrics(service):
    roxywi_common.check_user_group_for_flask()
    lang = roxywi_common.get_user_lang_for_flask()
    group_id = roxywi_common.get_user_group(id=1)

    if service in ('nginx', 'apache'):
        metrics = sql.select_service_table_metrics(service, group_id)
    else:
        metrics = sql.select_table_metrics(group_id)

    return render_template('ajax/table_metrics.html', table_stat=metrics, service=service, lang=lang)


@bp.post('/<service>/<server_ip>')
@check_services
def show_metric(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    hostname = sql.get_hostname_by_server_ip(server_ip)
    time_range = common.checkAjaxInput(request.form.get('time_range'))

    if service in ('nginx', 'apache', 'waf'):
        return jsonify(metric.service_metrics(server_ip, hostname, service, time_range))
    elif service == 'haproxy':
        return jsonify(metric.haproxy_metrics(server_ip, hostname, time_range))

    return 'error: Wrong service'


@bp.post('/<service>/<server_ip>/http')
@check_services
def show_http_metric(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    hostname = sql.get_hostname_by_server_ip(server_ip)
    time_range = common.checkAjaxInput(request.form.get('time_range'))

    if service == 'haproxy':
        return jsonify(metric.haproxy_http_metrics(server_ip, hostname, time_range))

    return 'error: Wrong service'
