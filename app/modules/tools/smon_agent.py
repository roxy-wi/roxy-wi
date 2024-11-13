import uuid

import requests
import app.modules.db.sql as sql
import app.modules.db.smon as smon_sql
import app.modules.db.server as server_sql
import app.modules.common.common as common
import app.modules.roxywi.common as roxywi_common
from app.modules.service.installation import run_ansible


def generate_agent_inc(server_ip: str, action: str, agent_uuid: uuid) -> object:
    agent_port = sql.get_setting('agent_port')
    master_port = sql.get_setting('master_port')
    master_ip = sql.get_setting('master_ip')
    if not master_ip: raise Exception('error: Master IP cannot be empty')
    if master_port == '': raise Exception('error: Master port cannot be empty')
    if agent_port == '': raise Exception('error: Agent port cannot be empty')
    inv = {"server": {"hosts": {}}}
    server_ips = [server_ip]
    inv['server']['hosts'][server_ip] = {
        'action': action,
        'agent_port': agent_port,
        'agent_uuid': agent_uuid,
        'master_ip': master_ip,
        'master_port': master_port
    }

    return inv, server_ips


def check_agent_limit():
    user_subscription = roxywi_common.return_user_subscription()
    count_agents = smon_sql.count_agents()
    if user_subscription['user_plan'] == 'user' and count_agents >= 1:
        raise Exception('error: You have reached limit for Home plan')
    elif user_subscription['user_plan'] == 'company' and count_agents >= 5:
        raise Exception('error: You have reached limit for Enterprise plan')


def add_agent(data) -> int:
    name = common.checkAjaxInput(data.get("name"))
    server_id = int(data.get("server_id"))
    server_ip = server_sql.get_server(server_id).ip
    desc = common.checkAjaxInput(data.get("desc"))
    enabled = int(data.get("enabled"))
    agent_uuid = str(uuid.uuid4())
    check_agent_limit()

    try:
        inv, server_ips = generate_agent_inc(server_ip, 'install', agent_uuid)
        run_ansible(inv, server_ips, 'smon_agent')
    except Exception as e:
        roxywi_common.handle_exceptions(e, server_ip, 'Cannot install SMON agent', roxywi=1, login=1)

    try:
        last_id = smon_sql.add_agent(name, server_id, desc, enabled, agent_uuid)
        roxywi_common.logging(server_ip, 'A new SMON agent has been created', roxywi=1, login=1, keep_history=1, service='SMON')
        return last_id
    except Exception as e:
        roxywi_common.handle_exceptions(e, 'Roxy-WI server', 'Cannot create Agent', roxywi=1, login=1)


def delete_agent(agent_id: int):
    server_ip = smon_sql.get_agent_ip_by_id(agent_id)
    agent_uuid = ''
    try:
        inv, server_ips = generate_agent_inc(server_ip, 'uninstall', agent_uuid)
        run_ansible(inv, server_ips, 'smon_agent')
    except Exception as e:
        roxywi_common.handle_exceptions(e, server_ip, 'Cannot uninstall SMON agent', roxywi=1, login=1)


def update_agent(json_data):
    agent_id = int(json_data.get("agent_id"))
    name = common.checkAjaxInput(json_data.get("name"))
    desc = common.checkAjaxInput(json_data.get("desc"))
    enabled = int(json_data.get("enabled"))
    reconfigure = int(json_data.get("reconfigure"))

    try:
        smon_sql.update_agent(agent_id, name, desc, enabled)
    except Exception as e:
        roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot update SMON agent: {agent_id}', roxywi=1, login=1)

    if reconfigure:
        agent_uuid = smon_sql.get_agent_uuid(agent_id)
        server_ip = smon_sql.select_server_ip_by_agent_id(agent_id)
        try:
            inv, server_ips = generate_agent_inc(server_ip, 'install', agent_uuid)
            run_ansible(inv, server_ips, 'smon_agent')
        except Exception as e:
            roxywi_common.handle_exceptions(e, server_ip, 'Cannot reconfigure SMON agent', roxywi=1, login=1)


def get_agent_headers(agent_id: int) -> dict:
    try:
        agent_uuid = smon_sql.get_agent_uuid(agent_id)
    except Exception as e:
        if str(e).find("agent not found") != -1:
            agent_uuid = None
        else:
            raise Exception(e)
    return {'Agent-UUID': str(agent_uuid)}


def send_get_request_to_agent(agent_id: int, server_ip: str, api_path: str) -> bytes:
    headers = get_agent_headers(agent_id)
    agent_port = sql.get_setting('agent_port')
    try:
        req = requests.get(f'http://{server_ip}:{agent_port}/{api_path}', headers=headers, timeout=5)
        return req.content
    except Exception as e:
        raise Exception(f'error: Cannot get agent status: {e}')


def send_post_request_to_agent(agent_id: int, server_ip: str, api_path: str, json_data: object) -> bytes:
    headers = get_agent_headers(agent_id)
    agent_port = sql.get_setting('agent_port')
    try:
        req = requests.post(f'http://{server_ip}:{agent_port}/{api_path}', headers=headers, json=json_data, timeout=5)
        return req.content
    except Exception as e:
        raise Exception(f'error: Cannot get agent status: {e}')


def delete_check(agent_id: int, server_ip: str, check_id: int) -> bytes:
    headers = get_agent_headers(agent_id)
    agent_port = sql.get_setting('agent_port')
    try:
        req = requests.delete(f'http://{server_ip}:{agent_port}/check/{check_id}', headers=headers, timeout=5)
        return req.content
    except requests.exceptions.HTTPError as e:
        roxywi_common.logging(server_ip, f'error: Cannot delete check from agent: http error {e}', roxywi=1, login=1)
    except requests.exceptions.ConnectTimeout:
        roxywi_common.logging(server_ip, 'error: Cannot delete check from agent: connection timeout', roxywi=1, login=1)
    except requests.exceptions.ConnectionError:
        roxywi_common.logging(server_ip, 'error: Cannot delete check from agent: connection error', roxywi=1, login=1)
    except Exception as e:
        raise Exception(f'error: Cannot delete check from Agent {server_ip}: {e}')


def send_tcp_checks(agent_id: int, server_ip: str) -> None:
    checks = smon_sql.select_en_smon_tcp(agent_id)
    for check in checks:
        json_data = {
            'check_type': 'tcp',
            'name': check.smon_id.name,
            'server_ip': check.ip,
            'port': check.port,
            'interval': check.interval
        }
        api_path = f'check/{check.smon_id}'
        try:
            send_post_request_to_agent(agent_id, server_ip, api_path, json_data)
        except Exception as e:
            raise Exception(f'{e}')


def send_ping_checks(agent_id: int, server_ip: str) -> None:
    checks = smon_sql.select_en_smon_ping(agent_id)
    for check in checks:
        json_data = {
            'check_type': 'ping',
            'name': check.smon_id.name,
            'server_ip': check.ip,
            'packet_size': check.packet_size,
            'interval': check.interval
        }
        api_path = f'check/{check.smon_id}'
        try:
            send_post_request_to_agent(agent_id, server_ip, api_path, json_data)
        except Exception as e:
            raise Exception(f'{e}')


def send_dns_checks(agent_id: int, server_ip: str) -> None:
    checks = smon_sql.select_en_smon_dns(agent_id)
    for check in checks:
        json_data = {
            'check_type': 'dns',
            'name': check.smon_id.name,
            'server_ip': check.ip,
            'port': check.port,
            'record_type': check.record_type,
            'resolver': check.resolver,
            'interval': check.interval
        }
        api_path = f'check/{check.smon_id}'
        try:
            send_post_request_to_agent(agent_id, server_ip, api_path, json_data)
        except Exception as e:
            raise Exception(f'{e}')


def send_http_checks(agent_id: int, server_ip: str) -> None:
    checks = smon_sql.select_en_smon_http(agent_id)
    for check in checks:
        json_data = {
            'check_type': 'http',
            'name': check.smon_id.name,
            'url': check.url,
            'http_method': check.method,
            'body': check.body,
            'interval': check.interval
        }
        api_path = f'check/{check.smon_id}'
        try:
            send_post_request_to_agent(agent_id, server_ip, api_path, json_data)
        except Exception as e:
            raise Exception(f'{e}')


def send_checks(agent_id: int) -> None:
    server_ip = smon_sql.select_server_ip_by_agent_id(agent_id)
    try:
        send_tcp_checks(agent_id, server_ip)
    except Exception as e:
        roxywi_common.logging(f'Agent ID: {agent_id}', f'error: Cannot send TCP checks: {e}', roxywi=1)
    try:
        send_ping_checks(agent_id, server_ip)
    except Exception as e:
        roxywi_common.logging(f'Agent ID: {agent_id}', f'error: Cannot send Ping checks: {e}', roxywi=1)
    try:
        send_dns_checks(agent_id, server_ip)
    except Exception as e:
        roxywi_common.logging(f'Agent ID: {agent_id}', f'error: Cannot send DNS checks: {e}', roxywi=1)
    try:
        send_http_checks(agent_id, server_ip)
    except Exception as e:
        roxywi_common.logging(f'Agent ID: {agent_id}', f'error: Cannot send HTTP checks: {e}', roxywi=1)
