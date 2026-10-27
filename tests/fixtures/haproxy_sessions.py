"""HAProxy 2.8 session wire format, with only the external transport replaced."""
from types import SimpleNamespace

import pytest

from app.modules.config import runtime
from app.modules.db.db_model import Setting
from app.modules.service.stats import haproxy_stats
from tests.fixtures.haproxy_stats import INFO, stats_csv


ROWS = [
    dict(id='0x7f001', proto='tcpv4', src='203.0.113.42:51832', fe='public', be='web', srv='one',
         epoch='0x2', age='2m14s', calls='42', rate='2'),
    dict(id='0x7f002', proto='tcpv6', src='2001:db8::20:60421', fe='public', be='web', srv='two',
         epoch='0x2', age='48s', calls='7', rate='0'),
    dict(id='0x7f003', proto='tcpv4', src='192.0.2.25:56012', fe='tcp_in', be='database', srv='primary',
         epoch='0x3', age='7m3s', calls='1', rate='0'),
]


def session_lines(rows=None):
    return ''.join(row['id'] + ': ' + ' '.join(f'{key}={value}' for key, value in row.items() if key != 'id')
                   + ' rq[f=848000h,i=0,an=00h] rp[f=800000h,i=0,an=00h] task=0x123(exp=<NEVER>)\n'
                   for row in (ROWS if rows is None else rows))


def session_detail(row, uid=123):
    return (f"{row['id']}: [26/Oct/2026:12:00:00.123456] id={uid} proto={row['proto']} source={row.get('src', '')}\n"
            f"  flags=0x8000, conn_retries=0 epoch={row.get('epoch', '0')}\n"
            f"  frontend={row.get('fe', '<NONE>')} (id=2 mode=http), backend={row.get('be', '<NONE>')}\n")


@pytest.fixture
def sessions_host(product, monkeypatch):
    state = SimpleNamespace(rows=[dict(row) for row in ROWS], info=INFO, calls=[], writes=[],
                            read_failure=None, write_failure=None, reply='', detail_override=None, uid=123,
                            list_override=None)
    Setting.update(value='1999').where(Setting.param == 'haproxy_sock_port', Setting.group_id == 1).execute()

    def execute(server, port, command):
        assert int(port) == 1999
        state.calls.append((server, command))
        if command.startswith('shutdown session '):
            state.writes.append((server, command))
            if state.write_failure:
                raise state.write_failure
            if not state.reply:
                state.rows = [row for row in state.rows if row['id'] != command.split()[-1]]
            return state.reply
        if state.read_failure:
            raise state.read_failure
        if command == 'show info':
            return state.info
        if command == 'show stat':
            return stats_csv()
        if command == 'show sess':
            if state.list_override is not None:
                return state.list_override
            return session_lines(state.rows)
        if command.startswith('show sess '):
            if state.detail_override is not None:
                return state.detail_override
            row = next((row for row in state.rows if row['id'] == command.split()[-1]), None)
            return session_detail(row, state.uid) if row else 'Session not found.\n'
        raise AssertionError(command)

    monkeypatch.setattr(haproxy_stats, 'execute_runtime_command', execute)
    monkeypatch.setattr(runtime, 'execute_runtime_command', execute)
    return state
