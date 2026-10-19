from datetime import datetime, timezone

import pytest

from app.modules.roxywi import log_follow, log_query, log_snapshot
from app.scripts import log_reader


def audit_record(service='nginx', stamp='23/Sep/2026:03:05:00 +0300', uri='/blocked'):
    boundary = '---nginx---' if service == 'nginx' else '--haproxy-'
    if service == 'haproxy' and '.' not in stamp:
        stamp = stamp.replace(' +', '.123456 +')
    version = '1.1' if service == 'haproxy' else 'HTTP/1.1'
    return (f'{boundary}A--\n[{stamp}] id 127.0.0.1 12345 127.0.0.1 80\n'
            f'{boundary}B--\nGET {uri} {version}\nHost: localhost\n'
            f'{boundary}E--\n<html>response body</html>\n'
            f'{boundary}H--\nMessage: Access denied [id "920280"] [msg "test rule"]\n'
            f'{boundary}Z--\n')


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('central', [False, True])
def test_audit_sources_always_use_selected_host(monkeypatch, service, central):
    monkeypatch.setattr(log_snapshot.sql, 'get_setting', lambda _: '1' if central else '0')
    assert log_snapshot.remote_source(service, '192.0.2.10', 'audit.log', True) == (
        '192.0.2.10', f'/var/log/{service}/waf/audit.log')


def test_nginx_events_default_to_error_log_and_respect_settings(monkeypatch):
    settings = {'syslog_server_enable': '0', 'nginx_path_logs': '/custom/nginx'}
    monkeypatch.setattr(log_snapshot.sql, 'get_setting', settings.__getitem__)
    assert log_snapshot.remote_source('nginx', '192.0.2.10', None, True) == ('192.0.2.10', '/custom/nginx/error.log')
    settings.update(syslog_server_enable='1', syslog_server='192.0.2.20')
    assert log_snapshot.remote_source('nginx', '192.0.2.10', 'error.log', True) == (
        '192.0.2.20', '/var/log/192.0.2.10/syslog.log')


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('search,exclude,count', [('920280', '', 1), ('response body', '', 1), ('absent', '', 0), ('', 'localhost', 0)])
def test_audit_snapshot_filters_whole_transactions_and_keeps_raw(monkeypatch, tmp_path, service, search, exclude, count):
    raw = audit_record(service)
    path = tmp_path / 'audit.log'
    path.write_bytes(raw.encode())
    def remote(host, filename, position, limit, record_format):
        assert (host, filename, record_format) == ('192.0.2.10', f'/var/log/{service}/waf/audit.log', 'modsecurity')
        return log_reader.read_log(str(path), position, limit, record_format)
    monkeypatch.setattr(log_follow, 'remote_read', remote)
    query = log_query.LogQuery({'from': '2026-09-23T00:00Z', 'to': '2026-09-23T00:10Z', 'search': search, 'exclude': exclude})
    result = log_follow.snapshot(service, '192.0.2.10', 'audit.log', True, query)
    assert len(result['entries']) == count
    assert result['unparsed'] == 0
    if count:
        entry = result['entries'][0]
        assert entry['timestamp'] == '2026-09-23T00:05:00' + ('.123456' if service == 'haproxy' else '') + '+00:00'
        assert entry['text'] == raw.rstrip('\n')
        assert 'GET /blocked' in entry['message'] and '920280' in entry['message']
        assert '<html>' not in entry['message']


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_audit_live_partial_write_rotation_and_cursor_scope(app, monkeypatch, tmp_path, service):
    path = tmp_path / 'audit.log'
    path.write_bytes(b'')
    calls = []
    def remote(host, filename, position, limit, record_format):
        calls.append(filename)
        return log_reader.read_log(str(path), position, limit, record_format)
    monkeypatch.setattr(log_follow, 'remote_read', remote)
    stamp = datetime.now(timezone.utc).strftime('%d/%b/%Y:%H:%M:%S.%f %z')
    raw = audit_record(service, stamp).encode()
    def read(cursor=None, file='audit.log'):
        return log_follow.follow(service, '192.0.2.10', file, True,
                                 log_query.LogQuery({'relative': 3600}), cursor=cursor, scope=[1, 1, 1])
    with app.app_context():
        first = read()
        path.write_bytes(raw[:-6])
        second = read(first['cursor'])
        assert second['entries'] == [] and not second['more']
        with path.open('ab') as stream:
            stream.write(raw[-6:])
        third = read(second['cursor'])
        assert len(third['entries']) == 1
        assert read(third['cursor'])['entries'] == []
        # Immediate compression can remove the rotated copy; the active inode
        # must still reset correctly and deliver a new complete transaction.
        path.write_bytes(audit_record(service, stamp, '/new-after-rotation').encode())
        fourth = read(third['cursor'])
        assert fourth['reset']
        assert '/new-after-rotation' in fourth['entries'][0]['text']
        before = len(calls)
        monkeypatch.setattr(log_snapshot.sql, 'get_setting', lambda key: '0' if key == 'syslog_server_enable' else '/var/log/nginx')
        with pytest.raises(ValueError, match='changed'):
            read(fourth['cursor'], 'error.log' if service == 'nginx' else 'waf.log')
        assert len(calls) == before
