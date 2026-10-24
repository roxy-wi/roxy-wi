"""Single-server actions from a validated HAProxy Stats snapshot."""

import re

from app.modules.service.haproxy_runtime import execute_runtime_command
from app.modules.service.haproxy_stats import StatsError, collect_stats


def change_server(server: str, port: int, body: dict) -> str:
    """Use fresh runtime identities, never interpolate a client-supplied command."""
    if not isinstance(body, dict) or set(body) != {'row_key', 'pid', 'uptime', 'action', 'value'}:
        raise StatsError('invalid_action', 400)
    action, value = body['action'], body['value']
    if (not isinstance(body['row_key'], str) or not 0 < len(body['row_key']) <= 2048
            or type(body['pid']) is not int or body['pid'] < 1
            or type(body['uptime']) is not int or body['uptime'] < 0):
        raise StatsError('invalid_action', 400)
    if action == 'state':
        if not isinstance(value, str) or value not in ('ready', 'drain', 'maint'):
            raise StatsError('invalid_action', 400)
    elif action == 'weight':
        if type(value) is not int or not 0 <= value <= 256:
            raise StatsError('invalid_weight', 400)
    else:
        raise StatsError('invalid_action', 400)

    snapshot = collect_stats(server, port)
    if snapshot['info']['Pid'] != body['pid'] or snapshot['info']['Uptime_sec'] < body['uptime']:
        raise StatsError('target_changed', 409)
    row = next((row for row in snapshot['rows'] if row['key'] == body['row_key']), None)
    if row is None or row['kind'] != 'server':
        raise StatsError('target_changed', 409)
    # Names are resolved on the server and restricted to HAProxy identifier characters.
    # Do not accept CLI separators, escapes, whitespace or numeric-ID aliases from input.
    if any(not re.fullmatch(r'[A-Za-z0-9_.:-]+', row[key]) for key in ('proxy', 'name')):
        raise StatsError('unsupported_target', 409)
    command = f"set server {row['proxy']}/{row['name']} {action} {value}"
    try:
        response = execute_runtime_command(server, port, command)
    except (OSError, RuntimeError) as exc:
        # A lost reply does not prove the command failed. Never retry a write here.
        raise StatsError('action_unknown', 502) from exc
    if response.strip().startswith('Permission denied'):
        raise StatsError('action_permissions', 403)
    if response.strip():
        raise StatsError('command_rejected', 409)
    return command


def is_stats_server_command(action: str, arguments: str) -> bool:
    """Moved commands no longer execute through the legacy console."""
    return bool(re.search(
        r'(?:^|[;\n])\s*(?:(?:enable|disable)\s+server\b|set\s+(?:weight\b|maxconn\b|server\s+\S+\s+(?:state|weight|maxconn)\b))',
        f'{action} {arguments}',
    ))
