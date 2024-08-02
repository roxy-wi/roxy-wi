from flask import render_template, request, jsonify, g
from flask_jwt_extended import jwt_required

from app.routes.smon import bp
from app.middleware import get_user_params
import app.modules.db.smon as smon_sql
import app.modules.common.common as common
import app.modules.tools.smon_agent as smon_agent
import app.modules.tools.common as tools_common
import app.modules.roxywi.common as roxywi_common
import app.modules.server.server as server_mod


@bp.route('/agent', methods=['GET', 'POST', 'PUT', 'DELETE'])
@jwt_required()
@get_user_params()
def agent():
    if request.method == 'GET':
        group_id = g.user_params['group_id']
        kwargs = {
            'agents': smon_sql.get_agents(group_id),
            'lang': roxywi_common.get_user_lang_for_flask(),
            'smon_status': tools_common.is_tool_active('roxy-wi-smon'),
            'user_subscription': roxywi_common.return_user_subscription(),
        }

        return render_template('smon/agent.html', **kwargs)
    elif request.method == 'POST':
        data = request.get_json()
        try:
            last_id = smon_agent.add_agent(data)
            return str(last_id)
        except Exception as e:
            return f'{e}'
    elif request.method == "PUT":
        json_data = request.get_json()
        try:
            smon_agent.update_agent(json_data)
        except Exception as e:
            return f'{e}'
        return 'ok', 201
    elif request.method == 'DELETE':
        agent_id = int(request.form.get('agent_id'))
        try:
            smon_agent.delete_agent(agent_id)
            smon_sql.delete_agent(agent_id)
        except Exception as e:
            return f'{e}'
        return 'ok'


@bp.post('/agent/hello')
def agent_get_checks():
    json_data = request.json
    agent_id = smon_sql.get_agent_id_by_uuid(json_data['uuid'])
    try:
        smon_agent.send_checks(agent_id)
    except Exception as e:
        return f'{e}'
    return 'ok'


@bp.get('/agent/free')
@jwt_required()
@get_user_params()
def get_free_agents():
    group_id = g.user_params['group_id']
    free_servers = smon_sql.get_free_servers_for_agent(group_id)
    servers = {}
    for s in free_servers:
        servers.setdefault(s.server_id, s.hostname)

    return jsonify(servers)


@bp.get('/agent/count')
@jwt_required()
def get_agent_count():
    try:
        smon_agent.check_agent_limit()
    except Exception as e:
        return f'{e}'

    return 'ok'


@bp.get('/agent/<int:agent_id>')
@jwt_required()
@get_user_params()
def get_agent(agent_id):
    try:
        agent_data = smon_sql.get_agent(agent_id)
    except Exception as e:
        return f'{e}'

    return render_template('ajax/smon/agent.html', agents=agent_data, lang=roxywi_common.get_user_lang_for_flask())


@bp.get('/agent/settings/<int:agent_id>')
@jwt_required()
def get_agent_settings(agent_id):
    settings = {}
    try:
        agent_data = smon_sql.get_agent(agent_id)
    except Exception as e:
        return f'{e}'

    for a in agent_data:
        settings.setdefault('name', a.name)
        settings.setdefault('server_id', str(a.server_id))
        settings.setdefault('hostname', a.hostname)
        settings.setdefault('desc', a.desc)
        settings.setdefault('enabled', str(a.enabled))

    return jsonify(settings)


@bp.get('/agent/version/<server_ip>')
@jwt_required()
def get_agent_version(server_ip):
    agent_id = int(request.args.get('agent_id'))

    try:
        req = smon_agent.send_get_request_to_agent(agent_id, server_ip, 'version')
        return req
    except Exception as e:
        return f'{e}'


@bp.get('/agent/uptime/<server_ip>')
@jwt_required()
def get_agent_uptime(server_ip):
    agent_id = int(request.args.get('agent_id'))

    try:
        req = smon_agent.send_get_request_to_agent(agent_id, server_ip, 'uptime')
        return req
    except Exception as e:
        return f'{e}'


@bp.get('/agent/status/<server_ip>')
@jwt_required()
def get_agent_status(server_ip):
    agent_id = int(request.args.get('agent_id'))

    try:
        req = smon_agent.send_get_request_to_agent(agent_id, server_ip, 'scheduler')
        return req
    except Exception as e:
        return f'{e}'


@bp.get('/agent/checks/<server_ip>')
@jwt_required()
def get_agent_checks(server_ip):
    agent_id = int(request.args.get('agent_id'))

    try:
        req = smon_agent.send_get_request_to_agent(agent_id, server_ip, 'checks')
        return req
    except Exception as e:
        return f'{e}'


@bp.post('/agent/action/<action>')
@jwt_required()
def agent_action(action):
    server_ip = common.is_ip_or_dns(request.form.get('server_ip'))

    if action not in ('start', 'stop', 'restart'):
        return 'error: Wrong action'

    try:
        command = [f'sudo systemctl {action} roxy-wi-smon-agent']
        server_mod.ssh_command(server_ip, command)
    except Exception as e:
        return f'{e}'
    return 'ok'
