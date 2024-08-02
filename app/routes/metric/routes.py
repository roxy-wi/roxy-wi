import json
import time

import distro
from flask import render_template, request, jsonify, g, Response, stream_with_context
from flask_jwt_extended import jwt_required

from app.routes.metric import bp
import app.modules.db.server as server_sql
import app.modules.db.metric as metric_sql
import app.modules.db.service as service_sql
from app.middleware import check_services, get_user_params
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.roxywi.metrics as metric
import app.modules.roxywi.common as roxywi_common


@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
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
                        servers = metric_sql.select_nginx_servers_metrics_for_master()
                    elif service == 'apache':
                        servers = metric_sql.select_apache_servers_metrics_for_master()
                    else:
                        group_id = roxywi_common.get_user_group(id=1)
                        servers = metric_sql.select_servers_metrics(group_id)
            else:
                servers = ''
    except Exception as e:
        return f'error: on Metrics page: {e}', 500

    kwargs = {
        'autorefresh': 1,
        'servers': servers,
        'service': service,
        'services': services,
        'service_desc': service_sql.select_service(service),
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
        table_stat = metric_sql.select_service_table_metrics(service, group_id)
    else:
        table_stat = metric_sql.select_table_metrics(group_id)

    return render_template('ajax/table_metrics.html', table_stat=table_stat, service=service, lang=lang)


@bp.post('/<service>/<server_ip>')
def show_metric(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    hostname = server_sql.get_hostname_by_server_ip(server_ip)
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
    hostname = server_sql.get_hostname_by_server_ip(server_ip)
    time_range = common.checkAjaxInput(request.form.get('time_range'))

    if service == 'haproxy':
        return jsonify(metric.haproxy_http_metrics(server_ip, hostname, time_range))

    return 'error: Wrong service'


@bp.route('/<service>/<server_ip>/<is_http>/chart-stream')
@check_services
def chart_data(service, server_ip, is_http):
    def get_chart_data():
        while True:
            json_metric = {}
            if service in ('nginx', 'apache', 'waf'):
                chart_metrics = metric_sql.select_metrics(server_ip, service, time_range=1)
                for i in chart_metrics:
                    json_metric['time'] = common.get_time_zoned_date(i[2], '%H:%M:%S')
                    json_metric['value'] = str(i[1])
            elif service == 'haproxy' and not is_http:
                chart_metrics = metric_sql.select_metrics(server_ip, 'haproxy', time_range=1)
                for i in chart_metrics:
                    json_metric['time'] = common.get_time_zoned_date(i[5], '%H:%M:%S')
                    json_metric['value'] = str(i[1])
                    json_metric['value1'] = str(i[2])
                    json_metric['value2'] = str(i[3])
            else:
                chart_metrics = metric_sql.select_metrics(server_ip, 'http_metrics', time_range=1)
                for i in chart_metrics:
                    json_metric['time'] = common.get_time_zoned_date(i[5], '%H:%M:%S')
                    json_metric['value'] = str(i[1])
                    json_metric['value1'] = str(i[2])
                    json_metric['value2'] = str(i[3])
                    json_metric['value3'] = str(i[4])
            yield f"data:{json.dumps(json_metric)}\n\n"
            time.sleep(60)

    response = Response(stream_with_context(get_chart_data()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response
