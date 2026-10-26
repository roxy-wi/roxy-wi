"""Stats operations share persistence, failure handling and configuration locks."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
import hashlib
from pathlib import Path
import threading

import pytest

from app.modules.db import add as add_sql
from app.modules.db.db_model import HaproxySection
from app.modules.service.stats import haproxy_stats_config as stats_config
from app.modules.service.stats import haproxy_stats_maxconn as maxconn
from tests.fixtures.haproxy_servers import server_host, maxconn_host  # noqa: F401
from tests.product.test_haproxy_stats_maxconn import body as maxconn_body
from tests.product.test_haproxy_stats_servers import prepare


def request(app, ip, operation, payload):
    with app.test_client() as client:
        login = client.post('/login', json={
            'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/admin',
        })
        assert login.status_code == 200
        client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value
        client.environ_base['HTTP_ACCEPT'] = 'application/json'
        response = client.post(f'/stats/{operation}/haproxy/{ip}', json=payload)
        return response.status_code, response.json


def test_server_edit_and_maxconn_serialize_and_preserve_both_changes(
    app, product_client, product, server_host, monkeypatch,
):
    payload = prepare(product_client, product)
    validating, waiting, release = (threading.Event() for _ in range(3))
    original_lock = stats_config.file_lock

    @contextmanager
    def observed_lock(path):
        if validating.is_set():
            waiting.set()
        with original_lock(path):
            yield

    def hold_first_validation(ip):
        if not validating.is_set():
            validating.set()
            assert release.wait(15), 'Concurrent request did not reach the lock'

    monkeypatch.setattr(stats_config, 'file_lock', observed_lock)
    server_host.validation_hook = hold_first_validation
    with ThreadPoolExecutor(max_workers=2) as pool:
        edit = pool.submit(request, app, product.server.ip, 'servers', payload)
        try:
            assert validating.wait(15)
            maxconn = pool.submit(request, app, product.server.ip, 'maxconn', maxconn_body())
            assert waiting.wait(15)
            with pytest.raises(TimeoutError):
                maxconn.result(timeout=0.1)
            assert not server_host.writes and not server_host.saves
        finally:
            release.set()
        assert edit.result(timeout=15)[0] == 200
        status, result = maxconn.result(timeout=15)
        assert status == 200, result

    for node, record in zip((product.server, server_host.linked), server_host.records):
        assert 'server one 192.0.2.45:8181 check maxconn 150' in server_host.configs[node.ip]
        saved = HaproxySection.get_by_id(record.id).config['backend_servers'][0]
        assert (saved['server'], saved['port'], saved['maxconn']) == ('192.0.2.45', 8181, 150)
    assert len(server_host.saves) == 4


@pytest.mark.parametrize('operation', ['servers', 'maxconn'])
def test_topology_is_rechecked_after_waiting_for_existing_worker_lock(
    app, product_client, product, server_host, monkeypatch, operation,
):
    payload = prepare(product_client, product) if operation == 'servers' else maxconn_body()
    waiting = threading.Event()
    original_lock = stats_config.file_lock
    # Use the pre-refactor lock path: old and new workers must still serialize.
    lock_dir = product.root / 'lib' / 'stats-maxconn-locks'
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / (hashlib.sha256(product.server.ip.encode()).hexdigest() + '.lock')

    @contextmanager
    def observed_lock(path):
        waiting.set()
        with original_lock(path):
            yield

    monkeypatch.setattr(stats_config, 'file_lock', observed_lock)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with original_lock(lock_path):
            future = pool.submit(request, app, product.server.ip, operation, payload)
            assert waiting.wait(15)
            server_host.linked.master = 0
            server_host.linked.save()
        status, result = future.result(timeout=15)
    assert status == 409 and result['code'] == 'target_changed'
    assert not server_host.validations and not server_host.writes and not server_host.saves


@pytest.mark.parametrize('operation,failure', [
    ('maxconn', 'runtime'), ('edit', 'runtime'),
    ('maxconn', 'save'), ('edit', 'save'), ('delete', 'save'),
    ('maxconn', 'database'), ('edit', 'database'), ('delete', 'database'),
])
def test_changes_stop_at_failed_stage_and_leave_other_nodes_pending(
    product_client, product, server_host, monkeypatch, operation, failure,
):
    payload = maxconn_body() if operation == 'maxconn' else prepare(product_client, product, operation)
    endpoint = 'maxconn' if operation == 'maxconn' else 'servers'
    prefix = 'maxconn' if operation == 'maxconn' else 'server'
    updates = []

    def update(*args, **kwargs):
        updates.append(args)
        raise RuntimeError('private-settings-detail')

    monkeypatch.setattr(add_sql, 'update_haproxy_section_maxconn', update)
    monkeypatch.setattr(add_sql, 'update_haproxy_server_settings', update)
    if failure != 'database':
        setattr(server_host, 'fail_' + failure, product.server.ip)
    response = product_client.post(f'/stats/{endpoint}/haproxy/{product.server.ip}', json=payload)
    assert response.status_code == 502
    assert response.json['code'] == prefix + ('_section_sync_failed' if failure == 'database' else '_incomplete')
    first, second = response.json['nodes']
    assert first['runtime'] == ('unknown' if failure == 'runtime' or operation == 'delete' and failure == 'save' else 'applied')
    assert first['config'] == {'runtime': 'pending', 'save': 'unknown', 'database': 'saved'}[failure]
    assert second == dict(server=server_host.linked.ip, runtime='pending', config='pending',
                          **({'settings': 'pending'} if operation != 'maxconn' else {}))
    if operation != 'maxconn':
        assert first['settings'] == 'pending'
    assert len(server_host.writes) == (0 if operation == 'delete' else 1)
    assert len(server_host.saves) == len(updates) == (1 if failure == 'database' else 0)
    assert all(HaproxySection.get_by_id(record.id).config == record.config for record in server_host.records)
    assert 'private-' not in response.text


@pytest.mark.parametrize('operation', ['servers', 'maxconn'])
def test_failed_replica_download_cleans_all_candidates_before_any_write(
    product_client, product, server_host, monkeypatch, operation,
):
    payload = prepare(product_client, product) if operation == 'servers' else maxconn_body()
    download = stats_config.config.get_config
    candidates = []

    def fail_download(ip, filename, **kwargs):
        candidates.append(Path(filename))
        download(ip, filename, **kwargs)
        if ip == server_host.linked.ip:
            raise OSError('private-download-detail')

    monkeypatch.setattr(stats_config.config, 'get_config', fail_download)
    response = product_client.post(f'/stats/{operation}/haproxy/{product.server.ip}', json=payload)
    assert response.status_code == 500
    assert len(candidates) == 2 and all(not path.exists() for path in candidates)
    assert not server_host.writes and not server_host.saves
    assert 'private-' not in response.text


def test_missing_runtime_reply_is_not_treated_as_confirmed_success(
    product_client, product, server_host, monkeypatch,
):
    commands = []

    def missing_reply(*args):
        commands.append(args)
        return None

    monkeypatch.setattr(maxconn, 'execute_runtime_command', missing_reply)
    response = product_client.post(f'/stats/maxconn/haproxy/{product.server.ip}', json=maxconn_body())
    assert response.status_code == 502
    assert response.json['code'] == 'maxconn_incomplete'
    assert response.json['nodes'] == [
        dict(server=product.server.ip, runtime='unknown', config='pending'),
        dict(server=server_host.linked.ip, runtime='pending', config='pending'),
    ]
    assert len(commands) == 1 and not server_host.saves
    assert all(HaproxySection.get_by_id(record.id).config == record.config for record in server_host.records)
