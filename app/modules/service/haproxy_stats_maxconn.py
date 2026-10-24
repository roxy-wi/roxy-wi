"""Persist Stats Maxconn edits using the existing HAProxy configuration workflow."""

from contextlib import ExitStack
import hashlib
from pathlib import Path
import re

from app.modules.common.file_lock import file_lock
from app.modules.config import config, common as config_common, deployment_policy, haproxy_files, runtime
from app.modules.db import add as add_sql, server as server_sql, sql
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi import common
from app.modules.roxywi.error_handler import safe_error_message
from app.modules.roxywi.exception import RoxywiPermissionError
from app.modules.service.haproxy_runtime import execute_runtime_command
from app.modules.service.haproxy_stats import StatsError, collect_stats


class MaxconnError(StatsError):
    def __init__(self, code, nodes):
        super().__init__(code, 502)
        self.nodes = nodes


def targets(server):
    """Keep the existing selected-node -> direct replicas propagation topology."""
    nodes = {server.ip: server}
    for ip, _hostname in server_sql.is_master(server.ip):
        if ip:
            nodes[ip] = common.require_server_access(ip)
    for node in nodes.values():
        if not node.haproxy:
            raise StatsError('unsupported_target', 409)
        try:
            deployment_policy.require_direct_deployment_for_server(node.ip, 'haproxy', action='save')
        except RoxywiPermissionError as exc:
            raise StatsError('maxconn_policy', 403) from exc
    return [server, *[nodes[ip] for ip in sorted(nodes) if ip != server.ip]]


def _target(snapshot, scope, row_key=None, identity=None):
    if scope == 'global':
        return None
    rows = [row for row in snapshot['rows'] if row['kind'] == scope and (
        row['key'] == row_key if identity is None else (row['proxy'], row['name']) == identity)]
    if len(rows) != 1:
        raise StatsError('target_changed', 409)
    row = rows[0]
    if any(not re.fullmatch(r'[A-Za-z0-9_.:-]+', row[key]) for key in ('proxy', 'name')):
        raise StatsError('unsupported_target', 409)
    return row


def _validate(body):
    if not isinstance(body, dict) or set(body) != {'scope', 'row_key', 'pid', 'uptime', 'value', 'targets'}:
        raise StatsError('invalid_action', 400)
    scope = body['scope']
    if not isinstance(scope, str) or scope not in ('global', 'frontend', 'server'):
        raise StatsError('invalid_action', 400)
    if (type(body['value']) is not int or not (0 if scope == 'server' else 1) <= body['value'] <= 2147483647):
        raise StatsError('invalid_maxconn', 400)
    if (type(body['pid']) is not int or body['pid'] < 1 or type(body['uptime']) is not int
            or body['uptime'] < 0 or not isinstance(body['targets'], list)
            or any(not isinstance(ip, str) for ip in body['targets'])):
        raise StatsError('invalid_action', 400)
    if scope == 'global':
        if body['row_key'] is not None:
            raise StatsError('invalid_action', 400)
    elif not isinstance(body['row_key'], str) or not 0 < len(body['row_key']) <= 2048:
        raise StatsError('invalid_action', 400)


def _snapshot(node, body, identity=None, selected=False):
    port = sql.get_setting('haproxy_sock_port', group_id=node.group_id)
    snapshot = collect_stats(node.ip, port)
    if selected and (snapshot['info']['Pid'] != body['pid'] or snapshot['info']['Uptime_sec'] < body['uptime']):
        raise StatsError('target_changed', 409)
    row = _target(snapshot, body['scope'], body['row_key'], identity)
    if body['scope'] == 'global':
        ceiling = snapshot['info'].get('Hard_maxconn')
        if type(ceiling) is not int:
            raise StatsError('invalid_response')
        if body['value'] > ceiling:
            raise StatsError('maxconn_limit', 409)
    return snapshot, row, port


def change(server, body):
    _validate(body)
    nodes = targets(server)
    if body['targets'] != [node.ip for node in nodes]:
        raise StatsError('target_changed', 409)
    lock_dir = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'stats-maxconn-locks'
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ExitStack() as locks:
        # Stable ordering also serializes requests with overlapping replica sets.
        for node in sorted(nodes, key=lambda node: node.ip):
            locks.enter_context(file_lock(lock_dir / (hashlib.sha256(node.ip.encode()).hexdigest() + '.lock')))
        if [node.ip for node in targets(server)] != body['targets']:
            raise StatsError('target_changed', 409)
        return _change_locked(server, nodes, body)


def _change_locked(server, nodes, body):
    prepared, paths = [], []
    scope, value = body['scope'], body['value']
    config_path = haproxy_files.resolve_path()
    identity = None
    try:
        for node in nodes:
            snapshot, row, port = _snapshot(node, body, identity, selected=node.ip == server.ip)
            if row and identity is None:
                identity = (row['proxy'], row['name'])
            baseline = Path(config_common.generate_config_path('haproxy', node.ip))
            paths.append(baseline)
            config.get_config(node.ip, str(baseline), config_file_name=config_path)
            prepared.append(dict(node=node, snapshot=snapshot, port=port, baseline=baseline,
                                 digest=hashlib.sha256(baseline.read_bytes()).hexdigest()))
        candidate = Path(config_common.generate_config_path('haproxy', server.ip))
        paths.append(candidate)
        candidate.write_bytes(prepared[0]['baseline'].read_bytes())
        try:
            section_name = '' if scope == 'global' else identity[0]
            section_types = {'global': 'global', 'frontend': ('frontend', 'listen'), 'server': ('backend', 'listen')}[scope]
            lines = runtime._read_config_lines(str(candidate))
            start, _end = runtime._find_section(lines, section_types, section_name)
            section_type = lines[start].strip().split()[0]
            if scope == 'server':
                runtime._set_server_maxconn(str(candidate), *identity, value)
                target = '/'.join(identity)
            elif scope == 'frontend':
                # A listen section also produces a FRONTEND row.
                runtime._set_section_maxconn(str(candidate), ('frontend', 'listen'), identity[0], value)
                target = identity[0]
            else:
                runtime._set_section_maxconn(str(candidate), 'global', '', value)
                target = ''
        except RuntimeError as exc:
            raise StatsError('maxconn_config_target', 409) from exc
        command = f'set maxconn {scope} ' + (target + ' ' if target else '') + str(value)
        # Validate the shared candidate on every node before any runtime write.
        try:
            for entry in prepared:
                config.validate_candidate_config(entry['node'].ip, str(candidate), 'haproxy')
        except Exception as exc:
            safe_error_message(exc)
            raise StatsError('maxconn_config_invalid', 409) from exc
        for entry in prepared:
            fresh, _row, _port = _snapshot(entry['node'], body, identity, selected=entry['node'].ip == server.ip)
            if (fresh['info']['Pid'] != entry['snapshot']['info']['Pid']
                    or fresh['info']['Uptime_sec'] < entry['snapshot']['info']['Uptime_sec']):
                raise StatsError('target_changed', 409)
        if [node.ip for node in targets(server)] != body['targets']:
            raise StatsError('target_changed', 409)
        results = [dict(server=node.ip, runtime='pending', config='pending') for node in nodes]
        for entry, result in zip(prepared, results):
            node = entry['node']
            result['runtime'] = 'unknown'
            try:
                reply = execute_runtime_command(node.ip, entry['port'], command)
                if reply.strip():
                    result['runtime'] = 'failed'
                    raise StatsError('action_permissions' if reply.strip().startswith('Permission denied') else 'command_rejected')
                result['runtime'] = 'applied'
                result['config'] = 'unknown'
                if node.ip == server.ip:
                    # ConfigVersion references this file; retain it even if the
                    # reply is lost after the version has been recorded.
                    paths.remove(candidate)
                # Use the standard validator, atomic save, version and audit path.
                # Compare each node's own baseline under the remote configuration lock.
                config.upload_and_restart(node.ip, str(candidate), 'save', 'haproxy',
                                          config_file_name=config_path,
                                          expected_sha256=entry['digest'],
                                          record_version=node.ip == server.ip,
                                          version_message=f'HAProxy Stats: {command}')
                result['config'] = 'saved'
                try:
                    add_sql.update_haproxy_section_maxconn(
                        node.server_id, section_type, section_name or 'global', value,
                        server_name=identity[1] if scope == 'server' else None, config_path=config_path)
                except Exception as exc:
                    raise MaxconnError('maxconn_section_sync_failed', results) from exc
                common.logging(node.ip, f'HAProxy Stats: {command}; configuration saved', keep_history=1, service='haproxy')
            except Exception as exc:
                safe_error_message(exc)
                common.logging(node.ip, f'HAProxy Stats: {command}; runtime={result["runtime"]}, config={result["config"]}',
                               keep_history=1, service='haproxy')
                # Neither retries nor rollback can safely undo an unconfirmed write.
                if isinstance(exc, MaxconnError):
                    raise
                raise MaxconnError('maxconn_incomplete', results) from exc
        return results
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
