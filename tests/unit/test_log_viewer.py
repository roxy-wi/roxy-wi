import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import g
from flask_jwt_extended import create_access_token, decode_token

from app.modules.roxywi import auth, common, log_follow, log_query, log_snapshot, log_store, logger
from app.routes.logs import routes

NOW = datetime(2026, 9, 23, 0, 15, tzinfo=timezone.utc)


def event(message='same', timestamp='2026-09-23T00:00:00Z', group=2):
    return json.dumps(dict(timestamp=timestamp, message=message, group_id=group)) + '\n'


@pytest.fixture
def journal(tmp_path, monkeypatch):
    monkeypatch.setenv('ROXYWI_LOG_STORE_ENABLED', '1')
    monkeypatch.setenv('ROXYWI_LOG_STORE_PATH', str(tmp_path))
    monkeypatch.setenv('ROXYWI_LOG_PATH', str(tmp_path / 'legacy'))
    return tmp_path


def query(**values):
    return log_query.LogQuery({'relative': 3600, **values}, now=NOW)


def read(app, q=None, **kwargs):
    with app.app_context():
        return log_query.read_logs('runtime', q or query(), **kwargs)


def test_tail_keeps_repeated_lines_and_waits_for_partial_record(app, journal):
    path = journal / 'rwi-web.log'
    path.write_text(event() * 3, encoding='utf-8')
    first = read(app, query(limit=2))
    assert len(first['entries']) == 2
    with path.open('a', encoding='utf-8') as stream:
        stream.write(event() * 2 + event('partial')[:-1])
    second = read(app, cursor=first['cursor'], q=query(limit=2))
    assert len(second['entries']) == 2
    third = read(app, cursor=second['cursor'], q=query(limit=2))
    assert third['entries'] == []
    with path.open('a', encoding='utf-8') as stream:
        stream.write('\n')
    fourth = read(app, cursor=third['cursor'], q=query(limit=2))
    assert 'partial' in fourth['entries'][0]['text']
    assert read(app, cursor=fourth['cursor'], q=query(limit=2))['entries'] == []


def test_cursor_survives_rotation_and_drains_backlog(app, journal):
    first_file = journal / 'rwi-old.log'
    first_file.write_text(event('before'), encoding='utf-8')
    first = read(app, query(limit=1))
    with first_file.open('a', encoding='utf-8') as stream:
        stream.write(event('during rotation'))
    (journal / 'rwi-new.log').write_text(event('after rotation') * 2, encoding='utf-8')
    found = []
    cursor = first['cursor']
    for _ in range(4):
        response = read(app, query(limit=1), cursor=cursor)
        cursor = response['cursor']
        found += [json.loads(item['text'])['message'] for item in response['entries']]
    assert found == ['during rotation', 'after rotation', 'after rotation']


def test_copytruncate_detected_even_if_replacement_is_longer(app, journal):
    path = journal / 'rwi-web.log'
    path.write_text(event('old'), encoding='utf-8')
    before = read(app)
    path.write_text(event('new' * 100), encoding='utf-8')
    after = read(app, cursor=before['cursor'])
    assert after['reset'] is True
    assert len(after['entries']) == 1


def test_oversized_line_does_not_pin_cursor_or_render_its_suffix(app, journal, monkeypatch):
    monkeypatch.setattr(log_query, 'MAX_LINE', 100)
    monkeypatch.setattr(log_query, 'CHUNK_BYTES', 200)
    path = journal / 'rwi-web.log'
    path.write_text('', encoding='utf-8')
    cursor = read(app)['cursor']
    path.write_text('x' * 500 + event('not a separate record') + event('ok'), encoding='utf-8')
    entries, limited = [], False
    for _ in range(5):
        response = read(app, cursor=cursor)
        cursor = response['cursor']
        entries += response['entries']
        limited |= response['limited']
    assert limited
    assert [json.loads(e['text'])['message'] for e in entries] == ['ok']


def test_paused_cursor_reports_removed_unread_segment(app, journal):
    path = journal / 'rwi-web.log'
    path.write_text('', encoding='utf-8')
    first = read(app, query(limit=1))
    path.write_text(event() * 3, encoding='utf-8')
    second = read(app, query(limit=1), cursor=first['cursor'])
    assert second['more']
    path.unlink()
    assert read(app, query(limit=1), cursor=second['cursor'])['reset']


def test_signed_cursor_bound_to_user_group_and_filters(app, journal):
    (journal / 'rwi-web.log').write_text(event(), encoding='utf-8')
    cursor = read(app, scope=[1, 2], group_id=2)['cursor']
    with pytest.raises(ValueError):
        read(app, scope=[2, 2], group_id=2, cursor=cursor)
    with pytest.raises(ValueError):
        read(app, query(search='other'), scope=[1, 2], cursor=cursor)
    with pytest.raises(ValueError):
        read(app, cursor=cursor + 'tampered')


def test_group_filter_uses_structured_id_not_message_or_group_name(app, journal):
    (journal / 'rwi-web.log').write_text(event('mine') + event('group: mine', group=3) + event(group=None)
                                        + 'Sep 23 00:00:00 group: mine\n', encoding='utf-8')
    result = read(app, group_id=2)
    assert len(result['entries']) == 1
    assert json.loads(result['entries'][0]['text'])['message'] == 'mine'
    assert result['unparsed'] == 0


def test_process_filter_respects_groups_and_binds_cursor(app, journal):
    records = [dict(timestamp=NOW.isoformat(), message='scheduler mentioned', process_role=role, group_id=group)
               for role, group in [('web', 2), ('scheduler', 2), ('scheduler', 3), ('operations', 2)]]
    (journal / 'rwi-mixed.log').write_text(''.join(json.dumps(record) + '\n' for record in records), encoding='utf-8')
    result = read(app, query(process='scheduler'), group_id=2)
    assert len(result['entries']) == 1
    assert json.loads(result['entries'][0]['text'])['process_role'] == 'scheduler'
    with pytest.raises(ValueError):
        read(app, query(process='web'), cursor=result['cursor'], group_id=2)
    with pytest.raises(ValueError):
        query(process='unknown')


@pytest.mark.parametrize('line', [
    event(timestamp='2026-09-22T23:30:00'),
    event(timestamp='2026-09-23T02:30:00+03:00'),
    '2026-09-22T23:30:00Z host event',
    '127.0.0.1 - - [23/Sep/2026:02:30:00 +0300] "GET /"',
    '2026/09/23 02:30:00 [error] example',
    'Sep 23 02:30:00 host event',
    '[Wed Sep 23 02:30:00.123456 2026] [error] example',
])
def test_time_range_crosses_midnight_and_understands_offsets(line):
    result, unknown = query(timezone='Europe/Moscow').entry(line)
    assert unknown is False
    assert result is not None
    assert result['timestamp'].startswith('2026-09-22T23:30:00')


def test_syslog_year_rollover_and_literal_search():
    q = log_query.LogQuery({'relative': 3600, 'search': '[.*]'}, now=datetime(2027, 1, 1, 0, 10, tzinfo=timezone.utc))
    assert q.entry('Dec 31 23:30:00 host [.*]')[0]['timestamp'].startswith('2026-12-31')
    assert q.entry('Dec 31 23:30:00 host other')[0] is None
    assert q.entry('Jan 01 00:11:00 host [.*]')[0] is None


def test_find_matches_decoded_unicode_and_preserves_literal_json_search():
    line = event('Ошибка [.*]')
    assert '\\u' in line
    assert query(search='Ошибка [.*]').entry(line)[0] is not None
    assert query(search=r'\u041e').entry(line)[0] is not None
    assert query(exclude='Ошибка').entry(line)[0] is None


def test_leap_day_syslog():
    q = log_query.LogQuery({'relative': 3600}, now=datetime(2028, 2, 29, 12, 10, tzinfo=timezone.utc))
    assert q.entry('Feb 29 12:00:00 host event')[0]['timestamp'].startswith('2028-02-29')


@pytest.mark.parametrize('values', [
    {'limit': 0}, {'limit': 1001}, {'relative': -1}, {'relative': 32 * 86400},
    {'timezone': 'Mars'}, {'relative': 0, 'from': '2026-09-22', 'to': '2026-09-23'},
    {'relative': 0, 'from': '2026-09-23T00:00:00Z', 'to': '2026-09-22T00:00:00Z'},
    {'search': 'x' * 257},
])
def test_invalid_queries(values):
    with pytest.raises(ValueError):
        query(**values)


def test_bound_and_unknown_timestamps_are_reported(app, journal, monkeypatch):
    monkeypatch.setattr(log_query, 'CHUNK_BYTES', 300)
    (journal / 'rwi-web.log').write_text(event() * 20 + 'unknown timestamp\n', encoding='utf-8')
    result = read(app)
    assert result['limited'] is True
    assert len(result['entries']) < 20
    assert result['unparsed'] == 1


def test_no_arbitrary_path_or_symlink_read(app, journal):
    with app.app_context(), pytest.raises(ValueError):
        log_query.read_logs('../secrets', query())
    outside = journal / 'secret'
    outside.write_text(event('secret'), encoding='utf-8')
    try:
        (journal / 'rwi-link.log').symlink_to(outside)
    except OSError:
        pytest.skip('Symlinks require Windows privileges')
    assert read(app)['entries'] == []


def test_journal_rotation_cleanup_and_process_isolation(journal, monkeypatch):
    monkeypatch.setattr(log_store, 'SEGMENT_BYTES', 1)
    expired = journal / 'rwi-expired.log'
    expired.write_text('old')
    os.utime(expired, (0, 0))
    unrelated = journal / 'keep.txt'
    unrelated.write_text('keep')
    handler = log_store.JournalHandler(journal)
    record = logging.LogRecord('test', logging.INFO, '', 1, 'test', (), None)
    handler.emit(record)
    first = handler.segment
    handler.emit(record)
    assert handler.segment != first
    second = log_store.JournalHandler(journal)
    second.emit(record)
    assert second.segment != handler.segment
    assert len(list(journal.glob('rwi-*.log'))) == 3
    assert not expired.exists()
    assert unrelated.exists()


def test_formatter_adds_utc_role_and_server_derived_group(app, monkeypatch):
    monkeypatch.setenv('ROXYWI_PROCESS_ROLE', 'operations')
    record = logging.LogRecord('test', logging.INFO, '', 1, 'test', (), None)
    record._group_id = 999
    with app.test_request_context('/'):
        g.user_params = {'group_id': 2}
        data = json.loads(logger.StructuredLogFormatter().format(record))
    assert data['group_id'] == 2
    assert data['process_role'] == 'operations'
    assert data['timestamp'].endswith('Z')


@pytest.fixture
def actor(app, monkeypatch):
    params = dict(user_id=1, user='test', role=2, group_id=2, lang='en', servers=[], user_services=[])
    monkeypatch.setattr(common, 'get_users_params', lambda **_: dict(params))
    monkeypatch.setattr(auth, 'is_admin', lambda level=1, **_: params['role'] <= level)
    monkeypatch.setattr(common, 'check_user_group_for_flask', lambda: True)
    monkeypatch.setattr(common.user_sql, 'get_user_id', lambda *a, **kw: SimpleNamespace(
        user_id=1, username='test', enabled=True, group_id=2))
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '2'})
    return params, {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}


def test_query_rbac_and_no_cache(client, actor, journal):
    (journal / 'rwi-web.log').write_text(event(timestamp=datetime.now(timezone.utc).isoformat()) +
                                        event(group=3, timestamp=datetime.now(timezone.utc).isoformat()), encoding='utf-8')
    url = '/logs/internal/query?relative=3600'
    assert client.get(url, headers={'Accept': 'application/json'}).status_code == 401
    response = client.get(url, headers=actor[1])
    assert response.status_code == 200
    assert len(response.json['entries']) == 1
    assert response.headers['Cache-Control'] == 'no-store'
    actor[0]['role'] = 4
    assert client.get(url, headers=actor[1]).status_code == 403


def test_overview_uses_shared_journal_latest_first_with_group_isolation(client, actor, journal):
    now = datetime.now(timezone.utc)
    (journal / 'rwi-web.log').write_text(''.join(
        event(str(index), timestamp=(now - timedelta(seconds=30 - index)).isoformat()) for index in range(12)
    ) + event('other group', group=3, timestamp=now.isoformat()) + event(
        'expired', timestamp=(now - timedelta(days=8)).isoformat()), encoding='utf-8')
    (journal / 'rwi-scheduler.log').write_text(event('scheduler', timestamp=now.isoformat()), encoding='utf-8')
    legacy = journal / 'legacy'
    legacy.mkdir()
    (legacy / 'roxy-wi.log').write_text(event('stale file', timestamp=now.isoformat()), encoding='utf-8')
    response = client.get('/overview/logs?limit=1000&group_id=3&source=roxy-wi.log', headers=actor[1])
    assert response.status_code == 200
    assert response.json['source'] == 'runtime'
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'cursor' not in response.json
    assert [json.loads(entry['text'])['message'] for entry in response.json['entries']] == [
        'scheduler', *map(str, range(11, 2, -1))]


def test_overview_searches_decoded_json_and_preserves_original_record(client, actor, journal):
    original = event('Ошибка <script>alert(1)</script>', timestamp=datetime.now(timezone.utc).isoformat())
    (journal / 'rwi-web.log').write_text(original, encoding='utf-8')
    response = client.get('/overview/logs', query_string={'search': 'Ошибка'}, headers=actor[1])
    assert response.status_code == 200
    assert response.json['entries'][0]['text'] == original.rstrip('\n')
    assert client.get('/overview/logs?search=missing', headers=actor[1]).json['entries'] == []
    assert client.get('/overview/logs', query_string={'search': 'x' * 257}, headers=actor[1]).status_code == 400


def test_overview_enforces_admin_and_current_group_before_reading(client, actor, monkeypatch):
    monkeypatch.setattr(log_query, 'sources', lambda: pytest.fail('Unauthorized request read log sources'))
    assert client.get('/overview/logs', headers={'Accept': 'application/json'}).status_code == 401
    actor[0]['role'] = 4
    assert client.get('/overview/logs', headers=actor[1]).status_code == 403
    actor[0]['role'] = 2
    monkeypatch.setattr(common, 'check_user_group_for_flask', lambda: False)
    assert client.get('/overview/logs', headers=actor[1]).status_code == 403


def test_overview_global_and_selected_group_scope(client, actor, journal):
    now = datetime.now(timezone.utc).isoformat()
    (journal / 'rwi-web.log').write_text(event('one', group=2, timestamp=now) +
                                        event('two', group=3, timestamp=now), encoding='utf-8')
    actor[0].update(role=1, group_id=1)
    assert len(client.get('/overview/logs', headers=actor[1]).json['entries']) == 2
    actor[0]['group_id'] = 2
    assert len(client.get('/overview/logs', headers=actor[1]).json['entries']) == 1
    actor[0].update(role=2, group_id=1)
    assert client.get('/overview/logs', headers=actor[1]).json['entries'] == []


def test_overview_file_fallback_empty_and_unreadable(client, actor, journal, monkeypatch):
    from app.routes.overview import routes as overview_routes
    monkeypatch.setenv('ROXYWI_LOG_STORE_ENABLED', '0')
    assert client.get('/overview/logs', headers=actor[1]).json['entries'] == []
    legacy = journal / 'legacy'
    legacy.mkdir()
    (legacy / 'roxy-wi.log').write_text(event('package log', timestamp=datetime.now(timezone.utc).isoformat()), encoding='utf-8')
    response = client.get('/overview/logs', headers=actor[1])
    assert response.json['source'] == 'roxy-wi.log'
    assert len(response.json['entries']) == 1
    def unreadable(*args, **kwargs):
        raise PermissionError('private filesystem path')
    monkeypatch.setattr(log_query, 'read_logs', unreadable)
    reported = []
    monkeypatch.setattr(overview_routes.logger, 'exception', lambda message: reported.append(message))
    response = client.get('/overview/logs', headers=actor[1])
    assert response.status_code == 503
    assert 'private filesystem path' not in response.get_data(as_text=True)
    assert reported == ['Cannot read Overview logs']


def test_overview_widget_renders_all_locales_with_shared_renderer(app):
    from flask import render_template_string
    with app.test_request_context('/'):
        for language in ('en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'):
            html = render_template_string(
                "{% import 'languages/' + language + '.html' as lang %}{% include 'include/overview_logs.html' %}",
                language=language)
            assert 'js/log-viewer.js' in html
            assert 'js/overview-logs.js' in html
            assert 'overview-log-search' in html
            assert 'href="/logs/internal?type=2"' in html


def test_post_cursor_and_cookie_csrf(client, app, actor, journal):
    now = datetime.now(timezone.utc).isoformat()
    for index in range(100):
        (journal / f'rwi-{index}.log').write_text(event(str(index), timestamp=now), encoding='utf-8')
    token = actor[1]['Authorization'].split()[1]
    with app.app_context():
        csrf = decode_token(token)['csrf']
    client.set_cookie('access_token_cookie', token)
    url = '/logs/internal/query'
    assert client.post(url, data={'relative': 3600}, headers={'Accept': 'application/json'}).status_code == 401
    headers = {'X-CSRF-TOKEN': csrf, 'Accept': 'application/json'}
    first = client.post(url, data={'relative': 3600}, headers=headers)
    assert first.status_code == 200
    # Carry potentially large multi-process cursors in POST bodies, not URLs.
    assert len(first.json['cursor']) > 4096
    second = client.post(url, data={'relative': 3600, 'cursor': first.json['cursor']}, headers=headers)
    assert second.status_code == 200
    assert second.json['entries'] == []


def test_containers_hide_and_reject_host_logs(client, actor, journal, monkeypatch):
    # Hide the global navigation: several unrelated Linux blueprints are not
    # registered by the lightweight test application.
    actor[0].update(role=1, group_id=1, user='')
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_MODE', 'compose')
    monkeypatch.setattr(common, 'return_user_subscription', lambda: {'user_status': 0, 'user_plan': 'free'})
    from app.modules.roxywi import error_handler
    monkeypatch.setattr(error_handler, 'log_error', lambda exc, *a, **kw: pytest.fail(str(exc)))
    page = client.get('/logs/internal', headers=actor[1])
    assert page.status_code == 200, page.get_data(as_text=True)
    assert b'fail2ban.log' not in page.data
    assert b'log-time-picker' in page.data
    assert b'time_range_out_hour' not in page.data
    response = client.get('/logs/internal/query?relative=3600&source=fail2ban.log', headers=actor[1])
    assert response.status_code == 403


def test_internal_source_selector_only_lists_internal_logs(client, actor, journal, monkeypatch):
    actor[0].update(role=2, user='', user_services=['1', '2', '3', '4'])
    monkeypatch.setattr(common, 'return_user_subscription', lambda: {'user_status': 0, 'user_plan': 'free'})
    page = client.get('/logs/internal?type=2', headers=actor[1])
    assert page.status_code == 200
    assert b'data-process="scheduler"' in page.data
    assert b'data-process="operations"' in page.data
    assert b'id="log-source"' in page.data
    assert b'data-url=' not in page.data
    assert b'value="service:' not in page.data
    assert b'id="serv"' not in page.data


@pytest.mark.parametrize('service,waf', [
    ('haproxy', None), ('nginx', None), ('apache', None), ('keepalived', None), ('haproxy', 'waf'),
])
def test_service_log_page_keeps_service_fixed(client, actor, monkeypatch, service, waf):
    actor[0].update(role=2, user='', user_services=['1', '2', '3', '4'])
    monkeypatch.setattr(common, 'return_user_subscription', lambda: {'user_status': 0, 'user_plan': 'free'})
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: True)
    monkeypatch.setattr(routes.service_sql, 'select_service', lambda slug: SimpleNamespace(service=slug, slug=slug))
    selected = []
    def servers(**kwargs):
        selected.append(kwargs['service'])
        return [('1', 'test-server', '192.0.2.10')]
    monkeypatch.setattr(common, 'get_dick_permit', servers)
    page = client.get(f'/logs/{service}' + (f'/{waf}' if waf else ''), headers=actor[1])
    assert page.status_code == 200
    assert selected == [service]
    assert f'<input type="hidden" id="service" value="{service}">'.encode() in page.data
    assert b'id="log-source"' not in page.data
    assert b'data-url=' not in page.data
    assert b'id="serv"' in page.data
    assert b'id="log-live"' in page.data
    assert (b'id="log_files"' in page.data) is (not waf)


def test_remote_file_list_returns_json_and_preserves_spaces(client, actor, monkeypatch):
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: True)
    monkeypatch.setattr(common, 'require_server_access', lambda _: SimpleNamespace(ip='192.0.2.10'))
    monkeypatch.setattr(routes.sql, 'get_setting', lambda key: '0' if key == 'syslog_server_enable' else '/var/log/nginx')
    calls = []
    def files(*args):
        calls.append(args)
        return 'access.log\nerror report.log\n'
    monkeypatch.setattr(routes.server_mod, 'get_remote_files', files)
    response = client.post('/logs/nginx/192.0.2.10', headers=actor[1])
    assert response.status_code == 200
    assert response.json == {'files': ['access.log', 'error report.log']}
    assert response.headers['Cache-Control'] == 'no-store'
    assert calls == [('192.0.2.10', '/var/log/nginx', 'log')]
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: False)
    assert client.post('/logs/nginx/192.0.2.10', headers=actor[1]).status_code == 403
    assert len(calls) == 1


def test_remote_file_list_uses_syslog_source(client, actor, monkeypatch):
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: True)
    monkeypatch.setattr(common, 'require_server_access', lambda _: SimpleNamespace(ip='192.0.2.10'))
    monkeypatch.setattr(routes.sql, 'get_setting', lambda _: '1')
    monkeypatch.setattr(routes.server_mod, 'get_remote_files', lambda *a: pytest.fail('Must not list files on managed host'))
    response = client.post('/logs/nginx/192.0.2.10', headers=actor[1])
    assert response.json == {'files': ['syslog.log']}


def test_remote_file_list_reports_failure(client, actor, monkeypatch):
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: True)
    monkeypatch.setattr(common, 'require_server_access', lambda _: SimpleNamespace(ip='192.0.2.10'))
    monkeypatch.setattr(routes.sql, 'get_setting', lambda _: '0')
    monkeypatch.setattr(routes.server_mod, 'get_remote_files', lambda *a: 'error: cannot connect')
    monkeypatch.setattr(routes.logger, 'exception', lambda *a, **kw: None)
    response = client.post('/logs/nginx/192.0.2.10', headers=actor[1])
    assert response.status_code == 503
    assert 'error' in response.json


def test_remote_access_checked_before_connection(client, actor, monkeypatch):
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: False)
    monkeypatch.setattr(log_snapshot, 'remote_snapshot', lambda *a: pytest.fail('Remote read without access'))
    assert client.get('/logs/query/haproxy?server=192.0.2.2&relative=3600', headers=actor[1]).status_code == 403


@pytest.fixture
def service_follow(monkeypatch, tmp_path):
    from app.scripts import log_reader
    path = tmp_path / 'access.log'
    path.write_text('', encoding='utf-8')
    calls = []
    monkeypatch.setattr(log_snapshot.sql, 'get_setting', lambda key: '0' if key == 'syslog_server_enable' else '/var/log/nginx')
    def remote(host, filename, position, limit):
        calls.append((host, filename, position))
        return log_reader.read_log(str(path), position, limit)
    monkeypatch.setattr(log_follow, 'remote_read', remote)
    return path, calls


def test_service_follow_signed_cursor_filters_and_backlog(app, service_follow):
    path, calls = service_follow
    timestamp = datetime.now(timezone.utc).isoformat()
    path.write_text(event('initial', timestamp), encoding='utf-8')
    with app.app_context():
        first = log_follow.follow('nginx', '192.0.2.10', 'access.log', False,
                                  query(limit=2, search='match'), scope=[1, 2, 2])
        assert first['entries'] == []
        with path.open('a', encoding='utf-8') as stream:
            stream.write(event('irrelevant', timestamp) * 2 + event('match', timestamp) * 3)
        found, cursor = [], first['cursor']
        for _ in range(3):
            result = log_follow.follow('nginx', '192.0.2.10', 'access.log', False,
                query(limit=2, search='match'), cursor=cursor, scope=[1, 2, 2])
            cursor = result['cursor']
            found.extend(result['entries'])
        assert len(found) == 3
        assert all(json.loads(entry['text'])['message'] == 'match' for entry in found)
        assert not result['more']
        assert all(host == '192.0.2.10' and file == '/var/log/nginx/access.log' for host, file, _ in calls)


@pytest.mark.parametrize('change', ['server', 'file', 'scope', 'search', 'service', 'waf', 'tamper'])
def test_service_cursor_cannot_cross_context_or_query(app, service_follow, change):
    _, calls = service_follow
    args = dict(service='nginx', server='192.0.2.10', filename='access.log', waf=False,
                query=query(), scope=[1, 2, 2])
    with app.app_context():
        first = log_follow.follow(**args)
        args['cursor'] = first['cursor']
        if change == 'server':
            args['server'] = '192.0.2.11'
        elif change == 'file':
            args['filename'] = 'error.log'
        elif change == 'scope':
            args['scope'] = [2, 2, 2]
        elif change == 'search':
            args['query'] = query(search='secret')
        elif change == 'service':
            args['service'] = 'haproxy'
        elif change == 'waf':
            args['waf'] = True
        else:
            args['cursor'] += 'invalid'
        with pytest.raises(ValueError):
            log_follow.follow(**args)
    assert len(calls) == 1


def test_service_follow_checks_access_on_every_poll(client, actor, service_follow, monkeypatch):
    path, calls = service_follow
    path.write_text(event('visible', datetime.now(timezone.utc).isoformat()), encoding='utf-8')
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: True)
    monkeypatch.setattr(common, 'require_server_access', lambda _: SimpleNamespace(ip='192.0.2.10'))
    data = dict(server='192.0.2.10', file='access.log', relative=3600, follow='1')
    first = client.post('/logs/query/nginx', data=data, headers=actor[1])
    assert first.status_code == 200
    assert len(first.json['entries']) == 1
    assert first.headers['Cache-Control'] == 'no-store'
    data['cursor'] = first.json['cursor']
    assert client.post('/logs/query/nginx', data=data, headers=actor[1]).json['entries'] == []
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: False)
    assert client.post('/logs/query/nginx', data=data, headers=actor[1]).status_code == 403
    assert len(calls) == 2
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: True)
    def deny(_):
        from flask import abort
        abort(403)
    monkeypatch.setattr(common, 'require_server_access', deny)
    assert client.post('/logs/query/nginx', data=data, headers=actor[1]).status_code == 403
    assert len(calls) == 2


def test_service_follow_retries_same_position_after_transport_failure(app, service_follow, monkeypatch):
    path, _ = service_follow
    args = ('nginx', '192.0.2.10', 'access.log', False)
    with app.app_context():
        first = log_follow.follow(*args, query())
        path.write_text(event('after retry', datetime.now(timezone.utc).isoformat()), encoding='utf-8')
        remote = log_follow.remote_read
        def fail(*args):
            raise OSError('Connection dropped')
        monkeypatch.setattr(log_follow, 'remote_read', fail)
        with pytest.raises(OSError):
            log_follow.follow(*args, query(), cursor=first['cursor'])
        monkeypatch.setattr(log_follow, 'remote_read', remote)
        retry = log_follow.follow(*args, query(), cursor=first['cursor'])
        assert len(retry['entries']) == 1
        assert log_follow.follow(*args, query(), cursor=retry['cursor'])['entries'] == []


def test_service_follow_accounts_for_ssh_latency(app, service_follow, monkeypatch):
    path, _ = service_follow
    old_query = query()  # Constructed before the remote record was written.
    path.write_text(event('during SSH', datetime.now(timezone.utc).isoformat()), encoding='utf-8')
    with app.app_context():
        result = log_follow.follow('nginx', '192.0.2.10', 'access.log', False, old_query)
    assert len(result['entries']) == 1


@pytest.mark.parametrize('central,waf,host,path', [
    (False, False, '192.0.2.10', '/var/log/haproxy/access.log'),
    (True, False, '192.0.2.20', '/var/log/192.0.2.10/syslog.log'),
    (False, True, '192.0.2.10', '/var/log/waf.log'),
    (True, True, '192.0.2.10', '/var/log/waf.log'),
])
def test_service_follow_resolves_central_syslog_and_waf(app, monkeypatch, service_follow, central, waf, host, path):
    _, calls = service_follow
    settings = {'syslog_server_enable': '1' if central else '0', 'syslog_server': '192.0.2.20',
                'haproxy_path_logs': '/var/log/haproxy'}
    monkeypatch.setattr(log_snapshot.sql, 'get_setting', lambda key: settings[key])
    with app.app_context():
        log_follow.follow('haproxy', '192.0.2.10', 'access.log', waf, query())
    assert calls[0][:2] == (host, path)


def test_service_follow_relative_only_and_cursor_expiry(app, service_follow, monkeypatch):
    _, calls = service_follow
    args = ('nginx', '192.0.2.10', 'access.log', False)
    with app.app_context():
        with pytest.raises(ValueError, match='relative'):
            log_follow.follow(*args, query(relative=0, **{'from': '2026-09-23T00:00Z', 'to': '2026-09-23T01:00Z'}))
        assert calls == []
        from itsdangerous import TimestampSigner
        with monkeypatch.context() as scoped:
            scoped.setattr(TimestampSigner, 'get_timestamp', lambda _: 1)
            first = log_follow.follow(*args, query())
        with pytest.raises(ValueError, match='expired'):
            log_follow.follow(*args, query(), cursor=first['cursor'])
    assert len(calls) == 1


@pytest.mark.parametrize('mode', ['ok', 'bad_json', 'stderr', 'exit', 'oversize', 'connect_failure'])
def test_service_transport_bounds_errors_and_closes_resources(monkeypatch, mode):
    import io
    import shlex
    result = {'data': '', 'position': {'files': {}, 'active': None}, 'more': False, 'limited': False, 'reset': False}
    observed = {}
    class Channel:
        def shutdown_write(self):
            observed['stdin_shutdown'] = True
        def recv_exit_status(self):
            return 1 if mode == 'exit' else 0
    class Input(io.StringIO):
        channel = Channel()
        def close(self):
            observed['input'] = self.getvalue()
            super().close()
    class Output(io.BytesIO):
        channel = Channel()
    stdin = Input()
    stdout = Output(b'x' * 101 if mode == 'oversize' else b'not json' if mode == 'bad_json' else json.dumps(result).encode())
    stderr = Output(b'private diagnostic' if mode == 'stderr' else b'')
    class Connection:
        def __init__(self):
            self.ssh = self
        def __enter__(self):
            if mode == 'connect_failure':
                raise OSError('authentication failed')
            return self
        def __exit__(self, *args):
            self.close()
        def exec_command(self, command, timeout):
            observed['command'] = shlex.split(command)
            assert 0 < timeout < 15
            return stdin, stdout, stderr
        def close(self):
            observed['closed'] = True
    monkeypatch.setattr(log_follow.ssh_mod, 'ssh_connect', lambda *a, **kw: Connection())
    if mode == 'oversize':
        monkeypatch.setattr(log_follow, 'MAX_RESPONSE', 100)
    path = "/var/log/nginx/access '; $(whoami).log"
    if mode == 'ok':
        assert log_follow.remote_read('192.0.2.10', path, None, 100) == result
    else:
        with pytest.raises(OSError):
            log_follow.remote_read('192.0.2.10', path, None, 100)
    assert observed['closed']
    if mode != 'connect_failure':
        assert stdin.closed and stdout.closed and stderr.closed
        assert json.loads(observed['input'])['path'] == path
        assert observed['command'][:4] == ['sudo', '-n', 'python3', '-c']
        assert path not in observed['command'][4]


@pytest.mark.parametrize('path', [
    '/logs/internal/0/10', '/logs/apache_internal/fail2ban.log/10',
    '/logs/haproxy/192.0.2.1/10', '/logs/haproxy/waf/192.0.2.1/10',
])
def test_retired_log_ajax_routes_are_not_exposed(client, actor, path, monkeypatch):
    monkeypatch.setattr(log_snapshot.ssh_mod, 'ssh_connect', lambda *a, **kw: pytest.fail('Retired route opened SSH'))
    assert client.get(path, headers=actor[1]).status_code == 404


def test_remote_snapshot_uses_bounded_quoted_path(monkeypatch):
    calls = []
    class Stream:
        channel = SimpleNamespace(recv_exit_status=lambda: 0)
        def __init__(self, data): self.data = data
        def read(self, size): return self.data[:size]
        def close(self): pass
    class Connection:
        def __enter__(self): return SimpleNamespace(ssh=self)
        def __exit__(self, *_): pass
        def exec_command(self, command, **kwargs):
            calls.append(command)
            return Stream(b''), Stream(event().encode()), Stream(b'')
    monkeypatch.setattr(log_snapshot.ssh_mod, 'ssh_connect', lambda *a, **kw: Connection())
    monkeypatch.setattr(log_snapshot.sql, 'get_setting', lambda key: '0' if key == 'syslog_server_enable' else '/var/log/nginx')
    result = log_snapshot.remote_snapshot('nginx', '192.0.2.1', "access'$(id).log", False, query())
    assert len(result['entries']) == 1
    assert calls == ["sudo -n tail -c 4194304 -- '/var/log/nginx/access'\"'\"'$(id).log'"]
    with pytest.raises(ValueError):
        log_snapshot.remote_snapshot('nginx', '192.0.2.1', '../secret', False, query())


def test_js_follow_state_and_calendar_validation():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required')
    script = Path(__file__).parents[2] / 'app/static/js/log-viewer.js'
    harness = r'''
const assert = require('assert');
require(process.argv[1]);
const {Follower, parseDate, parseEntry, highlightParts, recordFields, createLogRow} = globalThis.RoxyLogViewer;
const raw = JSON.stringify({level:'WARN', process_role:'web', message:'<img src=x onerror=alert(1)> [.*] [.*]', request:{ip:'192.0.2.1'}});
const parsed = parseEntry({text:raw});
assert.equal(parsed.level, 'WARNING');
assert.equal(parsed.process, 'web');
assert.equal(parsed.message, '<img src=x onerror=alert(1)> [.*] [.*]');
const fragments = highlightParts(parsed.message, '[.*]');
assert.equal(fragments.filter(p=>p.match).length, 2);
assert.equal(fragments.map(p=>p.text).join(''), parsed.message);
assert.equal(highlightParts('<script>x</script>', 'script').filter(p=>p.match).length, 2);
assert.equal(highlightParts('Токен токен', 'токен').filter(p=>p.match).length, 1);
assert.deepEqual(highlightParts('text',''), [{text:'text',match:false}]);
assert.equal(parseEntry({text:'{invalid JSON'}).message, '{invalid JSON');
assert.equal(parseEntry({text:'{"level":{"toString":42},"message":"safe"}'}).level, '');
assert.equal(parseEntry({text:'Sep 23 00:00:00 host message'}).record, null);
assert(recordFields(parsed.record).some(([k,v])=>k==='request.ip'&&v==='192.0.2.1'));
let nested = {}; for(let i=0; i<10000; i++) nested = {child:nested};
assert(recordFields(nested).length <= 200);
assert.equal(recordFields(Object.fromEntries(Array.from({length:300},(_,i)=>[i,i]))).length,200);
// A small DOM sink harness rejects HTML interpretation, including in lazily opened details.
class Node {
  constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.events={};this.attributes={};}
  set innerHTML(value){throw new Error('Log data must never use an HTML sink');}
  set textContent(value){this.children=[];this.text=String(value);}
  get textContent(){return (this.text||'')+this.children.map(c=>c.textContent).join('');}
  append(...nodes){for(const node of nodes){assert(node instanceof Node);this.children.push(node);}}
  appendChild(node){this.append(node);return node;}
  addEventListener(name,fn){this.events[name]=fn;}
  setAttribute(name,value){this.attributes[name]=value;}
}
globalThis.document={createElement:tag=>new Node(tag),createTextNode:text=>{const node=new Node('#text');node.textContent=text;return node;}};
const row=createLogRow({text:raw,timestamp:'2026-09-23T00:00:00Z'},
  {search:'[.*]',utc:true,timezone:'UTC',source:'',labels:{fields:'Fields',raw:'Raw',details:'Details',match_fields:'Match in details'}});
row.open=true;row.events.toggle();
const nodes=[];const visit=node=>{nodes.push(node);node.children.forEach(visit);};visit(row);
assert.equal(nodes.filter(n=>n.tag==='img'||n.tag==='script').length,0);
assert(nodes.filter(n=>n.tag==='mark').length>=4);
assert(row.textContent.includes('<img src=x onerror=alert(1)>'));
assert(row.textContent.includes('request.ip'));
const dated=createLogRow({text:raw,timestamp:'2026-09-23T00:00:00Z'},
  {search:'',utc:true,timezone:'UTC',showDate:true,labels:{}});
assert(dated.children[0].children[0].textContent.startsWith('2026-09-23 00:00:00'));
delete globalThis.document;
globalThis.clearTimeout = function () {assert(!(this instanceof Follower), 'Browser timers need the window receiver');};
new Follower(() => {}, () => {}, () => {}).stop();
assert.equal(parseDate('2026-09-22', '23:30', true).toISOString(), '2026-09-22T23:30:00.000Z');
assert.throws(() => parseDate('2026-02-30', '12:00', true));
assert.throws(() => parseDate('2026-09-23', '25:00', true));
let calls = [], renders = [], timers = [], statuses = [];
const fetch = cursor => {
  const request = {cursor, done(fn){this.ok=fn; return this;}, fail(fn){this.bad=fn; return this;},
    always(fn){this.end=fn; return this;}, abort(){this.aborted=true;}};
  calls.push(request); return request;
};
const follower = new Follower(fetch, (data, initial) => renders.push({data, initial}),
  (...args) => statuses.push(args), (fn, delay) => {timers.push({fn, delay}); return timers.length;}, () => {});
follower.start(true, true);
assert.equal(calls.length, 1);
assert.equal(timers.length, 0);
calls[0].ok({cursor: 'one', entries: []}); calls[0].end();
assert.equal(timers[0].delay, 2000);
timers[0].fn();
assert.equal(calls[1].cursor, 'one');
follower.stop();
calls[1].ok({cursor: 'late', entries: []}); calls[1].end();
assert.equal(renders.length, 1); assert.equal(follower.cursor, 'one');
follower.start(true, false);
assert.equal(calls[2].cursor, 'one');
calls[2].bad({status: 503}, 'error'); calls[2].end();
timers.at(-1).fn();
calls[3].ok({cursor: 'two', more: true, entries: []}); calls[3].end();
assert.equal(timers.at(-1).delay, 250);
timers.at(-1).fn();
calls[4].bad({status: 401}, 'error'); calls[4].end();
assert.equal(follower.live, false);
'''
    subprocess.run([node, '-e', harness, str(script)], check=True, capture_output=True, text=True)
