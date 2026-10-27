"""Session snapshots and single-session termination using existing Runtime commands."""

import hashlib
import json
import re

from app.modules.common.time import utc_now, utc_iso
from app.modules.config import runtime
from app.modules.service.stats import haproxy_stats as stats, haproxy_stats_config as stats_config


_SESSION = re.compile(r'^(0x[0-9a-fA-F]{1,16}):\s+(.+)$')
_FIELD = re.compile(r'(?:^|\s)([A-Za-z_][A-Za-z_0-9]*)=(\S+)')
_DETAIL = re.compile(r'^(0x[0-9a-fA-F]{1,16}):\s+\[([^\]\r\n]+)\]\s+id=(\d+)\s+proto=')


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()


def _check_response(response: str) -> str:
    if response.strip().startswith('Permission denied'):
        raise stats.StatsError('runtime_permissions', 403)
    return response


def parse_sessions(response: str) -> list[dict]:
    """Read named fields, not positional columns; keep the original line for details."""
    rows, identifiers = [], set()
    for line in response.splitlines():
        if not line.strip():
            continue
        match = _SESSION.fullmatch(line.strip())
        if not match:
            raise stats.StatsError('invalid_response')
        session_id, values = match.groups()
        fields = dict(_FIELD.findall(values))
        if not fields.get('proto') or session_id in identifiers:
            raise stats.StatsError('invalid_response')
        identifiers.add(session_id)
        # The epoch changes when a CLI dump starts. Together with the pointer and
        # endpoints it detects recycled streams between snapshots (HAProxy 2.8+).
        identity = [session_id, *[fields.get(key) for key in ('epoch', 'proto', 'src', 'fe', 'be', 'srv')]]
        rows.append({'id': session_id, 'key': _digest(identity), 'fields': fields, 'raw': line})
    return rows


def _snapshot(server: str, port: int, body: dict | None = None) -> dict:
    try:
        before = stats.parse_info(_check_response(stats.execute_runtime_command(server, port, 'show info')))
        if body is not None:
            stats_config.check_process({'info': before}, body['pid'], body['uptime'])
        rows = parse_sessions(_check_response(runtime.select_session(server, sock_port=port)))
        detail = None
        if body is not None:
            row = next((row for row in rows if row['id'] == body['session_id']), None)
            if row is None:
                raise stats.StatsError('session_gone', 410)
            if row['key'] != body['row_key']:
                raise stats.StatsError('target_changed', 409)
            raw = _check_response(runtime.show_session(server, row['id'], sock_port=port))
            if not raw.strip() or raw.startswith('Session not found') or 'session terminated while we were watching' in raw:
                raise stats.StatsError('session_gone', 410)
            header = _DETAIL.match(raw)
            # Detail output is intentionally not a stable HAProxy API. Unknown
            # versions remain readable, but cannot be used to authorize a write.
            epoch = re.search(r'\bepoch=(0x[0-9a-fA-F]+|0)\b', raw)
            revision = None
            if header and header[1] == row['id'] and epoch and row['fields'].get('epoch') == epoch[1]:
                revision = _digest([before['Pid'], *header.groups(), epoch[1]])
            detail = {'row': row, 'raw': raw, 'revision': revision}
        info = stats.parse_info(_check_response(stats.execute_runtime_command(server, port, 'show info')))
    except TimeoutError as exc:
        raise stats.StatsError('runtime_timeout', 504) from exc
    except OSError as exc:
        raise stats.StatsError('runtime_unavailable', 503) from exc
    except RuntimeError as exc:
        raise stats.StatsError('response_too_large') from exc
    if before['Pid'] != info['Pid'] or before['Uptime_sec'] > info['Uptime_sec']:
        raise stats.StatsError('process_changed', 503)
    result = {'status': 'ok', 'server': server, 'collected_at': utc_iso(utc_now()), 'info': info}
    if detail is None:
        result['rows'] = rows
    else:
        result['row'] = detail['row']
        result['raw'] = detail['raw']
        result['revision'] = detail['revision']
    return result


def collect_sessions(server: str, port: int) -> dict:
    return _snapshot(server, port)


def describe(server: str, port: int, body: dict) -> dict:
    return _snapshot(server, port, body)


def terminate(server: str, port: int, body: dict) -> str:
    current = describe(server, port, body)
    if current['revision'] is None or current['revision'] != body['revision']:
        raise stats.StatsError('target_changed', 409)
    # HAProxy only accepts a pointer for shutdown; it has no conditional-delete
    # command. Recheck immediately before the write and never retry a lost reply.
    try:
        response = runtime.delete_session(server, current['row']['id'], sock_port=port)
    except (OSError, RuntimeError) as exc:
        raise stats.StatsError('action_unknown') from exc
    response = response.strip()
    if response.startswith('Permission denied'):
        raise stats.StatsError('action_permissions', 403)
    if response.startswith('No such session'):
        raise stats.StatsError('session_gone', 410)
    if response:
        raise stats.StatsError('command_rejected', 409)
    return f"shutdown session {current['row']['id']}"
