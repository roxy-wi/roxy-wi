from typing import Union, Literal

from flask import render_template, request, g, jsonify, abort
from flask_jwt_extended import jwt_required
from flask_pydantic import validate
from pydantic import IPvAnyAddress, ValidationError

from app.routes.install import bp
from app.middleware import get_user_params
import app.modules.db.sql as sql
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.server.server as server_mod
import app.modules.service.common as service_common
import app.modules.service.installation as service_mod
import app.modules.service.exporter_installation as exp_installation
from app.views.install.views import InstallView
from app.modules.roxywi.class_models import DomainName
from app.modules.db.db_model import InstallationTasks, PacemakerCluster
from app.modules.roxywi.error_handler import safe_error_message


bp.add_url_rule(
    '/<any(haproxy, nginx, apache, keepalived):service>',
    view_func=InstallView.as_view('install'),
    methods=['POST'],
    defaults={'server_id': None}
)
bp.add_url_rule(
    '/<any(haproxy, nginx, apache, keepalived):service>/<server_id>',
    view_func=InstallView.as_view('install_ip'),
    methods=['POST'],
)
bp.add_url_rule(
    '/<any(haproxy, nginx, apache, keepalived):service>/<int:server_id>',
    view_func=InstallView.as_view('install_id'),
    methods=['POST'],
)


@bp.before_request
@jwt_required()
@get_user_params()
def before_request():
    """ Protect all the admin endpoints. """
    roxywi_auth.page_for_admin(level=3)
    roxywi_common.require_request_server_access()


@bp.route('')
@get_user_params()
def install_monitoring():
    roxywi_auth.page_for_admin(level=2)
    kwargs = {
        'is_needed_tool': common.is_tool('ansible'),
        'geoip_country_codes': sql.select_geoip_country_codes(),
        'lang': g.user_params['lang']
    }
    from app.modules.pacemaker import exporter as ha_exporter
    import json
    member_ids={member['server_id'] for cluster in PacemakerCluster.select().where(PacemakerCluster.group_id==g.user_params['group_id']) for member in json.loads(cluster.servers)}
    kwargs['ha_cluster_exporter_servers']=[server for server in g.user_params.get('servers',[]) if server[0] in member_ids]
    kwargs['ha_cluster_exporter_versions']={ha_exporter.VERSION:ha_exporter.VERSION}
    return render_template('install.html', **kwargs)


@bp.get('/pacemaker')
def pacemaker_setup():
    if not roxywi_auth.is_access_permit_to_service('cluster'):
        abort(403)
    mode = request.args.get('setup', 'new')
    if mode not in ('new', 'adopt', 'witness'):
        abort(400)
    return render_template('pacemaker.html', lang=g.user_params['lang'], view='setup', setup_mode=mode)


@bp.post('/exporter/<exporter>')
def install_exporter(exporter):
    json_data = request.get_json()
    server_ip = common.is_ip_or_dns(json_data['server_ip'])
    ver = common.checkAjaxInput(json_data['exporter_v'])
    roxywi_common.check_is_server_in_group(server_ip)

    if exporter not in ('haproxy', 'nginx', 'apache', 'keepalived', 'node', 'ha_cluster'):
        return jsonify({'status': 'failed', 'error': 'Wrong exporter'})

    try:
        if exporter=='ha_cluster':
            from app.modules.pacemaker import exporter as ha_exporter
            if int(g.user_params['role'])>3 or not roxywi_auth.is_access_permit_to_service('cluster'): abort(403)
            ha_exporter.member_server(server_ip,g.user_params['group_id'])
            options={'listen_address':json_data.get('listen_address',server_ip),'port':json_data.get('port',9664)}
            ha_exporter.inventory(server_ip,ver,options)
            task_id=exp_installation.install_exporter(server_ip,ver,exporter,options)
        else:
            task_id = exp_installation.install_exporter(server_ip, ver, exporter)
        return jsonify({"status": "accepted", "tasks_ids": [task_id]}), 202
    except ValidationError:
        return jsonify(status='failed',error='Check exporter version, listen IP and port'),400
    except Exception as e:
        from werkzeug.exceptions import HTTPException
        if isinstance(e,HTTPException):raise
        return jsonify({'status': 'failed', 'error': f'Cannot install {exporter.title()} exporter: {safe_error_message(e)}'})


@bp.route('/exporter/<exporter>/version/<server_ip>')
@validate()
def get_exporter_version(exporter: str, server_ip: Union[IPvAnyAddress, DomainName]):
    if exporter=='ha_cluster':
        from app.modules.pacemaker.exporter import member_server
        if int(g.user_params['role'])>3 or not roxywi_auth.is_access_permit_to_service('cluster'):abort(403)
        member_server(str(server_ip),g.user_params['group_id'])
    return service_common.get_exp_version(str(server_ip), exporter)


@bp.get('/exporter/ha_cluster/status/<server_ip>')
@validate()
def ha_cluster_exporter_status(server_ip: Union[IPvAnyAddress, DomainName]):
    if int(g.user_params['role'])>3 or not roxywi_auth.is_access_permit_to_service('cluster'):abort(403)
    from app.modules.pacemaker.exporter import status
    try:
        return jsonify(data=status(str(server_ip),g.user_params['group_id']))
    except Exception as exc:
        return jsonify(error=safe_error_message(exc)),400


@bp.post('/waf/<service>/<server_ip>')
@validate()
def install_waf(service: str, server_ip: Union[IPvAnyAddress, DomainName]):
    server_ip = str(server_ip)
    roxywi_common.check_is_server_in_group(server_ip)
    if service not in ('haproxy', 'nginx'):
        return jsonify({'status': 'failed', 'error': 'Wrong service'})
    try:
        inv, server_ips = service_mod.generate_waf_inv(server_ip, service)
    except Exception as e:
        return jsonify({'status': 'failed', 'error': f'Cannot create inventory: {safe_error_message(e)}'})
    try:
        task_id = service_mod.run_ansible_thread(
            inv,
            server_ips,
            f'waf_{service}',
            f'{service.title()} WAF',
            success_action={
                'type': 'waf-installed',
                'server_ip': server_ip,
                'service': service,
            },
        )
    except Exception as e:
        return jsonify({'status': 'failed', 'error': f'Cannot install WAF: {safe_error_message(e)}'})

    return jsonify({'status': 'accepted', 'tasks_ids': [task_id]}), 202


@bp.post('/geoip')
def install_geoip():
    json_data = request.get_json()
    server_ip = common.is_ip_or_dns(json_data['server_ip'])
    roxywi_common.check_is_server_in_group(server_ip)
    geoip_update = common.checkAjaxInput(json_data['update'])
    service = common.checkAjaxInput(json_data['service'])

    try:
        inv, server_ips = service_mod.generate_geoip_inv(server_ip, service, geoip_update)
        task_id = service_mod.run_ansible_thread(
            inv, server_ips, f'{service}_geoip', f'{service.title()} GeoIP'
        )
        return jsonify({'status': 'accepted', 'tasks_ids': [task_id]}), 202
    except Exception as e:
        return jsonify({'status': 'failed', 'error': f'Cannot install GeoIP: {safe_error_message(e)}'})


@bp.route('/geoip/<service>/<server_ip>')
@validate()
def check_geoip(service: Literal['haproxy', 'nginx'], server_ip: Union[IPvAnyAddress, DomainName]):
    service_dir = common.return_nice_path(sql.get_setting(f'{service}_dir'))
    cmd = f"ls {service_dir}geoip/"
    return server_mod.ssh_command(str(server_ip), cmd)


@bp.route('/task-status/<int:task_id>')
@get_user_params()
def get_task_status(task_id):
    task = InstallationTasks.get((InstallationTasks.id == task_id) & (InstallationTasks.group_id == g.user_params['group_id']))
    return jsonify({'task_id': task_id, 'status': task.status, 'service_name': task.service_name, 'error': task.error}), 200
