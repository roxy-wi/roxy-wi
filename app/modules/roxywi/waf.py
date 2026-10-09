import hashlib
import json
from pathlib import Path
import re
from shlex import join, quote

from flask import render_template
from peewee import IntegrityError

import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
import app.modules.db.user as user_sql
import app.modules.db.server as server_sql
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.roxywi.auth as roxywi_auth
from app.modules.db.db_model import WafRules
from app.modules.common.file_lock import file_lock
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiPermissionError, RoxywiValidationError


def get_waf_rule(server_ip: str, rule_id: int, service: str = None) -> WafRules:
    """Resolve the rule owner before reading or changing its remote files.

    The legacy toggle URL has no service; derive it from the server-scoped rule.
    """
    rule = waf_sql.get_waf_rule(rule_id, server_ip, service)
    if rule.service not in ('haproxy', 'nginx'):
        raise RoxywiValidationError('Unsupported WAF service')
    if not roxywi_auth.is_access_permit_to_service(rule.service):
        raise RoxywiPermissionError()
    return rule


def waf_overview(serv: str, waf_service: str, claims: dict) -> str:
    server = server_sql.get_server_by_ip(serv)
    role = user_sql.get_user_role_in_group(claims['user_id'], claims['group'])
    returned_servers = []
    waf = ''
    metrics_en = 0
    waf_process = ''
    waf_mode = ''
    is_waf_on_server = 0
    waf_len = 0
    server_status = (
        server.hostname, server.ip, waf_process, waf_mode, metrics_en, waf_len, server.server_id
    )

    if waf_service == 'haproxy':
        is_waf_on_server = server.haproxy
    elif waf_service == 'nginx':
        is_waf_on_server = server.nginx

    if is_waf_on_server == 1:
        config_path = sql.get_setting(f'{waf_service}_dir')
        if waf_service == 'haproxy':
            waf = waf_sql.select_waf_servers(server.ip)
            metrics_en = waf_sql.select_waf_metrics_enable_server(server.ip)
        elif waf_service == 'nginx':
            waf = waf_sql.select_waf_nginx_servers(server.ip)
        try:
            waf_len = len(waf)
        except Exception:
            waf_len = 0

        if waf_len >= 1:
            if waf_service == 'haproxy':
                command = "ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l"
            elif waf_service == 'nginx':
                command = f"grep 'modsecurity on' {common.return_nice_path(config_path)}* --exclude-dir=waf -Rs |wc -l"
            commands1 = f"grep SecRuleEngine {config_path}/waf/modsecurity.conf |grep -v '#' |awk '{{print $2}}'"
            waf_process = server_mod.ssh_command(server.ip, command)
            waf_mode = server_mod.ssh_command(server.ip, commands1).strip()

            server_status = (server.hostname,
                             server.ip,
                             waf_process,
                             waf_mode,
                             metrics_en,
                             waf_len,
                             server.server_id)
        else:
            server_status = (server.hostname,
                             server.ip,
                             waf_process,
                             waf_mode,
                             metrics_en,
                             waf_len,
                             server.server_id)
    returned_servers.append(server_status)

    lang = roxywi_common.get_user_lang_for_flask()
    servers_sorted = sorted(returned_servers, key=common.get_key)

    return render_template('ajax/overviewWaf.html', service_status=servers_sorted, role=role, waf_service=waf_service, lang=lang)


def change_waf_mode(waf_mode: str, server_id: int, service: str) -> None:
    serv = server_sql.get_server(server_id)

    if service == 'haproxy':
        config_dir = sql.get_setting('haproxy_dir')
    elif service == 'nginx':
        config_dir = sql.get_setting('nginx_dir')

    commands = f"sudo sed -i 's/^SecRuleEngine.*/SecRuleEngine {waf_mode}/' {config_dir}/waf/modsecurity.conf"
    server_mod.ssh_command(serv.ip, commands)

    roxywi_common.logging(serv.hostname, f'Has been changed WAF mod to {waf_mode}')


def switch_waf_rule(serv: str, enable: int, rule_id: int):
    rule = get_waf_rule(serv, rule_id)
    rule_file = rule.rule_file
    rule_file_path = f'Include {common.resolve_waf_config_path(rule.service, rule_file)}'
    conf_file_path = common.get_waf_directory(rule.service) + '/modsecurity.conf'

    if enable == 0:
        replacement = f's!{rule_file_path}!#{rule_file_path}!'
        en_for_log = 'disabled'
    else:
        replacement = f's!#{rule_file_path}!{rule_file_path}!'
        en_for_log = 'enabled'
    cmd = f'sudo sed -i {quote(replacement)} {quote(conf_file_path)}'

    roxywi_common.logging('WAF', f' Has been {en_for_log} WAF rule: {rule_file} for the server {serv}')
    waf_sql.update_enable_waf_rules(rule_id, serv, enable)
    server_mod.ssh_command(serv, cmd)


def _existing_created_rule(serv: str, service: str, name: str, filename: str, description: str) -> int | None:
    rules = waf_sql.find_waf_rule_conflicts(serv, service, name, filename)
    if not rules:
        return None
    if len(rules) == 1:
        rule = rules[0]
        if (rule.rule_name, rule.rule_file, rule.desc) == (name, filename, description):
            return rule.id
    raise RoxywiConflictError('A WAF rule with this name or filename already exists')


def create_waf_rule(serv: str, service: str, json_data: dict) -> int:
    if service not in ('haproxy', 'nginx'):
        raise RoxywiValidationError('Unsupported WAF service')
    if not roxywi_auth.is_access_permit_to_service(service):
        raise RoxywiPermissionError()
    if not isinstance(json_data, dict):
        raise RoxywiValidationError('Invalid rule creation request')
    values = [json_data.get(key) for key in ('new_waf_rule', 'new_rule_description', 'new_rule_file')]
    if any(not isinstance(value, str) or not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)
           for value in values):
        raise RoxywiValidationError('Rule name, description and filename are required')
    name, description, filename = (value.strip() for value in values)
    # Keep the existing API accepting a filename stem; the UI supplies .conf.
    if not filename.endswith('.conf'):
        filename += '.conf'
    if (len(name) > 255 or len(description) > 4096 or len(filename) > 255
            or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9._-]*\.conf', filename)):
        raise RoxywiValidationError('Invalid rule name, description or filename')
    root = common.get_waf_directory(service)
    rule_path = common.resolve_waf_config_path(service, filename)
    # Both installations load modsecurity.conf. Keep custom rules here until
    # Include placement and the existing rule toggle are updated together.
    entrypoint = root + '/modsecurity.conf'
    request_id = hashlib.sha256(json.dumps([serv, service, name, filename, description],
                                           ensure_ascii=True).encode('utf-8')).hexdigest()
    lock_id = hashlib.sha256(f'{serv}\0{service}'.encode('utf-8')).hexdigest()
    lock_dir = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'waf-locks'
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Serialize the catalog check, SSH and insert across workers on shared storage.
    # No database transaction is held while waiting for the remote host.
    with file_lock(lock_dir / f'{lock_id}.lock'):
        existing = _existing_created_rule(serv, service, name, filename, description)
        if existing is not None:
            return existing
        script = Path(__file__).with_name('waf_rule_file.py').read_text(encoding='utf-8')
        remote_lock = hashlib.sha256(root.encode('utf-8')).hexdigest()
        command = join(['sudo', '-n', 'flock', '-w', '30', f'/var/lock/roxywi-waf-{remote_lock}.lock',
                        'python3', '-c', script, entrypoint, rule_path, request_id])
        output = server_mod.ssh_command(serv, command, rc=1, timeout=45, error_context='Cannot create WAF rule')
        result = json.loads(output)
        if result == {'status': 'conflict'}:
            raise RoxywiConflictError('The WAF rule file or its Include already exists or has changed')
        if result != {'status': 'ok'}:
            raise RuntimeError('Unexpected WAF rule creation result')
        try:
            last_id = waf_sql.insert_new_waf_rule(name, filename, description, service, serv)
        except IntegrityError:
            existing = _existing_created_rule(serv, service, name, filename, description)
            if existing is not None:
                return existing
            raise
        # A failed insert/SSH response leaves an empty marked file. An identical
        # retry resumes creation without overwriting files or repeating Include.
        roxywi_common.logging('WAF', f'A new rule has been created {filename} on the server {serv}')
        return last_id
