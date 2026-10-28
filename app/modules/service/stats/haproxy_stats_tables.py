"""Stick-table snapshots and transient changes through the existing Runtime API."""

import hashlib
import json
import re

from app.modules.common.time import utc_iso, utc_now
from app.modules.config import runtime
from app.modules.service.stats import haproxy_stats as stats, haproxy_stats_config as stats_config


_HEADER = re.compile(r'^# table: ([A-Za-z0-9_.:/-]+), type: (\w+), size:\s*(\d+), used:\s*(\d+)$')
_ENTRY = re.compile(r'^(0x[0-9a-fA-F]+): key=((?:\\.|[^\s\\])*)\s+(.+)$')
_FIELD = re.compile(r'([A-Za-z0-9_]+(?:\(\d+\))?)=(-?\d+)')


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()


def _check_response(response: str) -> str:
    if response.strip().startswith('Permission denied') or 'contents not dumped due to insufficient privileges' in response:
        raise stats.StatsError('runtime_permissions', 403)
    if response.strip() == 'No such table':
        raise stats.StatsError('table_gone', 409)
    return response


def _command_key(value: str, kind: str) -> str | None:
    """Decode dump_text's C escapes only when the key can round-trip over UTF-8."""
    if kind not in ('ip', 'ipv6', 'integer', 'string'):
        return None
    if kind == 'string':
        escapes = {'t': 9, 'n': 10, 'r': 13, 'e': 27, '\\': 92, ' ': 32, '=': 61}
        decoded = bytearray()
        index = 0
        try:
            while index < len(value):
                char = value[index]
                index += 1
                if char != '\\':
                    decoded.extend(char.encode('ascii'))
                elif value[index] == 'x':
                    decoded.append(int(value[index + 1:index + 3], 16))
                    index += 3
                else:
                    decoded.append(escapes[value[index]])
                    index += 1
            value = decoded.decode('utf-8')
        except (IndexError, KeyError, ValueError, UnicodeError):
            return None
    # Empty/binary/control-character keys remain readable. Do not translate them
    # into a different CLI key, or allow line delimiters into a Runtime command.
    return value if value and all(char.isprintable() for char in value) else None


def parse_tables(response: str) -> list[dict]:
    """Parse table headers and named counters, preserving every stored metric."""
    tables = []
    identifiers = set()
    for line in _check_response(response).splitlines():
        if not line.strip():
            continue
        header = _HEADER.fullmatch(line)
        if header:
            name, kind, size, used = header.groups()
            if any(table['name'] == name for table in tables):
                raise stats.StatsError('invalid_response')
            tables.append({'name': name, 'type': kind, 'size': int(size), 'used': int(used),
                           'revision': _digest([name, kind, size]), 'rows': []})
            identifiers = set()
            continue
        entry = _ENTRY.fullmatch(line)
        if not entry or not tables:
            raise stats.StatsError('invalid_response')
        pointer, key, values = entry.groups()
        parts = values.split()
        if not all(_FIELD.fullmatch(part) for part in parts):
            raise stats.StatsError('invalid_response')
        fields = dict(_FIELD.findall(values))
        if 'use' not in fields or 'exp' not in fields or pointer in identifiers:
            raise stats.StatsError('invalid_response')
        identifiers.add(pointer)
        command_key = _command_key(key, tables[-1]['type'])
        tables[-1]['rows'].append({'key': command_key if command_key is not None else key,
                                  'row_key': _digest([tables[-1]['revision'], pointer, key]),
                                  'fields': fields, 'deletable': command_key is not None})
    return tables


def collect_tables(server: str, port: int, table: str | None = None, *, expected: dict | None = None) -> dict:
    """Load the catalogue and only the selected table; reject mixed processes."""
    try:
        before = stats.parse_info(_check_response(stats.execute_runtime_command(server, port, 'show info')))
        if expected is not None:
            stats_config.check_process({'info': before}, expected['pid'], expected['uptime'])
        tables = parse_tables(runtime.get_all_stick_table(server, sock_port=port))
        selected = table or (tables[0]['name'] if tables else None)
        detail = None
        if selected is not None:
            if not any(item['name'] == selected for item in tables):
                raise stats.StatsError('table_gone', 409)
            details = parse_tables(runtime.get_stick_table(server, selected, sock_port=port))
            if len(details) != 1 or details[0]['name'] != selected:
                raise stats.StatsError('invalid_response')
            detail = details[0]
        info = stats.parse_info(_check_response(stats.execute_runtime_command(server, port, 'show info')))
    except TimeoutError as exc:
        raise stats.StatsError('runtime_timeout', 504) from exc
    except OSError as exc:
        raise stats.StatsError('runtime_unavailable', 503) from exc
    except RuntimeError as exc:
        raise stats.StatsError('response_too_large') from exc
    if before['Pid'] != info['Pid'] or before['Uptime_sec'] > info['Uptime_sec']:
        raise stats.StatsError('process_changed', 503)
    return {'status': 'ok', 'server': server, 'collected_at': utc_iso(utc_now()), 'info': info,
            'tables': [{key: value for key, value in item.items() if key != 'rows'} for item in tables],
            'table': detail}


def change(server: str, port: int, body: dict) -> dict:
    """Recheck a validated target, apply once, and report the observed remainder."""
    current = collect_tables(server, port, body['table'], expected=body)
    table = current['table']
    if table['revision'] != body['revision']:
        raise stats.StatsError('target_changed', 409)
    key = None
    if body['action'] == 'delete':
        row = next((row for row in table['rows'] if row['row_key'] == body['row_key']), None)
        if row is None:
            raise stats.StatsError('table_entry_gone', 410)
        if not row['deletable']:
            raise stats.StatsError('table_key_read_only', 409)
        key = row['key']
    # HAProxy has no conditional deletion. Check the process/table/entry just
    # before the command and never retry a lost reply: traffic can recreate keys.
    try:
        response = runtime.clear_stick_table(server, body['table'], sock_port=port, key=key).strip()
    except (OSError, RuntimeError) as exc:
        raise stats.StatsError('action_unknown') from exc
    if response.startswith('Permission denied'):
        raise stats.StatsError('action_permissions', 403)
    if response.startswith('Entry currently in use'):
        raise stats.StatsError('table_entry_in_use', 409)
    if response:
        raise stats.StatsError('command_rejected', 409)
    # This is an observed count, not a number of deleted entries. Active sessions
    # retain entries, and concurrent traffic/peers can repopulate the table.
    try:
        info = stats.parse_info(_check_response(stats.execute_runtime_command(server, port, 'show info')))
        stats_config.check_process({'info': info}, body['pid'], body['uptime'])
        tables = parse_tables(runtime.get_all_stick_table(server, sock_port=port))
        after = stats.parse_info(_check_response(stats.execute_runtime_command(server, port, 'show info')))
        if info['Pid'] != after['Pid'] or info['Uptime_sec'] > after['Uptime_sec']:
            raise stats.StatsError('process_changed', 503)
        remaining = next((item['used'] for item in tables if item['revision'] == body['revision']), None)
    except (stats.StatsError, OSError, RuntimeError):
        # The write succeeded; explicitly return an unavailable verification.
        return {'status': 'ok', 'remaining': None, 'verified': False}
    return {'status': 'ok', 'remaining': remaining, 'verified': remaining is not None}
