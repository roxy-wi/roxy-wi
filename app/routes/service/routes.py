from contextlib import nullcontext
from typing import Union

import distro
from flask import render_template, request, g, jsonify
from flask_jwt_extended import jwt_required
from flask_pydantic import validate
from peewee import SqliteDatabase
from pydantic import IPvAnyAddress

from app import app, cache
from app.routes.service import bp
import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.db.service_event as service_event_sql
from app.middleware import check_services, get_user_params, page_for_admin
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.service.common as service_common
import app.modules.roxywi.common as roxywi_common
import app.modules.roxywi.overview as roxy_overview
from app.modules.service.haproxy_runtime import execute_runtime_command
from app.views.service.views import ServiceActionView, ServiceBackendView, ServiceView
from app.views.service.lets_encrypt_views import LetsEncryptView, LetsEncryptsView
from app.views.service.le_profile_views import LetsEncryptDnsProfilesView, LetsEncryptDnsProfileView
from app.views.service import certificate_source_views as certificate_sources
from app.views.service.certificate_views import (
    CertificatesView, CertificatePreviewView, CertificateOperationView,
    CertificateCreateView, CertificateFileView, CertificateHistoryView, CertificateUploadView,
)
from app.modules.roxywi.class_models import DomainName
from app.modules.roxywi.exception import RoxywiPermissionError
from app.modules.subscription.access import MANAGED_SERVICES, require_feature
from app.modules.roxywi.error_handler import safe_error_message

bp.add_url_rule('/<service>/<server_id>/<any(start, stop, reload, restart):action>', view_func=ServiceActionView.as_view('service_action_ip'), methods=['POST'])
bp.add_url_rule('/<service>/<int:server_id>/<any(start, stop, reload, restart):action>', view_func=ServiceActionView.as_view('service_action'), methods=['POST'])
bp.add_url_rule('/<service>/<server_id>/backend', view_func=ServiceBackendView.as_view('service_backend_ip'), methods=['GET'])
bp.add_url_rule('/<service>/<int:server_id>/backend', view_func=ServiceBackendView.as_view('service_backend'), methods=['GET'])
bp.add_url_rule('/<service>/<server_id>/status', view_func=ServiceView.as_view('service_ip'), methods=['GET'])
bp.add_url_rule('/<service>/<int:server_id>/status', view_func=ServiceView.as_view('service'), methods=['GET'])
bp.add_url_rule('/letsencrypt', view_func=LetsEncryptView.as_view('le_web'), methods=['POST'])
bp.add_url_rule('/letsencrypt/<int:le_id>', view_func=LetsEncryptView.as_view('le_web_id'), methods=['GET', 'PUT', 'PATCH', 'DELETE'])
bp.add_url_rule('/letsencrypts', view_func=LetsEncryptsView.as_view('le_webs'), methods=['GET'])
bp.add_url_rule('/letsencrypt/dns-profiles', view_func=LetsEncryptDnsProfilesView.as_view('le_profiles'), methods=['GET', 'POST'])
bp.add_url_rule('/letsencrypt/dns-profiles/<int:profile_id>', view_func=LetsEncryptDnsProfileView.as_view('le_profile'), methods=['PUT', 'DELETE'])
bp.add_url_rule('/certificate-sources', endpoint='certificate_source_page', view_func=certificate_sources.page)
bp.add_url_rule('/certificate-sources/api', endpoint='certificate_source_collection', view_func=certificate_sources.collection, methods=['GET', 'POST'])
bp.add_url_rule('/certificate-sources/choices', endpoint='certificate_source_choices', view_func=certificate_sources.choices)
bp.add_url_rule('/certificate-sources/api/<int:source_id>', endpoint='certificate_source_item', view_func=certificate_sources.item, methods=['GET', 'PUT', 'DELETE'])
bp.add_url_rule('/certificate-sources/api/<int:source_id>/<any(check,sync,recover):action>', endpoint='certificate_source_action', view_func=certificate_sources.action, methods=['POST'])
bp.add_url_rule('/haproxy/certificates/<int:server_id>', view_func=CertificatesView.as_view('certificates'), methods=['GET', 'POST'])
bp.add_url_rule('/<any(nginx, apache):service>/certificates/<int:server_id>', view_func=CertificatesView.as_view('service_certificates'), methods=['GET'])
bp.add_url_rule('/<any(haproxy, nginx, apache):service>/certificates/<int:server_id>/upload', view_func=CertificateUploadView.as_view('certificate_upload'), methods=['POST'])
bp.add_url_rule('/haproxy/certificates/<int:server_id>/preview', view_func=CertificatePreviewView.as_view('certificate_preview'), methods=['POST'])
bp.add_url_rule('/haproxy/certificates/<int:server_id>/new', view_func=CertificateCreateView.as_view('certificate_create'), methods=['POST'])
bp.add_url_rule('/haproxy/certificates/<int:server_id>/history', view_func=CertificateHistoryView.as_view('certificate_history'), methods=['GET'])
bp.add_url_rule('/haproxy/certificates/operations/<int:task_id>', view_func=CertificateOperationView.as_view('certificate_operation'), methods=['GET', 'POST'])
bp.add_url_rule('/<any(haproxy, nginx, apache):service>/certificates/<int:server_id>/file/<file_token>', view_func=CertificateFileView.as_view('certificate_file'), methods=['GET', 'DELETE'])


def _service_status_payload(result):
    """Normalize MethodView return values for the batch status endpoint."""
    status_code = 200
    if isinstance(result, tuple):
        result, status_code = result[0], result[1]
    if hasattr(result, 'get_json'):
        payload = result.get_json(silent=True)
    else:
        payload = result
    if not isinstance(payload, dict):
        payload = {'status': 'failed', 'error': str(payload)}
    if status_code >= 400:
        payload.setdefault('status', 'failed')
    payload['http_status'] = status_code
    return payload


@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.post('/<service>/statuses')
@check_services
@get_user_params()
def service_statuses(service):
    """Return status snapshots for multiple service servers in one browser request.
    ---
    tags:
      - Service
    parameters:
      - in: path
        name: service
        required: true
        type: string
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [server_ids]
          properties:
            server_ids:
              type: array
              maxItems: 100
              items:
                type: integer
    responses:
      200:
        description: A status result for every requested server
      400:
        description: Invalid server_ids payload
    """
    body = request.get_json(silent=True) or {}
    server_ids = body.get('server_ids')
    if not isinstance(server_ids, list) or not server_ids or len(server_ids) > 100:
        return jsonify({'status': 'failed', 'error': 'server_ids must be a non-empty list with at most 100 items'}), 400

    normalized_ids = []
    for server_id in server_ids:
        if isinstance(server_id, bool):
            return jsonify({'status': 'failed', 'error': 'server_ids must contain integer IDs'}), 400
        try:
            server_id = int(server_id)
        except (TypeError, ValueError):
            return jsonify({'status': 'failed', 'error': 'server_ids must contain integer IDs'}), 400
        if server_id not in normalized_ids:
            normalized_ids.append(server_id)

    service_view = ServiceView()
    results = []
    for server_id in normalized_ids:
        try:
            result = service_view.get(service, server_id)
            payload = _service_status_payload(result)
        except Exception as exc:
            roxywi_common.logging(
                'Roxy-WI server',
                f'error: Cannot get {service} status for server ID {server_id}: {exc}',
            )
            payload = {
                'server_id': server_id,
                'service': service,
                'status': 'failed',
                'error': 'Cannot get service status',
                'http_status': 500,
            }
        payload.setdefault('server_id', server_id)
        payload.setdefault('service', service)
        results.append(payload)

    return jsonify({'status': 'success', 'data': results})


@bp.route('/<service>', defaults={'serv': None})
@bp.route('/<service>/<serv>')
@check_services
@get_user_params()
def services(service, serv):
    worker_states = service_event_sql.worker_summary(group_id=int(g.user_params['group_id']))
    tool_availability = {name: worker_states.get(name, {}).get('active', 0) > 0 for name in ('checker', 'metrics')}
    service_desc = service_sql.select_service(service)
    servers = roxywi_common.get_dick_permit(virt=1, service=service_desc.slug)
    servers_with_status1 = []
    waf_server = ''
    cmd = "ps ax |grep -e 'keep_alive.py' |grep -v grep |wc -l"
    keep_alive, stderr = server_mod.subprocess_execute(cmd)

    if len(servers) == 1:
        serv = servers[0][2]

    if serv:
        if roxywi_common.check_is_server_in_group(serv):
            servers = server_sql.select_servers(server=serv)
            waf_server = waf_sql.select_waf_servers(serv)
            server_id = server_sql.get_server_by_ip(serv).server_id
            docker_settings = service_sql.select_docker_service_settings(server_id, service_desc.slug)
            restart_settings = service_sql.select_restart_service_settings(server_id, service_desc.slug)
        else:
            raise Exception('error: wrong group')
    else:
        docker_settings = service_sql.select_docker_services_settings(service_desc.slug)
        restart_settings = service_sql.select_restart_services_settings(service_desc.slug)

    # Auto Start still uses the local keep_alive service. Checker and Metrics
    # are distributed workers; packages on the web host do not describe them.
    if distro.id() == 'ubuntu':
        cmd = 'apt list --installed 2>&1 |grep roxy-wi-keep-alive'
    else:
        cmd = "rpm --query roxy-wi-keep_alive-* |awk -F\"roxy-wi-keep_alive\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
    service_ver, stderr = server_mod.subprocess_execute(cmd)
    tool_availability['keep_alive'] = bool(service_ver and service_ver[0] and 'is not installed' not in service_ver[0])

    for s in servers:
        servers_with_status = list()
        servers_with_status.append(s[0])
        servers_with_status.append(s[1])
        servers_with_status.append(s[2])
        servers_with_status.append(s[11])
        servers_with_status.append(server_sql.select_servers(server=s[2]))
        is_keepalived = s[13]

        if is_keepalived:
            try:
                cmd = ('sudo kill -USR1 `cat /var/run/keepalived.pid` && sudo grep State /tmp/keepalived.data -m 1 |'
                       'awk -F"=" \'{print $2}\'|tr -d \'[:space:]\' && sudo rm -f /tmp/keepalived.data')
                if service_sql.select_service_setting(s[0], 'keepalived', 'dockerized') == '1':
                    from app.modules.service import container_settings
                    out = container_settings.keepalived_state(server_sql.get_server(s[0]))
                else:
                    out = server_mod.ssh_command(s[2], cmd)
                out1 = ('1', out)
                servers_with_status.append(out1)
            except Exception as e:
                servers_with_status.append('error: ' + safe_error_message(e))
        else:
            servers_with_status.append('')

        servers_with_status1.append(servers_with_status)

    from app.modules.service import container_settings
    container_engines = {row.server_id: container_settings.runtime(row.server_id, service_desc.slug)['engine']
                         for row in docker_settings if row.value == '1'}
    kwargs = {
        'clusters': ha_sql.select_ha_cluster_name_and_slaves(),
        'master_slave': server_sql.is_master(0, master_slave=1),
        'user_subscription': roxywi_common.return_user_subscription(),
        'servers': servers_with_status1,
        'lang': g.user_params['lang'],
        'serv': serv,
        'service': service,
        'tool_availability': tool_availability,
        'service_desc': service_desc,
        'restart_settings': restart_settings,
        'docker_settings': docker_settings,
        'container_engines': container_engines,
        'waf_server': waf_server,
        'keep_alive': ''.join(keep_alive)
    }

    return render_template('service.html', **kwargs)


@bp.route('/<service>/<server_ip>/last-edit')
@check_services
@validate()
def last_edit(service: str, server_ip: Union[IPvAnyAddress, DomainName]):
    return service_common.get_overview_last_edit(str(server_ip), service)


@bp.route('/<service>/ssl')
@check_services
@get_user_params()
def ssl_service(service):
    return render_template('ssl.html', lang=g.user_params['lang'], service=service)


@bp.route('/cpu-ram-metrics/<server_ip>/<server_id>/<name>/<service>')
@get_user_params()
@validate()
def cpu_ram_metrics(server_ip: Union[IPvAnyAddress, DomainName], server_id: int, name: str, service: str):
    if service == 'haproxy':
        try:
            output = execute_runtime_command(
                str(server_ip),
                int(sql.get_setting('haproxy_sock_port')),
                'show info',
                timeout=1,
            )
            allowed_fields = ('node', 'Nbproc', 'Maxco', 'MB', 'Nbthread')
            return_out = '\n'.join(
                line for line in output.splitlines()
                if any(field in line for field in allowed_fields)
            )
        except Exception:
            return_out = "Cannot connect to HAProxy"
    else:
        return_out = ''

    servers = [[name, str(server_ip), return_out]]
    kwargs = {
        'service_status': sorted(servers, key=common.get_key),
        'id': server_id,
        'service_page': service,
        'lang': g.user_params['lang']
    }

    return render_template('ajax/overviewServers.html', **kwargs)


@bp.get('/haproxy/bytes/<server_ip>')
@validate()
def show_haproxy_bytes(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return roxy_overview.show_haproxy_binout(server_ip)
    except Exception as e:
        return f'error: {safe_error_message(e)}'


@bp.get('/nginx/connections/<server_ip>')
@validate()
def show_nginx_connections(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return roxy_overview.show_nginx_connections(server_ip)
    except Exception as e:
        return f'error: {safe_error_message(e)}'


@bp.get('/apache/bytes/<server_ip>')
@validate()
def show_apache_bytes(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return roxy_overview.show_apache_bytes(server_ip)
    except Exception as e:
        return f'error: {safe_error_message(e)}'


@bp.get('/keepalived/become-master/<server_ip>')
@validate()
@cache.cached()
def show_keepalived_become_master(server_ip: Union[IPvAnyAddress, DomainName]):
    return roxy_overview.keepalived_became_master(str(server_ip))


@bp.route('/position/<int:server_id>/<int:pos>')
def change_pos(server_id, pos):
    return server_sql.update_server_pos(pos, server_id)


@bp.route('/settings/<service>/<int:server_id>')
@check_services
@get_user_params()
@page_for_admin(level=3)
def show_service_settings(service, server_id):
    server = server_sql.get_server(server_id)
    roxywi_common.require_active_group_access(server.group_id)
    settings = {row.setting: str(row.value) for row in service_sql.select_service_settings(server_id, service)}
    from app.modules.service import container_settings
    settings.update({'container_' + key: value for key, value in container_settings.runtime(server_id, service).items()})
    settings['container_name'] = container_settings.name(server_id, service) if settings.get('dockerized') == '1' else settings.get('container_name', '')
    return render_template('ajax/service_settings.html', settings=settings, service=service,
                           server_id=server_id, lang=g.user_params['lang'])


@bp.get('/settings/<any(haproxy,nginx,apache,keepalived):service>/<int:server_id>/containers')
@check_services
@get_user_params()
@page_for_admin(level=2)
def show_container_candidates(service, server_id):
    from app.modules.service import container_settings
    from app.modules.connectors import containers
    server = server_sql.get_server(server_id)
    roxywi_common.require_active_group_access(server.group_id)
    try:
        runtime = containers.validate({key: request.args.get(key, default) for key, default in
                                       (('engine', 'docker'), ('owner', 'root'))})
        return jsonify(container_settings.discover(server, runtime))
    except Exception:
        return jsonify(error='Cannot inspect this engine and owner; check installation, user runtime and permissions'), 400


@bp.get('/settings/<any(haproxy):service>/<int:server_id>/sources')
@check_services
@get_user_params()
@page_for_admin(level=3)
def show_haproxy_sources(service, server_id):
    from app.modules.config.haproxy_files import discover_sources
    server = server_sql.get_server(server_id)
    roxywi_common.require_active_group_access(server.group_id)
    dockerized = request.args.get('dockerized')
    if dockerized not in (None, '0', '1'):
        return jsonify({'status': 'failed', 'error': 'Invalid Docker setting'}), 400
    from app.modules.connectors import containers
    try:
        runtime = containers.validate({key: request.args['container_' + key] for key in ('engine', 'owner', 'unit') if 'container_' + key in request.args})
        if int(g.user_params['role']) > 2:
            from app.modules.service import container_settings
            stored = container_settings.runtime(server_id, service)
            if (any(request.args['container_' + key] != stored[key] for key in ('engine', 'owner', 'unit') if 'container_' + key in request.args)
                    or (request.args.get('container_name') and request.args['container_name'] != container_settings.name(server_id, service))):
                return jsonify(error='A server administrator must inspect other container identities'), 403
        discovery = discover_sources(server.ip, server_id, dockerized=None if dockerized is None else dockerized == '1',
                                     **({'runtime':runtime} if any(key.startswith('container_') for key in request.args) else {}),
                                     **({'container_name':request.args['container_name']} if request.args.get('container_name') else {}))
    except ValueError:
        return jsonify({'status':'failed', 'error':'Invalid container identity'}), 400
    return render_template('include/haproxy_sources.html', discovery=discovery,
                           server_id=server_id, lang_code=g.user_params['lang'])


@bp.post('/settings/<service>')
@check_services
@get_user_params()
@page_for_admin(level=3)
def save_service_settings(service):
    from app.modules.db.db_model import ServiceSetting
    try:
        server_id = int(request.form.get('serverSettingsSave'))
        server = server_sql.get_server(server_id)
    except (ValueError, TypeError):
        return jsonify({'status': 'failed', 'error': 'Invalid server'}), 400
    roxywi_common.require_active_group_access(server.group_id)
    values = {'dockerized': request.form.get('serverSettingsDockerized'),
              'restart': request.form.get('serverSettingsRestart')}
    if service == 'haproxy' and 'serverSettingsMultipleConfigs' in request.form:
        values['multiple_config_files'] = request.form['serverSettingsMultipleConfigs']
    if any(value not in ('0', '1') for value in values.values()):
        return jsonify({'status': 'failed', 'error': 'Invalid service setting'}), 400
    from app.modules.connectors import containers
    try:
        runtime = containers.validate({key:request.form['container_' + key] for key in ('engine','owner','unit') if 'container_' + key in request.form})
        if service == 'keepalived' and runtime['owner'] != 'root':
            raise ValueError('Keepalived requires host network privileges')
        if any('container_' + key in request.form for key in ('engine','owner','unit')):
            values.update({'container_' + key:value for key,value in runtime.items()})
        if 'container_name' in request.form:
            values['container_name'] = containers.name(request.form['container_name']) if request.form['container_name'] else ''
    except ValueError:
        return jsonify({'status':'failed', 'error':'Invalid container identity; rootless Keepalived is unsupported'}), 400
    if int(g.user_params['role']) > 2:
        previous = {row.setting:str(row.value) for row in service_sql.select_service_settings(server_id, service)}
        from app.modules.service import container_settings
        previous.update({'container_' + key:value for key,value in container_settings.runtime(server_id, service).items()})
        previous['container_name'] = container_settings.name(server_id, service) if previous.get('dockerized') == '1' else previous.get('container_name','')
        if any(value != previous.get(key,'') for key,value in values.items() if key.startswith('container_')):
            return jsonify({'status':'failed','error':'A server administrator must change container identities'}), 403
    try:
        database = ServiceSetting._meta.database
        # Wait for the SQLite writer before starting the settings transaction.
        # Deferred transactions can fail immediately when a worker writes too.
        transaction_args = ('IMMEDIATE',) if isinstance(database, SqliteDatabase) else ()
        from app.modules.service.ha_mutation import mutation
        reservation = mutation(server_ids=[server_id]) if service == 'keepalived' else nullcontext()
        with reservation, database.atomic(*transaction_args):
            for setting, value in values.items():
                if not service_sql.insert_or_update_service_setting(server_id, service, setting, value):
                    raise RuntimeError('Cannot save service settings')
    except Exception as exc:
        return roxywi_common.handler_exceptions_for_json_data(exc, 'Cannot save service settings')
    server_ip = server.ip
    service_dockerized, service_restart = values['dockerized'], values['restart']
    service_docker = f'Service {service.title()} has been flagged as a dockerized'
    service_systemd = f'Service {service.title()} has been flagged as a system service'
    disable_restart = f'Restart option is disabled for {service.title()} service'
    enable_restart = f'Restart option is enabled for {service.title()} service'

    roxywi_common.logging(server_ip, service_docker if service_dockerized == '1' else service_systemd,
                          keep_history=1, service=service)
    roxywi_common.logging(server_ip, disable_restart if service_restart == '1' else enable_restart,
                          keep_history=1, service=service)
    if 'multiple_config_files' in values:
        roxywi_common.logging(server_ip, 'HAProxy multiple configuration files: ' + values['multiple_config_files'],
                              keep_history=1, service=service)

    return 'ok'


@bp.post('/<service>/tools/update')
@check_services
def update_tools_enable(service):
    server_id = int(request.form.get('server_id'))
    active = request.form.get('active')
    name = request.form.get('name')
    alert = request.form.get('alert_en')
    metrics = request.form.get('metrics')
    if any(str(value).strip().lower() in {'1', 'true', 'yes', 'on'} for value in (active, alert, metrics)):
        try:
            require_feature(MANAGED_SERVICES)
        except RoxywiPermissionError as exc:
            return jsonify({'status': 'failed', 'error': exc.public_message}), 403
    service_sql.update_hapwi_server(server_id, alert, metrics, active, service)
    from app.modules.db import service_command as service_command_sql
    service_command_sql.queue_checker_assignment(
        server_id, service, str(alert).strip().lower() in {'1', 'true', 'yes', 'on'}
    )
    if service in {'haproxy', 'nginx', 'apache'}:
        service_command_sql.queue_metrics_assignment(
            server_id, service, str(metrics).strip().lower() in {'1', 'true', 'yes', 'on'}
        )
    server_ip = server_sql.get_server(server_id).ip
    roxywi_common.logging(server_ip, f'The server {name} has been updated ', keep_history=1, service=service)

    return 'ok'
