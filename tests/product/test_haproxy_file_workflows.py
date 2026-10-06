from pathlib import Path
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.modules.config import config, common
from app.modules.db import add as add_sql
from app.modules.db.db_model import ConfigVersion, UserGroups, Setting, ServiceSetting
from app.modules.roxywi.class_models import HaproxyGlobalRequest
from app.modules.roxywi.exception import RoxywiResourceNotFound
from app.views.service.haproxy_section_views import HaproxySectionView


EXTRA = '/etc/haproxy/conf.d/site92.cfg'


def test_settings_save_waits_for_a_competing_database_writer(product_client, product, monkeypatch):
    # Perform the throttled login activity write before holding the database.
    assert product_client.get('/service/settings/haproxy/11').status_code == 200
    ready = threading.Event()
    release = threading.Event()

    def writer():
        with sqlite3.connect(product.db.database, timeout=5) as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute("UPDATE servers SET description='Concurrent worker' WHERE id=11")
            ready.set()
            assert release.wait(5), 'Settings request did not reach the write transaction'

    execute = product.db.execute_sql
    database_errors = []

    def observed_execute(sql, *args, **kwargs):
        if sql.startswith('BEGIN'):
            release.set()
        try:
            return execute(sql, *args, **kwargs)
        except Exception as exc:
            database_errors.append((sql[:80], str(exc)))
            raise

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(writer)
        assert ready.wait(5)
        monkeypatch.setattr(product.db, 'execute_sql', observed_execute)
        try:
            response = product_client.post('/service/settings/haproxy', data={
                'serverSettingsSave': '11', 'serverSettingsDockerized': '0',
                'serverSettingsRestart': '1', 'serverSettingsMultipleConfigs': '1'})
        finally:
            release.set()
        future.result(timeout=5)
    assert response.status_code == 200, (response.text, database_errors)
    assert {row.setting: row.value for row in ServiceSetting.select()} == {
        'dockerized': '0', 'restart': '1', 'multiple_config_files': '1'}


def test_settings_save_rolls_back_all_fields_on_failure(product_client, product, monkeypatch):
    from app.modules.db import service as service_sql
    for setting in ('dockerized', 'restart', 'multiple_config_files'):
        ServiceSetting.create(server_id=11, service='haproxy', setting=setting, value='0')
    save = service_sql.insert_or_update_service_setting

    def failing_save(server_id, service, setting, value):
        if setting == 'multiple_config_files':
            raise RuntimeError('Database write failed')
        return save(server_id, service, setting, value)

    monkeypatch.setattr(service_sql, 'insert_or_update_service_setting', failing_save)
    response = product_client.post('/service/settings/haproxy', data={
        'serverSettingsSave': '11', 'serverSettingsDockerized': '1',
        'serverSettingsRestart': '1', 'serverSettingsMultipleConfigs': '1'})
    assert response.status_code == 500
    assert all(row.value == '0' for row in ServiceSetting.select())


def test_multiple_files_setting_is_per_service_and_server(product_client, product):
    assert not Setting.select().where(Setting.param == 'haproxy_config_args').exists()
    response = product_client.post('/service/settings/haproxy', data={
        'serverSettingsSave': '11', 'serverSettingsDockerized': '0',
        'serverSettingsRestart': '0', 'serverSettingsMultipleConfigs': '1'})
    assert response.status_code == 200, response.text
    row = ServiceSetting.get(ServiceSetting.setting == 'multiple_config_files')
    assert row.server_id == 11 and row.service == 'haproxy' and row.value == '1'
    response = product_client.get('/service/settings/haproxy/11')
    assert 'haproxy_multiple_config_files' in response.text and 'checked' in response.text
    response = product_client.post('/service/settings/haproxy', data={
        'serverSettingsSave': '11', 'serverSettingsDockerized': '0',
        'serverSettingsRestart': '0', 'serverSettingsMultipleConfigs': 'invalid'})
    assert response.status_code == 400
    assert ServiceSetting.get(ServiceSetting.setting == 'multiple_config_files').value == '1'
    # Older clients do not send the new checkbox and must preserve its value.
    response = product_client.post('/service/settings/haproxy', data={
        'serverSettingsSave': '11', 'serverSettingsDockerized': '0', 'serverSettingsRestart': '1'})
    assert response.status_code == 200
    assert ServiceSetting.get(ServiceSetting.setting == 'multiple_config_files').value == '1'


@pytest.mark.parametrize('payload', ['{}', '{"state":"ready"}', '{"state":"ready","code":"ready",'
                                    '"verified_running":true,"sources":[{}],"files":[]}'])
def test_incomplete_remote_discovery_shows_diagnostic_instead_of_server_error(product_client, product, monkeypatch, payload):
    from app.modules.server import server
    monkeypatch.setattr(server, 'ssh_command', lambda *a, **kw: payload)
    response = product_client.get('/service/settings/haproxy/11/sources')
    assert response.status_code == 200, response.text
    assert 'haproxy-sources-retry' in response.text
    assert '<pre>' not in response.text


def test_service_sources_and_settings_require_server_access(product_client, product, monkeypatch):
    UserGroups.update(user_role_id=2).where(UserGroups.user_id == product.admin.user_id).execute()
    from app.modules.config import haproxy_files
    monkeypatch.setattr(haproxy_files, 'discover_sources', lambda *a, **kw: pytest.fail('Unauthorized inspection'))
    assert product_client.get('/service/settings/haproxy/22/sources').status_code in (403, 404)
    assert product_client.get('/service/settings/haproxy/22').status_code in (403, 404)
    assert product_client.post('/service/settings/haproxy', data={
        'serverSettingsSave': '22', 'serverSettingsDockerized': '0',
        'serverSettingsRestart': '0', 'serverSettingsMultipleConfigs': '1'}).status_code in (403, 404)
    assert not ServiceSetting.select().exists()


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('state,code', [('single', 'not_configured'), ('error', 'permission_denied'), ('ready', 'ready')])
def test_sources_panel_localizes_setup_and_access_errors(product_client, product, monkeypatch, locale, state, code):
    from app.modules.config import haproxy_files
    monkeypatch.setattr(haproxy_files, 'discover_sources', lambda *a, **kw: {
        'state': state, 'code': code, 'sources': [], 'files': [], 'mode': 'systemd',
        'verified_running': False, 'example': '-f /etc/haproxy/haproxy.cfg -f /etc/haproxy/conf.d'})
    product_client.set_cookie('lang', locale)
    response = product_client.get('/service/settings/haproxy/11/sources')
    assert response.status_code == 200, response.text
    assert 'haproxy-sources-retry' in response.text
    assert ('systemctl daemon-reload' in response.text) == (state == 'single')
    assert ('class="haproxy-sources-hint"' in response.text) == (state == 'single')
    assert 'Undefined' not in response.text


def test_file_listing_retains_server_authorization(product_client, product, monkeypatch):
    UserGroups.update(user_role_id=2).where(UserGroups.user_id == product.admin.user_id).execute()
    calls = []
    monkeypatch.setattr(config, 'list_config_files', lambda server, service: calls.append(server) or [EXTRA])
    response = product_client.get('/config/haproxy/11/files')
    assert response.status_code == 200 and response.json['data'] == [EXTRA]
    assert product_client.get('/config/haproxy/22/files').status_code == 403
    assert calls == [product.server.ip]


def test_form_api_never_uses_main_file_metadata_for_another_file(product_client, product, monkeypatch):
    add_sql.insert_or_update_new_section(11, 'global', 'global', HaproxyGlobalRequest(daemon=True))
    path = '/add/haproxy/11/section/global'
    assert product_client.get(path, query_string={'file_path': EXTRA}).status_code == 404
    add_sql.insert_or_update_new_section(11, 'global', 'global', HaproxyGlobalRequest(daemon=False), config_path=EXTRA)
    response = product_client.get(path, query_string={'file_path': EXTRA})
    assert response.status_code == 200 and response.json['config']['daemon'] is False
    monkeypatch.setattr(HaproxySectionView, '_edit_config', staticmethod(lambda *args, **kwargs: 'Configuration file is valid'))
    response = product_client.put(path, query_string={'file_path': EXTRA}, json={'daemon': True})
    assert response.status_code == 201, response.json
    assert add_sql.get_section(11, 'global', 'global', config_path=EXTRA).config['daemon'] is True
    assert add_sql.get_section(11, 'global', 'global').config['daemon'] is True
    with pytest.raises(RoxywiResourceNotFound):
        add_sql.get_section(11, 'global', 'global', config_path='/etc/haproxy/third.cfg')


def test_saved_version_applies_to_its_recorded_haproxy_file(product_client, product, monkeypatch):
    saved = Path(common.generate_config_path('haproxy', product.server.ip))
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text('backend saved\n', encoding='utf-8')
    ConfigVersion.create(server_id=11, user_id=product.admin.user_id, service='haproxy',
                         local_path=str(saved.resolve()), remote_path=EXTRA, diff='', date='2026-10-05 10:00:00')
    calls = []
    monkeypatch.setattr(config, 'master_slave_upload_and_restart',
                        lambda *args, **kwargs: calls.append(kwargs['config_file_name']) or 'valid')
    response = product_client.post(f'/config/versions/haproxy/{product.server.ip}/{saved.name}/save', json={'action': 'save'})
    assert response.status_code == 201, response.json
    assert calls == [EXTRA]
