import pytest

from app.modules.service import haproxy_stats as stats
from tests.fixtures.haproxy_stats import INFO, FIELDS, ROWS, stats_csv


def test_csv_uses_field_names_and_preserves_unknown_and_empty_fields():
    fields = ['future_counter', *reversed(FIELDS)]
    data = stats.parse_stats(stats_csv([{**ROWS[1], 'pxname': 'quoted,backend',
                                       'future_counter': 'new value', 'last_chk': 'line one\nline two'}], fields))
    assert data[0]['proxy'] == 'quoted,backend'
    assert data[0]['metrics']['future_counter'] == 'new value'
    assert data[0]['metrics']['last_chk'] == 'line one\nline two'
    assert data[0]['metrics']['qcur'] == 0
    assert data[0]['metrics']['econ'] is None
    assert data[0]['kind'] == 'server'
    assert data[0]['metrics']['rtime'] == 10


@pytest.mark.parametrize('status,state', [
    ('UP', 'up'), ('UP 1/3', 'up'), ('DOWN 1/2', 'down'), ('OPEN', 'up'), ('STOP', 'down'),
    ('MAINT (via backend/one)', 'maint'), ('MAINT (resolution)', 'maint'),
    ('DRAIN 1/3', 'drain'), ('NOLB', 'nolb'), ('no check', 'no_check'), ('future state', 'unknown'),
])
def test_runtime_states_keep_full_status(status, state):
    row = stats.parse_stats(stats_csv([{**ROWS[1], 'status': status}]))[0]
    assert row['state'] == state and row['status'] == status


def test_minimal_older_csv_and_empty_proxy_set():
    assert stats.parse_stats('# pxname,svname,type\nproxy,server,2\n')[0]['metrics'].get('req_rate') is None
    assert stats.parse_stats(stats_csv([])) == []


@pytest.mark.parametrize('response', [
    '', 'Permission denied\n', 'Unknown command\n', '# invalid,header\n',
    '# pxname,svname,type\nproxy,one\n', '# pxname,svname,type\nproxy,one,2,unexpected\n',
    '# pxname,svname,type\n,one,2\n', '# pxname,svname,type,type\nproxy,one,2,2\n',
    '# pxname,svname,type\n"unterminated,one,2\n', stats_csv([ROWS[1], ROWS[1]]),
    stats_csv([{**ROWS[1], 'scur': 'not-a-number'}]),
])
def test_invalid_or_truncated_stats_are_not_empty_success(response):
    with pytest.raises(stats.StatsError, match='invalid_response'):
        stats.parse_stats(response)


@pytest.mark.parametrize('response', ['', 'Permission denied', 'Pid: 1\n', INFO + 'Pid: 200\n', INFO.replace('3600', 'bad')])
def test_invalid_info_is_rejected(response):
    with pytest.raises(stats.StatsError, match='invalid_response'):
        stats.parse_info(response)


def test_snapshot_summary_does_not_double_count_proxy_totals(monkeypatch):
    calls = []
    def execute(server, port, command):
        calls.append((server, port, command))
        return stats_csv() if command == 'show stat' else INFO
    monkeypatch.setattr(stats, 'execute_runtime_command', execute)
    data = stats.collect_stats('::1', 1999)
    assert [call[2] for call in calls] == ['show info', 'show stat', 'show info']
    assert data['info']['CurrConns'] == 7
    assert data['summary'] == dict(frontends=1, backends=1, servers=3, down=1, maint=0, drain=0)
    assert data['collected_at'].endswith('Z')
    assert data['rows'][4]['metrics']['hrsp_2xx'] is None


@pytest.mark.parametrize('new_info', [INFO.replace('Pid: 100', 'Pid: 101'), INFO.replace('3600', '1')])
def test_reload_during_collection_rejects_mixed_snapshot(monkeypatch, new_info):
    responses = iter([INFO, stats_csv(), new_info])
    monkeypatch.setattr(stats, 'execute_runtime_command', lambda *a: next(responses))
    with pytest.raises(stats.StatsError, match='process_changed'):
        stats.collect_stats('localhost', 1999)


def test_stats_from_different_process_are_rejected(monkeypatch):
    responses = iter([INFO, stats_csv([{**ROWS[1], 'pid': 2}]), INFO])
    monkeypatch.setattr(stats, 'execute_runtime_command', lambda *a: next(responses))
    with pytest.raises(stats.StatsError, match='process_changed'):
        stats.collect_stats('localhost', 1999)


def test_socket_permission_failure_is_distinct_from_malformed_data(monkeypatch):
    monkeypatch.setattr(stats, 'execute_runtime_command', lambda *a: 'Permission denied\n')
    with pytest.raises(stats.StatsError, match='runtime_permissions'):
        stats.collect_stats('localhost', 1999)


@pytest.mark.parametrize('error,code,status', [
    (ConnectionRefusedError('secret'), 'runtime_unavailable', 503),
    (TimeoutError('secret'), 'runtime_timeout', 504),
    (RuntimeError('secret'), 'response_too_large', 502),
])
def test_transport_failure_has_safe_error_code(monkeypatch, error, code, status):
    def execute(*args):
        raise error
    monkeypatch.setattr(stats, 'execute_runtime_command', execute)
    with pytest.raises(stats.StatsError) as caught:
        stats.collect_stats('localhost', 1999)
    assert caught.value.code == code and caught.value.status == status
    assert 'secret' not in str(caught.value)
