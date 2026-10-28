"""Stick-table wire responses with only the external TCP transport replaced."""
from types import SimpleNamespace

import pytest

from app.modules.config import runtime
from app.modules.db.db_model import Setting
from app.modules.service.stats import haproxy_stats
from tests.fixtures.haproxy_stats import INFO, stats_csv


def table_dump(name, table, *, entries=True):
    header = f"# table: {name}, type: {table['type']}, size:{table['size']}, used:{len(table['rows'])}\n"
    return header + ('\n'.join(table['rows']) + '\n' if entries else '')


@pytest.fixture
def tables_host(product, monkeypatch):
    state = SimpleNamespace(info=INFO, calls=[], writes=[], read_failure=None, write_failure=None,
                            reply='', override=None, tables={
        'clients': {'type': 'ip', 'size': 200000, 'rows': [
            '0x100: key=203.0.113.42 use=0 exp=30000 shard=0 conn_cur=0 http_req_rate(10000)=12 gpc0=0',
            '0x200: key=192.0.2.5 use=1 exp=29000 shard=1 conn_cur=1 http_req_rate(10000)=42 gpc0=2',
        ]},
        'peers/ipv6': {'type': 'ipv6', 'size': 100, 'rows': [
            '0x300: key=2001:db8::1 use=0 exp=2000 conn_cnt=5',
        ]},
        'tokens': {'type': 'string', 'size': 50, 'rows': [
            r'0x400: key=user\ name\=one;two\\three use=0 exp=1000 gpc0=1',
        ]},
    })
    Setting.update(value='1999').where(Setting.param == 'haproxy_sock_port', Setting.group_id == 1).execute()

    def execute(server, port, command):
        assert int(port) == 1999
        state.calls.append((server, command))
        if command.startswith('clear table '):
            state.writes.append((server, command))
            if state.write_failure:
                raise state.write_failure
            if state.reply:
                return state.reply
            prefix, _, key = command.partition(' key ')
            current = state.tables[prefix.removeprefix('clear table ')]
            # Match the known wire encodings, independently of the production parser.
            keys = {'203.0.113.42': '0x100:', '192.0.2.5': '0x200:', '2001:db8::1': '0x300:',
                    r'user\ name=one\;two\\three': '0x400:'}
            if key:
                matching = [line for line in current['rows'] if line.startswith(keys[key])]
                if any(' use=1 ' in line for line in matching):
                    return 'Entry currently in use, cannot remove\n'
                current['rows'] = [line for line in current['rows'] if line not in matching]
            else:
                current['rows'] = [line for line in current['rows'] if ' use=1 ' in line]
            return ''
        if state.read_failure:
            raise state.read_failure
        if command == 'show info':
            return state.info
        if command == 'show stat':
            return stats_csv()
        if state.override is not None:
            return state.override
        if command == 'show table':
            return ''.join(table_dump(name, table, entries=False) for name, table in state.tables.items())
        if command.startswith('show table '):
            name = command.removeprefix('show table ')
            return table_dump(name, state.tables[name]) if name in state.tables else 'No such table\n'
        raise AssertionError(command)

    monkeypatch.setattr(haproxy_stats, 'execute_runtime_command', execute)
    monkeypatch.setattr(runtime, 'execute_runtime_command', execute)
    return state
