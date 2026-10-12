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
from app.modules.roxywi import logger
from app.modules.roxywi.waf_rule_file import WAF_MODES


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
    _require_waf_service(waf_service)
    server = server_sql.get_server_by_ip(serv)
    role = user_sql.get_user_role_in_group(claims['user_id'], claims['group'])
    returned_servers = []
    waf = ''
    metrics_en = 0
    waf_process = ''
    waf_mode = ''
    is_waf_on_server = 0
    waf_len = 0
    mode_error = False
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
        waf_len = int(bool(waf))

        if waf_len >= 1:
            if waf_service == 'haproxy':
                command = "ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l"
            elif waf_service == 'nginx':
                command = f"grep -Rs --exclude-dir=waf -- 'modsecurity on' {quote(config_path)} |wc -l"
            waf_process = server_mod.ssh_command(server.ip, command)
            try:
                waf_mode = read_waf_mode(server.ip, waf_service)
            except Exception as exc:
                mode_error = True
                logger.exception('Cannot read WAF configuration mode', exc=exc, server_ip=server.ip)

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

    return render_template('ajax/overviewWaf.html', service_status=servers_sorted, role=role,
                           waf_service=waf_service, lang=lang, mode_error=mode_error)


def _require_waf_service(service: str) -> None:
    if service not in ('haproxy', 'nginx'):
        raise RoxywiValidationError('Unsupported WAF service')
    if not roxywi_auth.is_access_permit_to_service(service):
        raise RoxywiPermissionError()


def read_waf_mode(serv: str, service: str) -> str:
    _require_waf_service(service)
    root = common.get_waf_directory(service)
    result = _run_waf_file_command(serv, root, ['read-mode', root + '/modsecurity.conf'])
    if set(result) != {'status', 'mode'} or result['mode'] not in WAF_MODES:
        raise RuntimeError('Unconfirmed WAF configuration mode')
    return result['mode']


def change_waf_mode(waf_mode: str, server_id: int, service: str) -> None:
    _require_waf_service(service)
    if waf_mode not in WAF_MODES:
        raise RoxywiValidationError('Unsupported WAF mode')
    serv = server_sql.get_server(server_id)
    roxywi_common.check_is_server_in_group(serv.ip)
    root = common.get_waf_directory(service)
    with _waf_lock(serv.ip, service):
        _run_waf_file_command(serv.ip, root, ['set-mode', root + '/modsecurity.conf', waf_mode],
                              {'status': 'ok', 'mode': waf_mode})
        roxywi_common.logging(serv.hostname, f'WAF mode {waf_mode} saved in {service} configuration')


def _waf_lock(serv: str, service: str):
    lock_id = hashlib.sha256(f'{serv}\0{service}'.encode('utf-8')).hexdigest()
    lock_dir = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'waf-locks'
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return file_lock(lock_dir / f'{lock_id}.lock')


def _run_waf_file_command(serv: str, root: str, arguments: list[str], expected: dict = None) -> dict:
    script = Path(__file__).with_name('waf_rule_file.py').read_text(encoding='utf-8')
    remote_lock = hashlib.sha256(root.encode('utf-8')).hexdigest()
    command = join(['sudo', '-n', 'flock', '-w', '30', f'/var/lock/roxywi-waf-{remote_lock}.lock',
                    'python3', '-c', script, *arguments])
    output = server_mod.ssh_command(serv, command, rc=1, timeout=45, error_context='Cannot update WAF rule files')
    result = json.loads(output)
    if result == {'status': 'conflict'}:
        raise RoxywiConflictError('The WAF rule file or its Include is ambiguous or has changed')
    if not isinstance(result, dict) or result.get('status') != 'ok' or (expected is not None and result != expected):
        raise RuntimeError('Unexpected WAF file operation result')
    return result


def switch_waf_rule(serv: str, enable: int, rule_id: int, service: str = None) -> None:
    if enable not in (0, 1):
        raise RoxywiValidationError('Rule state must be 0 or 1')
    rule = get_waf_rule(serv, rule_id, service)
    with _waf_lock(serv, rule.service):
        rule = get_waf_rule(serv, rule_id, rule.service)
        root = common.get_waf_directory(rule.service)
        rule_path = common.resolve_waf_config_path(rule.service, rule.rule_file)
        entrypoint = common.get_waf_entrypoint(rule.service)
        # Always confirm the remote state, including after an interrupted SSH
        # response or database write. Repeating the desired state is idempotent.
        _run_waf_file_command(serv, root, ['toggle', entrypoint, rule_path, str(enable)],
                              {'status': 'ok', 'enabled': enable})
        waf_sql.update_enable_waf_rules(rule_id, serv, enable)
        state = 'enabled' if enable else 'disabled'
        roxywi_common.logging('WAF', f'WAF rule {rule.rule_file} {state} in configuration on {serv}')


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
    entrypoint = common.get_waf_entrypoint(service)
    request_id = hashlib.sha256(json.dumps([serv, service, name, filename, description],
                                           ensure_ascii=True).encode('utf-8')).hexdigest()
    # Serialize the catalog check, SSH and insert across workers on shared storage.
    # No database transaction is held while waiting for the remote host.
    with _waf_lock(serv, service):
        existing = _existing_created_rule(serv, service, name, filename, description)
        if existing is not None:
            return existing
        _run_waf_file_command(serv, root, [entrypoint, rule_path, request_id], {'status': 'ok'})
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
