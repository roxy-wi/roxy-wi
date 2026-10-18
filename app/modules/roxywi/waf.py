import hashlib
import json
from pathlib import Path
import re
from shlex import join

from flask import render_template
from peewee import IntegrityError

import app.modules.service.common as service_common
import app.modules.db.waf as waf_sql
import app.modules.db.user as user_sql
import app.modules.db.server as server_sql
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.roxywi.auth as roxywi_auth
from app.modules.db.db_model import WafRules
from app.modules.config import candidate, config, waf_state
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
    metrics_en, installed, waf_mode, mode_error = 0, False, '', False
    diagnostics = None
    if getattr(server, waf_service) == 1:
        if waf_service == 'haproxy':
            installed = bool(waf_sql.select_waf_servers(server.ip))
            metrics_en = waf_sql.select_waf_metrics_enable_server(server.ip)
        else:
            installed = bool(waf_sql.select_waf_nginx_servers(server.ip))
        if installed:
            diagnostics = read_waf_diagnostics(server.ip, server.server_id, waf_service)
            try:
                waf_mode = read_waf_mode(server.ip, waf_service)
            except Exception as exc:
                mode_error = True
                logger.exception('Cannot read WAF configuration mode', exc=exc, server_ip=server.ip)

    server_status = (server.hostname, server.ip, '', waf_mode, metrics_en, int(installed), server.server_id)
    return render_template('ajax/overviewWaf.html', service_status=[server_status], role=role,
                           waf_service=waf_service, lang=roxywi_common.get_user_lang_for_flask(), mode_error=mode_error,
                           waf_diagnostics=diagnostics,
                           waf_apply_status=waf_state.status(server.server_id, waf_service),
                           waf_apply_ip=server.ip, waf_apply_service=waf_service, waf_apply_button=False)


def read_waf_diagnostics(server_ip: str, server_id: int, service: str) -> dict:
    _require_waf_service(service)
    allowed = {
        'status': {'ok'}, 'process': {'running', 'stopped', 'missing', 'unknown'},
        'check': {'ready', 'unready', 'valid', 'invalid', 'not_checked'},
        'module': {'enabled', 'disabled', 'mixed', 'not_configured', 'not_applicable', 'unknown'},
        'error': {'', 'process_unavailable', 'config_unavailable', 'check_unavailable', 'process_changed'},
    }
    result = dict(process='unknown', check='not_checked', module='unknown', error='connection_failed')
    try:
        command = candidate.candidate_command(f'{service}_waf', common.get_waf_directory(service) + '/modsecurity.conf',
                                              '', 'status', **service_common.waf_runtime_settings(service, server_id))
        output = server_mod.ssh_command(server_ip, command, rc=1, timeout=90, error_context='Cannot inspect WAF status')
        value = json.loads(output)
        if (not isinstance(value, dict) or set(value) != set(allowed)
                or any(not isinstance(value[key], str) or value[key] not in options for key, options in allowed.items())):
            raise ValueError('Unconfirmed WAF diagnostic result')
        result = value
    except Exception as exc:
        # SSH exceptions can contain remote output. Log only the exception type.
        logger.warning('Cannot inspect WAF status', server_ip=server_ip, service=service, cause=type(exc).__name__)
    if result['error']:
        logger.warning('WAF diagnostic incomplete', server_ip=server_ip, service=service, reason=result['error'])
    reason = result['error']
    if result['process'] == 'missing':
        reason = 'missing'
    elif result['process'] == 'stopped':
        reason = 'stopped'
    elif not reason:
        if result['check'] in ('invalid', 'unready'):
            reason = result['check']
        elif result['module'] in ('disabled', 'mixed', 'not_configured', 'unknown'):
            reason = 'module_' + result['module']
        elif result['process'] == 'running' and result['check'] == ('ready' if service == 'haproxy' else 'valid'):
            reason = 'healthy'
        else:
            reason = 'check_unavailable'
    result['reason'] = reason
    result['tone'] = ('serverNone' if result['process'] == 'unknown' else
                      'serverDown' if result['process'] in ('stopped', 'missing') else
                      'serverUp' if reason == 'healthy' else 'serverWarn')
    return result


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
    with waf_state.operation_lock(serv.ip, service), waf_state.track_changes(server_id, service):
        _run_waf_file_command(serv.ip, root, ['set-mode', root + '/modsecurity.conf', waf_mode],
                              {'status': 'ok', 'mode': waf_mode})
        roxywi_common.logging(serv.hostname, f'WAF mode {waf_mode} saved in {service} configuration')


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
    with waf_state.operation_lock(serv, rule.service):
        rule = get_waf_rule(serv, rule_id, rule.service)
        root = common.get_waf_directory(rule.service)
        rule_path = common.resolve_waf_config_path(rule.service, rule.rule_file)
        entrypoint = common.get_waf_entrypoint(rule.service)
        # Always confirm the remote state, including after an interrupted SSH
        # response or database write. Repeating the desired state is idempotent.
        server_id = server_sql.get_server_by_ip(serv).server_id
        with waf_state.track_changes(server_id, rule.service):
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
    with waf_state.operation_lock(serv, service):
        existing = _existing_created_rule(serv, service, name, filename, description)
        if existing is not None:
            return existing
        server_id = server_sql.get_server_by_ip(serv).server_id
        with waf_state.track_changes(server_id, service):
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
