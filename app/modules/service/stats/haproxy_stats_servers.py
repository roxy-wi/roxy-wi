"""Persistent backend membership edits from a fresh Stats/configuration snapshot."""

from functools import partial
from copy import deepcopy
import hashlib
import json
import re

from app.modules.config import haproxy_files, runtime
from app.modules.db import add as add_sql, sql
from app.modules.roxywi.exception import RoxywiResourceNotFound
from app.modules.service.haproxy import _haproxy_line_tokens
from app.modules.service.stats.haproxy_stats import StatsError, collect_stats
from app.modules.service.stats import haproxy_stats_config as stats_config


NAME = re.compile(r'[A-Za-z0-9_.:-]{1,255}')


class ServerEditError(stats_config.ChangeError):
    incomplete_code = 'server_incomplete'
    settings_code = 'server_section_sync_failed'


def _snapshot(node, body, identity=None, selected=False):
    port = sql.get_setting('haproxy_sock_port', group_id=node.group_id)
    snapshot = collect_stats(node.ip, port)
    if selected:
        stats_config.check_process(snapshot, body['pid'], body['uptime'])
    kind = 'backend' if body['action'] == 'add' else 'server'
    matches = [row for row in snapshot['rows'] if row['kind'] == kind and (
        row['key'] == body['row_key'] if identity is None else (row['proxy'], row['name']) == identity)]
    if len(matches) != 1 or any(not NAME.fullmatch(matches[0][key]) for key in ('proxy', 'name')):
        raise StatsError('target_changed', 409)
    return snapshot, matches[0], port


def _address(value):
    host, separator, port = value.rpartition(':')
    host = host.strip('[]')
    if not separator or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise StatsError('server_config_target', 409)
    # DNS entries can be shown; changing them requires an explicit IP in the form.
    return {'address': host, 'port': int(port)}


def _prepare(node, paths, previous, *, body):
    row = previous['row'] if previous else None
    identity = (row['proxy'], row['name']) if row else None
    snapshot, row, port = _snapshot(node, body, identity, selected=previous is None)
    if haproxy_files.multiple_files_enabled(node.server_id):
        discovery = haproxy_files.discover_sources(node.ip, node.server_id)
        if discovery['state'] == 'error':
            raise StatsError('server_config_target', 409)
        remote_paths = discovery['files']
    else:
        remote_paths = [haproxy_files.resolve_path()]
    found, sources, source_digests = [], [], []
    for remote_path in dict.fromkeys(remote_paths):
        entry = stats_config.download_config(node, remote_path, paths)
        source_digests.append((remote_path, entry['digest']))
        try:
            lines = entry['content'].decode('utf-8').splitlines(keepends=True)
        except UnicodeDecodeError as exc:
            raise StatsError('server_config_target', 409) from exc
        sources.append(lines)
        try:
            section = runtime.find_section(lines, ('backend', 'listen'), row['proxy'], required=False)
        except RuntimeError as exc:
            raise StatsError('server_config_target', 409) from exc
        if section is not None:
            section = (*section, _haproxy_line_tokens(lines[section[0]])[0])
            entry['lines'] = lines
            entry['section'] = section
            found.append(entry)
    if len(found) != 1:
        raise StatsError('server_config_target', 409)
    entry = found[0]
    try:
        record = add_sql.get_section(node.server_id, entry['section'][2], row['proxy'],
                                     config_path=entry['remote_path'])
    except RoxywiResourceNotFound:
        record = None
    try:
        if body['action'] != 'add':
            runtime.server_line(entry['lines'], entry['section'], row['name'])
        else:
            entry['defaults'] = runtime.server_default_options(sources, row['proxy'])
    except RuntimeError as exc:
        raise StatsError('server_config_target', 409) from exc
    entry['snapshot'] = snapshot
    entry['row'] = row
    entry['port'] = port
    entry['record'] = record
    entry['source_digests'] = source_digests
    return entry


def _revision(entries):
    return hashlib.sha256(json.dumps([
        [entry['node'].ip, entry['remote_path'], entry['source_digests'], entry['snapshot']['info']['Pid'],
         entry['record'].config if entry['record'] else None] for entry in entries
    ], sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def describe(server, body):
    with stats_config.prepared_configs(stats_config.targets(server), partial(_prepare, body=body)) as (entries, _paths):
        entry = entries[0]
        value = {'name': '', 'address': '', 'port': 80, 'check': True, 'check_port': 80}
        if body['action'] == 'edit':
            _index, match = runtime.server_line(entry['lines'], entry['section'], entry['row']['name'])
            value = _address(match.group(4))
        return {'revision': _revision(entries), 'value': value,
                'targets': [{'ip': entry['node'].ip, 'hostname': entry['node'].hostname} for entry in entries]}


def _settings(entry, action, value):
    record, old_name = entry['record'], entry['row']['name']
    if record is None:
        return None
    updated = deepcopy(record.config)
    if updated.get('servers_template') not in (None, 'None'):
        raise StatsError('server_section_mismatch', 409)
    servers = updated.get('backend_servers') or []
    updated['backend_servers'] = servers
    matches = [item for item in servers if (item.get('name') or item['server']) == old_name]
    if action == 'add':
        if any((item.get('name') or item['server']) == value['name'] for item in servers):
            raise StatsError('server_exists', 409)
        servers.append({'server': value['address'], 'name': value['name'], 'port': value['port'],
                        'port_check': value['check_port'], 'check_enabled': value['check'],
                        'maxconn': 0, 'backup': False, 'send_proxy': False})
    else:
        if len(matches) != 1:
            raise StatsError('server_section_mismatch', 409)
        if action == 'delete':
            servers.remove(matches[0])
        else:
            matches[0]['server'] = value['address']
            matches[0]['port'] = value['port']
            matches[0]['name'] = old_name
    return updated


def _prepare_change(entry, body):
    action, value = body['action'], body['value']
    entry['settings'] = _settings(entry, action, value)
    path, backend, name = str(entry['path']), entry['row']['proxy'], entry['row']['name']
    if action == 'delete':
        runtime.delete_server(path, backend, name)
    elif action == 'edit':
        runtime.replace_server_address(path, backend, name, value['address'], value['port'])
    else:
        if any(row['kind'] == 'server' and row['proxy'] == backend and row['name'] == value['name']
               for row in entry['snapshot']['rows']):
            raise StatsError('server_exists', 409)
        section_config = entry['record'].config if entry['record'] else {}
        options = 'check' if value['check'] else 'no-check'
        checks = section_config.get('servers_check')
        if value['check'] and isinstance(checks, dict) and checks.get('check_enabled'):
            options += f" inter {checks['inter']} rise {checks['rise']} fall {checks['fall']}"
        ssl = section_config.get('ssl')
        if isinstance(ssl, dict) and section_config.get('mode') == 'http':
            options += f" ssl verify {'required' if ssl.get('ssl_check_backend') else 'none'}"
        entry['options'] = f"port {value['check_port']} {options} maxconn 0"
        endpoint = runtime.server_endpoint(value['address'], value['port'])
        runtime.insert_server(path, backend, f"server {value['name']} {endpoint} {entry['options']}")
        # Dynamic servers do not inherit default-server. Pass those options explicitly.
        # no-check is config-only; dynamic checks remain inactive unless enabled below.
        runtime_options = entry['options'] if value['check'] else entry['options'].replace(' no-check ', ' ', 1)
        entry['options'] = f"{entry['defaults']} {runtime_options}".strip()

    name = value['name'] if action == 'add' else name
    entry['message'] = f'HAProxy Stats: {action} server {backend}/{name}'


def _apply_runtime(entry, *, body) -> str:
    node, row, value = entry['node'], entry['row'], body['value']
    if body['action'] == 'add':
        runtime.add_server(node.ip, row['proxy'], value['name'], value['address'], value['port'],
                           value['check'], value['check_port'], sock_port=entry['port'], options=entry['options'])
    else:
        runtime.change_ip_and_port(node.ip, row['proxy'], row['name'], value['address'], value['port'],
                                   sock_port=entry['port'])
    # Runtime helpers have already validated HAProxy's textual success replies.
    return ''


def _save_settings(entry) -> None:
    add_sql.update_haproxy_server_settings(entry['record'], entry['settings'])


def change(server, body) -> list[dict[str, str]]:
    with stats_config.locked_targets(server, body['targets']) as nodes:
        with stats_config.prepared_configs(nodes, partial(_prepare, body=body)) as (entries, paths):
            if _revision(entries) != body['revision']:
                raise StatsError('target_changed', 409)
            for entry in entries:
                try:
                    _prepare_change(entry, body)
                except RuntimeError as exc:
                    raise StatsError('server_config_target', 409) from exc
            row = entries[0]['row']
            stats_config.validate_candidates(server, body['targets'], entries,
                refresh=lambda entry: _snapshot(entry['node'], body, (row['proxy'], row['name']))[0],
                invalid_code='server_config_invalid')
            return stats_config.apply_changes(entries, paths,
                apply_runtime=None if body['action'] == 'delete' else partial(_apply_runtime, body=body),
                save_settings=_save_settings, error_type=ServerEditError, report_settings=True,
                action='reload' if body['action'] == 'delete' else 'save')
