"""Wire parsing and request validation for HAProxy session snapshots."""
import pytest
from pydantic import ValidationError

from app.modules.roxywi.class_models import HaproxyStatsSessionQuery, HaproxyStatsSessionDelete
from app.modules.service.stats import haproxy_stats, haproxy_stats_sessions as sessions
from tests.fixtures.haproxy_sessions import ROWS, session_lines
from tests.fixtures.haproxy_stats import INFO


def test_named_fields_ipv6_unix_and_unknown_fields():
    rows = sessions.parse_sessions(session_lines([
        dict(reversed(list(ROWS[1].items()))),
        dict(id='0xabc', proto='unix', src='unix:4', fe='local', be='<NONE>', srv='<none>', future='value'),
    ]))
    assert rows[0]['fields']['src'] == '2001:db8::20:60421'
    assert rows[0]['fields']['be'] == 'web'
    assert rows[1]['fields']['src'] == 'unix:4'
    assert rows[1]['fields']['future'] == 'value'
    assert 'rq[' in rows[1]['raw']
    assert sessions.parse_sessions('\n') == []


def test_identity_ignores_counters_but_changes_with_recycled_stream():
    original = sessions.parse_sessions(session_lines([ROWS[0]]))[0]
    later = sessions.parse_sessions(session_lines([{**ROWS[0], 'age': '3m', 'calls': '99'}]))[0]
    recycled = sessions.parse_sessions(session_lines([{**ROWS[0], 'epoch': '0x3'}]))[0]
    assert original['key'] == later['key']
    assert original['key'] != recycled['key']


@pytest.mark.parametrize('value', ['Unknown command\n', '0x1: src=x', '0x1: proto=',
    '0x1: proto=tcpv4\ntruncated', '0x1: proto=tcpv4\n0x1: proto=tcpv6'])
def test_malformed_and_duplicate_sessions_are_rejected(value):
    with pytest.raises(haproxy_stats.StatsError, match='invalid_response'):
        sessions.parse_sessions(value)


@pytest.mark.parametrize('info', [INFO.replace('Pid: 100', 'Pid: 200'), INFO.replace('3600', '1')])
def test_reload_during_session_collection_is_rejected(monkeypatch, info):
    replies = iter([INFO, info])
    monkeypatch.setattr(haproxy_stats, 'execute_runtime_command', lambda *args: next(replies))
    monkeypatch.setattr(sessions.runtime, 'select_session', lambda *args, **kwargs: session_lines())
    with pytest.raises(haproxy_stats.StatsError, match='process_changed'):
        sessions.collect_sessions('localhost', 1999)


def test_query_converts_http_parameters_but_write_model_is_strict():
    body = dict(session_id='0x123', row_key='a' * 64, pid='100', uptime='3600')
    parsed = HaproxyStatsSessionQuery.model_validate(body).model_dump()
    assert parsed['pid'] == 100
    with pytest.raises(ValidationError):
        HaproxyStatsSessionDelete.model_validate({**body, 'revision': 'b' * 64})
    assert HaproxyStatsSessionDelete.model_validate({**parsed, 'revision': 'b' * 64}).pid == 100


@pytest.mark.parametrize('change', [
    {'session_id': 'all'}, {'session_id': '0x1\nshow env'}, {'session_id': '0x1;show env'},
    {'session_id': '0x' + 'f' * 17}, {'pid': 0}, {'uptime': -1}, {'row_key': 'bad'},
    {'revision': None}, {'unexpected': True},
])
def test_invalid_write_models(change):
    body = dict(session_id='0x123', row_key='a' * 64, pid=100, uptime=3600, revision='b' * 64)
    with pytest.raises(ValidationError):
        HaproxyStatsSessionDelete.model_validate({**body, **change})
