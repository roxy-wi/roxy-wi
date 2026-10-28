import pytest
from pydantic import ValidationError

from app.modules.config.runtime import escape_runtime_argument
from app.modules.roxywi.class_models import HaproxyStatsTableChange, HaproxyStatsTableQuery
from app.modules.service.stats.haproxy_stats import StatsError
from app.modules.service.stats.haproxy_stats_tables import parse_tables
from app.modules.service.stats import haproxy_stats, haproxy_stats_tables
from tests.fixtures.haproxy_stats import INFO


def test_named_counters_ipv6_and_capacity():
    table = parse_tables('# table: peers/v6, type: ipv6, size:200000, used:1\n'
                         '0x123: key=2001:db8::1 use=0 exp=32000 shard=1 http_req_rate(30000)=7 gpc0=2\n')[0]
    assert table['size'] == 200000
    row = table['rows'][0]
    assert row['key'] == '2001:db8::1'
    assert row['fields'] == {'use': '0', 'exp': '32000', 'shard': '1', 'http_req_rate(30000)': '7', 'gpc0': '2'}
    assert row['deletable'] is True
    assert parse_tables('') == []


@pytest.mark.parametrize('raw,decoded,deletable', [
    (r'user\ name\=one;two\\three', 'user name=one;two\\three', True),
    (r'\xD0\xBA\xD0\xBB\xD1\x8E\xD1\x87', 'ключ', True),
    (r'line\ncommand', r'line\ncommand', False),
    (r'\xFF', r'\xFF', False),
    (r'\q', r'\q', False),
    ('', '', False),
])
def test_string_keys_round_trip_or_remain_read_only(raw, decoded, deletable):
    row = parse_tables(f'# table: strings, type: string, size:10, used:1\n0x1: key={raw} use=0 exp=1\n')[0]['rows'][0]
    assert row['key'] == decoded
    assert row['deletable'] is deletable


def test_binary_keys_are_readable_and_cli_escaping_does_not_create_commands():
    row = parse_tables('# table: binary, type: binary, size:10, used:1\n0x1: key=00ff01 use=0 exp=1\n')[0]['rows'][0]
    assert not row['deletable']
    assert escape_runtime_argument('user name=one;two\\three') == r'user\ name=one\;two\\three'


@pytest.mark.parametrize('response,code', [
    ('Permission denied\n', 'runtime_permissions'),
    ('# table: clients, type: ip, size:10, used:1\n# contents not dumped due to insufficient privileges\n', 'runtime_permissions'),
    ('No such table\n', 'table_gone'),
    ('Unexpected reply', 'invalid_response'),
    ('0x1: key=1 use=0 exp=1', 'invalid_response'),
    ('# table: clients, type: ip, size:10, used:1\n0x1: key=1 exp=1', 'invalid_response'),
])
def test_unknown_and_error_responses_are_not_empty_success(response, code):
    with pytest.raises(StatsError) as error:
        parse_tables(response)
    assert error.value.code == code


@pytest.mark.parametrize('table', ['x;show env', 'x\nshow env', 'x\r', 'x\x00', 'a b', '', 'x' * 257])
def test_pydantic_rejects_unsafe_table_names(table):
    with pytest.raises(ValidationError):
        HaproxyStatsTableQuery(table=table)


@pytest.mark.parametrize('changes', [
    {'action': 'delete'}, {'action': 'clear', 'row_key': 'a' * 64}, {'pid': True}, {'uptime': -1},
    {'action': 'set'}, {'key': 'anything'}, {'revision': 'wrong'},
])
def test_pydantic_rejects_invalid_operations(changes):
    body = dict(action='clear', table='clients', revision='a' * 64, pid=100, uptime=10)
    with pytest.raises(ValidationError):
        HaproxyStatsTableChange.model_validate(body | changes)


def test_restart_during_read_rejects_mixed_snapshot(monkeypatch):
    responses = iter([INFO, INFO.replace('Pid: 100', 'Pid: 200')])
    monkeypatch.setattr(haproxy_stats, 'execute_runtime_command', lambda *args: next(responses))
    monkeypatch.setattr(haproxy_stats_tables.runtime, 'get_all_stick_table', lambda *args, **kwargs: '')
    with pytest.raises(StatsError, match='process_changed'):
        haproxy_stats_tables.collect_tables('localhost', 1999)
