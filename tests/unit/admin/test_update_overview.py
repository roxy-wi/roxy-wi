import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from flask import render_template

from app.modules.tools import updates
from app.routes.admin import routes


def service(name='roxy-wi-metrics', current='1.0', latest='4.0.0', workers=None):
    return [name, 'unknown', {'current_version': current, 'new_version': latest},
            workers or {}, {'category': 'distributed', 'deployment_mode': 'compose'}]


def worker(version='4.0.0'):
    return {'active': 1, 'versions': [version]}


def inventory(service_name='roxy-wi-metrics', version='4.0.0', running=True):
    return {'schema': 1, 'complete': True, 'observed_at': datetime.now(timezone.utc).isoformat(),
            'services': [{'service': service_name, 'version': version, 'running': running}]}


def test_update_route_loads_evidence_and_disables_package_actions_in_containers(app, monkeypatch):
    captured = {}
    monkeypatch.setattr(routes.roxywi_auth, 'page_for_admin', lambda: None)
    monkeypatch.setattr(routes.roxy, 'versions', lambda: {'current_ver': '9.2.0'})
    monkeypatch.setattr(routes.roxy, 'deployment_mode', lambda: 'compose')
    monkeypatch.setattr(routes.roxywi_common, 'get_user_lang_for_flask', lambda: 'en')
    rows = [service()]
    monkeypatch.setattr(routes, 'get_update_services', lambda: rows)
    monkeypatch.setattr(routes, 'render_template', lambda name, **kwargs: captured.update(kwargs) or name)
    with app.test_request_context('/admin/update'):
        response = routes.update_roxywi()
        assert response.get_data(as_text=True) == 'ajax/load_updateroxywi.html'
        assert response.headers['Cache-Control'] == 'no-store'
    assert captured['services'] is rows
    assert captured['package_deployment'] is False


def test_update_loader_uses_worker_summary_without_package_queries_in_containers(monkeypatch):
    captured = {}
    states = {'metrics': worker()}
    monkeypatch.setattr(updates, 'deployment_mode', lambda: 'compose')
    monkeypatch.setattr(updates.service_event, 'worker_summary', lambda: states)
    monkeypatch.setattr(updates, 'load_inventory', lambda: None)
    def services(**kwargs):
        captured.update(kwargs)
        return [service(workers=states['metrics'])]
    monkeypatch.setattr(updates.common, 'get_services_status', services)
    monkeypatch.setattr(updates.roxy_sql, 'get_all_tools', lambda: pytest.fail('package refresh in container'))
    assert updates.get_update_services()[0][2]['current_version'] == '4.0.0'
    assert captured == {'update_cur_ver': False, 'worker_states': states}


@pytest.mark.parametrize('mode', ['compose', 'quadlet', 'kubernetes'])
def test_container_bootstrap_values_are_not_installation_evidence(mode):
    for row in updates.prepare_updates([service(), service('roxy-wi-keep_alive'),
                                       service('roxy-wi-prometheus-exporter')], mode):
        assert row[2]['current_version'] == ''
        assert row[2]['version_known'] is False
        assert row[4]['inventory_state'] == 'not_reported'
        assert not row[4]['can_update_package']
        assert not row[4]['can_install_package']


def test_active_worker_version_wins_over_image_tag():
    result = updates.prepare_updates([service(workers=worker('4.1.0'))], 'compose', inventory())
    assert result[0][2]['current_version'] == '4.1.0'
    assert result[0][2]['version_source'] == 'worker'


@pytest.mark.parametrize(('current', 'latest', 'expected'), [
    ('4.0.0', '4.1.0', True), ('4.9', '4.10', True), ('4.10', '4.9', False),
    ('4.0', '4.0.0', False), ('4.0.0rc1', '4.0.0', True), ('4.0.0', 'unknown', False),
])
def test_update_comparison_uses_complete_versions(current, latest, expected):
    result = updates.prepare_updates([service(latest=latest, workers=worker(current))], 'compose')
    assert result[0][2]['need_update'] is expected


def test_multiple_active_versions_are_compared_individually():
    result = updates.prepare_updates([service(workers={'active': 2, 'versions': ['4.0.0','4.1.0']},
                                             latest='4.1.0')], 'compose')
    assert result[0][2]['need_update'] is True
    assert result[0][2]['current_version'] == '4.0.0, 4.1.0'


def test_stale_heartbeats_do_not_confirm_the_installed_version():
    result = updates.prepare_updates([service(workers={'active': 0, 'stale': 1, 'versions': ['4.0.0']})], 'compose')
    assert result[0][2]['version_known'] is False
    assert result[0][4]['inventory_state'] == 'stale'


@pytest.mark.parametrize('name', ['roxy-wi-keep_alive', 'roxy-wi-prometheus-exporter',
                                  'roxy-wi-metrics', 'roxy-wi-portscanner', 'roxy-wi-socket'])
def test_inventory_confirms_installed_but_stopped_components(name):
    result = updates.prepare_updates([service(name)], 'compose', inventory(name, '3.8', False))
    assert result[0][2]['current_version'] == '3.8'
    assert result[0][1] == 'stopped'
    assert result[0][2]['version_source'] == 'inventory'
    assert result[0][4]['inventory_state'] == 'reported'


def test_complete_empty_inventory_is_only_local_absence_evidence():
    result = updates.prepare_updates([service()], 'compose', {'services': []})
    assert result[0][4]['inventory_state'] == 'not_detected'
    assert not result[0][2]['version_known']


def test_package_updates_still_work_and_do_not_modify_stored_version_data():
    row = service(current='3.8')
    result = updates.prepare_updates([row], 'package', packages={'roxy-wi-metrics': row[2]})
    assert result[0][4]['can_update_package'] is True
    assert result[0][2]['current_version'] == '3.8'
    assert row[2] == {'current_version': '3.8', 'new_version': '4.0.0'}


def test_remote_worker_does_not_offer_an_update_of_a_missing_local_package():
    result = updates.prepare_updates([service(workers=worker('3.8'))], 'package',
                                     packages={'roxy-wi-metrics': {'current_version': '0'}})
    assert result[0][2]['need_update'] is True
    assert result[0][4]['can_update_package'] is False
    assert result[0][4]['can_install_package'] is False


@pytest.mark.parametrize('age', [-10, 121])
def test_inventory_rejects_future_and_expired_snapshots(tmp_path, monkeypatch, age):
    path = tmp_path / 'inventory.json'
    now = datetime.now(timezone.utc)
    payload = inventory()
    payload['observed_at'] = (now - timedelta(seconds=age)).isoformat()
    path.write_text(json.dumps(payload))
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_INVENTORY_FILE', str(path))
    assert updates.load_inventory(now=now) is None


@pytest.mark.parametrize('payload', ['{', '[]', '{"schema":1,"complete":false}', 'x' * (1024 * 1024 + 1)])
def test_bad_inventory_never_breaks_the_page(tmp_path, monkeypatch, payload):
    path = tmp_path / 'inventory.json'
    path.write_text(payload)
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_INVENTORY_FILE', str(path))
    assert updates.load_inventory() is None


def test_valid_inventory_is_read_without_database_changes(tmp_path, monkeypatch):
    path = tmp_path / 'inventory.json'
    payload = inventory()
    path.write_text(json.dumps(payload))
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_INVENTORY_FILE', str(path))
    assert updates.load_inventory()['services'] == payload['services']


@pytest.mark.parametrize('record', [
    {'service':'roxy-wi-metrics','version':'4.0.0','running':'false'},
    {'service':'roxy-wi-metrics','version':4,'running':True},
    {'version':'4.0.0','running':True},
])
def test_malformed_inventory_records_cannot_confirm_installation(tmp_path, monkeypatch, record):
    path = tmp_path / 'inventory.json'
    payload = inventory()
    payload['services'] = [record]
    path.write_text(json.dumps(payload))
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_INVENTORY_FILE', str(path))
    assert updates.load_inventory() is None


@pytest.mark.parametrize('language', ['en','ru','fr','es-ES','pt-br','zh'])
def test_update_page_renders_verified_versions_and_external_management(app, language):
    rows = updates.prepare_updates([service(workers=worker()),
                                    service('roxy-wi-prometheus-exporter')], 'compose')
    with app.test_request_context('/admin/update'):
        html = render_template('ajax/load_updateroxywi.html', services=rows, lang=language,
                               versions={'current_ver':'9.2.0','new_ver':'9.3.0','need_update':1},
                               package_deployment=False)
    assert '4.0.0' in html
    assert "updateService(" not in html
    assert 'current-version-roxy-wi-prometheus-exporter' not in html
    assert '>1.0<' not in html


def test_package_update_action_renders_for_semantic_version_difference(app):
    row = service(current='4.9',latest='4.10')
    rows = updates.prepare_updates([row], 'package', packages={'roxy-wi-metrics': row[2]})
    with app.test_request_context('/admin/update'):
        html = render_template('ajax/load_updateroxywi.html', services=rows, lang='en',
                               versions={'current_ver':'9.2.0','new_ver':'9.2.0','need_update':0},
                               package_deployment=True)
    assert "updateService('roxy-wi-metrics')" in html


@pytest.fixture()
def collector():
    spec = importlib.util.spec_from_file_location('service_inventory', Path('docker/collect_service_inventory.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collector_does_not_publish_credentials_and_includes_stopped_container(collector, tmp_path, monkeypatch):
    container = {'Name':'/roxy-wi-prometheus-exporter','Image':'sha256:test',
                 'Config':{'Image':'ghcr.io/roxy-wi/roxy-wi-prometheus-exporter:1.6',
                           'Env':['PASSWORD=do-not-publish'], 'Labels':{}},
                 'State':{'Running':False}}
    def command(args):
        if args[1:]==['ps','-aq']:
            return 'container-id\n'
        if args[1:3]==['container','inspect']:
            return json.dumps([container])
        if args[1:3]==['image','inspect']:
            return json.dumps([{'Config':{'Labels':{}}}])
        pytest.fail(str(args))
    monkeypatch.setattr(collector, 'command', command)
    services = collector.collect_containers('podman')
    path = tmp_path.resolve() / 'runtime' / 'inventory.json'
    collector.publish(path, services)
    assert 'do-not-publish' not in path.read_text()
    result = json.loads(path.read_text())
    assert result['services'][0]['version'] == '1.6'
    assert result['services'][0]['running'] is False
    assert result['services'][0]['version_source'] == 'image_tag'
    assert path.stat().st_mode & 0o777 == 0o640
    assert path.parent.stat().st_mode & 0o777 == 0o750


def test_collector_preserves_previous_snapshot_on_engine_failure(collector, tmp_path, monkeypatch):
    path = tmp_path / 'inventory.json'
    path.write_text('previous snapshot')
    monkeypatch.setattr(collector, 'collect_containers', lambda _engine: (_ for _ in ()).throw(RuntimeError('engine unavailable')))
    monkeypatch.setattr('sys.argv', ['collector','--engine','docker','--output',str(path)])
    with pytest.raises(RuntimeError, match='engine unavailable'):
        collector.main()
    assert path.read_text() == 'previous snapshot'


def test_collector_uses_image_version_label_and_ignores_unrelated_web_container(collector):
    assert collector.image_version({'Config':{'Labels':{'org.opencontainers.image.version':'3.8'}}}, 'custom:latest') == ('3.8','image_label')
    assert collector.image_version({'Config':{'Labels':{}}}, 'custom:latest') == (None,'unknown')
    assert collector.service_name({'Name':'/unrelated-web','Config':{'Labels':{
        'com.docker.compose.project':'unrelated','com.docker.compose.service':'web'}}}) is None


def test_collector_refuses_symlinked_parent_without_modifying_target(collector, tmp_path):
    root = tmp_path.resolve()
    target = root / 'unrelated'
    target.mkdir(mode=0o700)
    (root / 'runtime').symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError):
        collector.publish(root / 'runtime' / 'inventory.json', [])
    assert not (target / 'inventory.json').exists()
    assert target.stat().st_mode & 0o777 == 0o700


def test_collector_replaces_final_symlink_without_following_it(collector, tmp_path):
    root = tmp_path.resolve()
    secret = root / 'unrelated.txt'
    secret.write_text('unchanged')
    destination = root / 'inventory.json'
    destination.symlink_to(secret)
    collector.publish(destination, [])
    assert secret.read_text() == 'unchanged'
    assert not destination.is_symlink()
    assert json.loads(destination.read_text())['complete'] is True


@pytest.mark.parametrize('manager', ['dpkg-query','rpm'])
def test_package_inventory_uses_actual_package_and_canonical_unit(collector, monkeypatch, manager):
    from types import SimpleNamespace
    monkeypatch.setattr(collector, 'PACKAGES', {'roxy-wi-keep-alive':'roxy-wi-keep_alive'})
    monkeypatch.setattr(collector.shutil, 'which', lambda name: name if name in (manager,'systemctl') else None)
    monkeypatch.setattr(collector, 'command', lambda args: 'installed\t3.8-1' if args[0]=='dpkg-query' else '3.8')
    calls = []
    def status(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0 if args[-1]=='roxy-wi-keep_alive' else 3)
    monkeypatch.setattr(collector.subprocess, 'run', status)
    result = collector.collect_packages()
    assert result[0]['service'] == 'roxy-wi-keep_alive'
    assert result[0]['running'] is True
    assert calls[0][-1] == 'roxy-wi-keep_alive'


def test_collector_directory_permissions_do_not_depend_on_umask(collector, tmp_path):
    import os
    path = tmp_path.resolve() / 'runtime' / 'inventory.json'
    previous = os.umask(0o077)
    try:
        collector.publish(path, [])
    finally:
        os.umask(previous)
    assert path.parent.stat().st_mode & 0o777 == 0o750
    assert path.stat().st_mode & 0o777 == 0o640


def test_publication_pins_directory_if_parent_is_replaced(collector, tmp_path, monkeypatch):
    root = tmp_path.resolve()
    runtime, moved, outside = root/'runtime', root/'moved-runtime', root/'outside'
    runtime.mkdir()
    outside.mkdir(mode=0o700)
    replace = collector.os.replace
    def swap_parent(source, target, **kwargs):
        runtime.rename(moved)
        runtime.symlink_to(outside, target_is_directory=True)
        return replace(source, target, **kwargs)
    monkeypatch.setattr(collector.os, 'replace', swap_parent)
    collector.publish(runtime/'inventory.json', [])
    assert not (outside/'inventory.json').exists()
    assert json.loads((moved/'inventory.json').read_text())['complete'] is True
