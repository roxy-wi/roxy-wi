"""Persist Stats Maxconn edits using the existing HAProxy configuration workflow."""

from functools import partial
import re

from app.modules.config import haproxy_files, runtime
from app.modules.db import add as add_sql, sql
from app.modules.service.managed_runtime import execute_runtime_command
from app.modules.service.stats.haproxy_stats import StatsError, collect_stats
from app.modules.service.stats import haproxy_stats_config as stats_config


class MaxconnError(stats_config.ChangeError):
    incomplete_code = 'maxconn_incomplete'
    settings_code = 'maxconn_section_sync_failed'


def _target(snapshot, scope, row_key=None, identity=None):
    if scope == 'global':
        return None
    matches = [row for row in snapshot['rows'] if row['kind'] == scope and (
        row['key'] == row_key if identity is None else (row['proxy'], row['name']) == identity)]
    if len(matches) != 1:
        raise StatsError('target_changed', 409)
    row = matches[0]
    if any(not re.fullmatch(r'[A-Za-z0-9_.:-]+', row[key]) for key in ('proxy', 'name')):
        raise StatsError('unsupported_target', 409)
    return row


def _snapshot(node, body, identity=None, selected=False):
    port = sql.get_setting('haproxy_sock_port', group_id=node.group_id)
    snapshot = collect_stats(node.ip, port)
    if selected:
        stats_config.check_process(snapshot, body['pid'], body['uptime'])
    row = _target(snapshot, body['scope'], body['row_key'], identity)
    if body['scope'] == 'global':
        ceiling = snapshot['info'].get('Hard_maxconn')
        if type(ceiling) is not int:
            raise StatsError('invalid_response')
        if body['value'] > ceiling:
            raise StatsError('maxconn_limit', 409)
    return snapshot, row, port


def _prepare(node, paths, previous, *, body):
    row = previous['row'] if previous else None
    identity = (row['proxy'], row['name']) if row else None
    snapshot, row, port = _snapshot(node, body, identity, selected=previous is None)
    entry = stats_config.download_config(node, haproxy_files.resolve_path(), paths)
    entry['snapshot'] = snapshot
    entry['row'] = row
    entry['port'] = port
    return entry


def _prepare_change(entry, body):
    scope, value, row = body['scope'], body['value'], entry['row']
    section_name = '' if scope == 'global' else row['proxy']
    section_types = {'global': 'global', 'frontend': ('frontend', 'listen'), 'server': ('backend', 'listen')}[scope]
    candidate = str(entry['path'])
    lines = runtime.read_config_lines(candidate)
    start, _end = runtime.find_section(lines, section_types, section_name)
    entry['section_type'] = lines[start].strip().split()[0]
    entry['section_name'] = section_name or 'global'
    if scope == 'server':
        runtime.set_server_maxconn(candidate, row['proxy'], row['name'], value)
    else:
        runtime.set_section_maxconn(candidate, section_types, section_name, value)
    target = f"{row['proxy']}/{row['name']}" if scope == 'server' else section_name
    arguments = f'{target} {value}' if target else f'{value}'
    entry['command'] = f'set maxconn {scope} {arguments}'
    entry['message'] = f"HAProxy Stats: {entry['command']}"
    entry['success_message'] = f"{entry['message']}; configuration saved"


def _apply_runtime(entry) -> str:
    return execute_runtime_command(entry['node'].ip, entry['port'], entry['command'])


def _save_settings(entry, *, body) -> None:
    add_sql.update_haproxy_section_maxconn(
        entry['node'].server_id, entry['section_type'], entry['section_name'], body['value'],
        server_name=entry['row']['name'] if body['scope'] == 'server' else None,
        config_path=entry['remote_path'])


def change(server, body) -> list[dict[str, str]]:
    with stats_config.locked_targets(server, body['targets']) as nodes:
        with stats_config.prepared_configs(nodes, partial(_prepare, body=body)) as (entries, paths):
            for entry in entries:
                try:
                    _prepare_change(entry, body)
                except RuntimeError as exc:
                    raise StatsError('maxconn_config_target', 409) from exc
            row = entries[0]['row']
            identity = (row['proxy'], row['name']) if row else None
            stats_config.validate_candidates(server, body['targets'], entries,
                refresh=lambda entry: _snapshot(entry['node'], body, identity, selected=entry['node'].ip == server.ip)[0],
                invalid_code='maxconn_config_invalid')
            return stats_config.apply_changes(entries, paths, apply_runtime=_apply_runtime,
                save_settings=partial(_save_settings, body=body), error_type=MaxconnError)
