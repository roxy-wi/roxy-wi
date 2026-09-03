import re

from flask import render_template, request, g, jsonify
from flask_jwt_extended import jwt_required

from app.routes.portscanner import bp
from app.middleware import get_user_params
import app.modules.db.server as server_sql
import app.modules.db.portscanner as ps_sql
import app.modules.db.service_command as service_command_sql
import app.modules.db.service_event as service_event_sql
from app.modules.server.command import run_local
import app.modules.roxywi.common as roxywi_common
import app.modules.tools.common as tools_common
import app.modules.common.common as common
from app.modules.subscription.access import MANAGED_SERVICES, feature_required


_NMAP_HOST_TIMEOUT_SECONDS = 40
_NMAP_PROCESS_TIMEOUT_SECONDS = 45


@bp.before_request
@jwt_required()
@feature_required(MANAGED_SERVICES)
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('')
@get_user_params(virt=1)
def portscanner():
    group_id = int(g.user_params['group_id'])
    port_scanner_settings = ps_sql.select_port_scanner_settings(group_id)
    worker_state = service_event_sql.worker_summary(group_id=group_id).get('portscanner', {})

    if not port_scanner_settings:
        port_scanner_settings = ''
        count_ports = ''
    else:
        count_ports = list()
        for s in g.user_params['servers']:
            count_ports_from_sql = ps_sql.select_count_opened_ports(s[2])
            i = (s[2], count_ports_from_sql)
            count_ports.append(i)

    kwargs = {
        'servers': g.user_params['servers'],
        'port_scanner_settings': port_scanner_settings,
        'count_ports': count_ports,
        'port_scanner': tools_common._distributed_status(worker_state) or 'stopped',
        'worker_state': worker_state,
        'lang': g.user_params['lang'],
        'user_subscription': roxywi_common.return_user_subscription()
    }

    return render_template('portscanner.html', **kwargs)


@bp.route('/history/<server_ip>')
@get_user_params()
def portscanner_history(server_ip):
    kwargs = {
        'h2': 1,
        'lang': g.user_params['lang'],
        'history': ps_sql.select_port_scanner_history(server_ip),
        'user_subscription': roxywi_common.return_user_subscription()
    }

    return render_template('include/port_scan_history.html', **kwargs)


@bp.post('/settings')
def change_settings_portscanner():
    server_id = int(request.form.get('server_id'))
    enabled = int(request.form.get('enabled'))
    notify = int(request.form.get('notify'))
    history = int(request.form.get('history'))
    server = server_sql.get_server(server_id)

    try:
        ps_sql.insert_port_scanner_settings(server_id, server.group_id, enabled, notify, history)
        service_command_sql.queue_portscanner_assignment(server_id, bool(enabled))
        return 'ok'
    except Exception as e:
        return f'error: Cannot save settings: {e}'


@bp.post('/scan')
def scan_port():
    json_data = request.get_json(silent=True)
    if not isinstance(json_data, dict):
        return jsonify({'error': 'JSON request body is required'}), 400

    if 'id' in json_data:
        ip = server_sql.get_server(int(json_data['id'])).ip
    else:
        ip = common.is_ip_or_dns(json_data.get('ip', ''))
        if not ip:
            return jsonify({'error': 'Invalid IP address or DNS name'}), 400

    result = run_local(
        [
            'sudo', '-n', 'nmap', '-n', '-sS', '-T4', '--max-retries', '1',
            '--host-timeout', f'{_NMAP_HOST_TIMEOUT_SECONDS}s', ip,
        ],
        timeout=_NMAP_PROCESS_TIMEOUT_SECONDS,
    )
    scan_output = f'{result.stdout}\n{result.stderr}'.lower()
    if result.timed_out or 'host timeout' in scan_output:
        return jsonify({
            'error': f'Port scan exceeded {_NMAP_PROCESS_TIMEOUT_SECONDS} seconds',
        }), 408
    if not result.succeeded:
        return jsonify({'error': result.stderr or 'Cannot scan ports'}), 502

    output_lines = result.stdout_lines
    ports = [
        re.sub(r'\s+', ' ', line.strip())
        for line in output_lines
        if line and line[0].isdigit()
    ]
    info = output_lines[3:5]

    lang = roxywi_common.get_user_lang_for_flask()
    temp = render_template('ajax/scan_ports.html', ports=ports, info=info, lang=lang)
    return jsonify({'status': 'Ok', 'data': temp})
