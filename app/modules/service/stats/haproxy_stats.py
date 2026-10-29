"""Read-only HAProxy snapshots. No HTTP stats page or configuration writes."""

import csv
import io
import json

from app.modules.common.time import utc_now, utc_iso
from app.modules.service.managed_runtime import execute_runtime_command


class StatsError(Exception):
    def __init__(self, code: str, status: int = 502):
        super().__init__(code)
        self.code = code
        self.status = status


_KINDS = {'0': 'frontend', '1': 'backend', '2': 'server', '3': 'listener'}
_NUMERIC_FIELDS = frozenset('''
qcur qmax scur smax slim stot bin bout dreq dresp ereq econ eresp wretr wredis
weight act bck chkfail chkdown lastchg downtime qlimit pid iid sid throttle lbtot
rate rate_lim rate_max check_code check_duration hrsp_1xx hrsp_2xx hrsp_3xx
hrsp_4xx hrsp_5xx hrsp_other hanafail req_rate req_rate_max req_tot cli_abrt
srv_abrt comp_in comp_out comp_byp comp_rsp lastsess qtime ctime rtime ttime
agent_code agent_duration check_rise check_fall check_health agent_rise
agent_fall agent_health conn_rate conn_rate_max conn_tot intercepted dcon dses
wrew connect reuse cache_lookups cache_hits srv_icur src_ilim qtime_max
ctime_max rtime_max ttime_max eint idle_conn_cur safe_conn_cur used_conn_cur
need_conn_est uweight
'''.split())
_INFO_NUMBERS = frozenset('''
Pid Process_num Nbthread Nbproc Uptime_sec Maxconn Hard_maxconn CurrConns
CumConns ConnRate ConnRateLimit MaxConnRate SessRate SessRateLimit MaxSessRate
CurrSslConns MaxSslConns SslRate SslRateLimit MaxSslRate Idle_pct
'''.split())


def _number(value: str):
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise StatsError('invalid_response') from exc


def _state(status: str) -> str:
    status = status.upper()
    if status.startswith('MAINT'):
        return 'maint'
    if status.startswith('DRAIN'):
        return 'drain'
    if status.startswith(('DOWN', 'STOP')):
        return 'down'
    if status.startswith(('UP', 'OPEN')):
        return 'up'
    if status == 'NO CHECK':
        return 'no_check'
    if status.startswith('NOLB'):
        return 'nolb'
    return 'unknown'


def parse_stats(response: str) -> list[dict]:
    """Use CSV field names; retain unknown fields and distinguish absent from zero."""
    stream = io.StringIO(response.lstrip('\ufeff'))
    first = stream.readline().strip()
    if not first.startswith('#'):
        raise StatsError('invalid_response')
    try:
        header = next(csv.reader([first[1:].strip()], strict=True))
        header = [field.strip() for field in header]
        # HAProxy's CSV header and records normally end in an extra comma.
        while header and not header[-1]:
            header.pop()
        if (not {'pxname', 'svname', 'type'}.issubset(header)
                or len(set(header)) != len(header) or '' in header):
            raise StatsError('invalid_response')
        rows = []
        identities = set()
        for record in csv.reader(stream, strict=True):
            if not record:
                continue
            if len(record) < len(header) or any(record[len(header):]):
                raise StatsError('invalid_response')
            values = {key: (_number(value) if key in _NUMERIC_FIELDS else value or None)
                      for key, value in zip(header, record)}
            if not values['pxname'] or not values['svname'] or not values['type']:
                raise StatsError('invalid_response')
            key = json.dumps([values.get(field) for field in
                              ('pid', 'iid', 'type', 'sid', 'pxname', 'svname')], separators=(',', ':'))
            if key in identities:
                raise StatsError('invalid_response')
            identities.add(key)
            status = values.get('status') or ''
            rows.append({
                'key': key,
                'proxy': values['pxname'],
                'name': values['svname'],
                'kind': _KINDS.get(values['type'], 'unknown'),
                'status': status or None,
                'state': _state(status),
                'backup': values.get('bck') == 1,
                'mode': values.get('mode'),
                'address': values.get('addr'),
                'metrics': values,
            })
        return rows
    except (csv.Error, StopIteration) as exc:
        raise StatsError('invalid_response') from exc


def parse_info(response: str) -> dict:
    info = {}
    for line in response.splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition(':')
        if not separator or key in info:
            raise StatsError('invalid_response')
        value = value.strip()
        info[key] = _number(value) if key in _INFO_NUMBERS else value or None
    if any(info.get(key) is None for key in ('Version', 'Pid', 'Uptime_sec')):
        raise StatsError('invalid_response')
    return info


def collect_stats(server: str, port: int) -> dict:
    """Bracket stats with process info so a reload cannot mix two generations."""
    def read(command):
        response = execute_runtime_command(server, port, command)
        if response.strip().startswith('Permission denied'):
            raise StatsError('runtime_permissions')
        return response

    try:
        before = parse_info(read('show info'))
        rows = parse_stats(read('show stat'))
        info = parse_info(read('show info'))
    except TimeoutError as exc:
        raise StatsError('runtime_timeout', 504) from exc
    except OSError as exc:
        raise StatsError('runtime_unavailable', 503) from exc
    except RuntimeError as exc:
        # The shared transport bounds the response size. Never return its raw text.
        raise StatsError('response_too_large') from exc

    if (before['Pid'] != info['Pid'] or before['Uptime_sec'] > info['Uptime_sec']
            or any(row['metrics'].get('pid') not in (None, info.get('Process_num'))
                   for row in rows if info.get('Process_num') is not None)):
        raise StatsError('process_changed', 503)
    servers = [row for row in rows if row['kind'] == 'server']
    return {
        'status': 'ok',
        'server': server,
        'collected_at': utc_iso(utc_now()),
        'info': info,
        'rows': rows,
        'summary': {
            'frontends': sum(row['kind'] == 'frontend' for row in rows),
            'backends': sum(row['kind'] == 'backend' for row in rows),
            'servers': len(servers),
            'down': sum(row['state'] == 'down' for row in servers),
            'maint': sum(row['state'] == 'maint' for row in servers),
            'drain': sum(row['state'] in ('drain', 'nolb') for row in servers),
        },
    }
