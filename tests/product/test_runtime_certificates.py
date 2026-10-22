import json
from uuid import uuid4

import pytest

from app.modules.db import db_model as models
from app.modules.db import service as service_sql
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.operations.worker import execute_operation, claim_operation
from app.modules.service import certificates


LOCALES = ('en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh')


def update_body(host, server):
    return dict(name='site.pem', pem=host.new, revision=host.revision(server.ip), operation_id=str(uuid4()))


def run(task_id):
    task = models.InstallationTasks.get_by_id(task_id)
    claim_operation(task.operation_id, task.id)
    return execute_operation(task.operation_id, task.id)


def test_update_persists_and_runs_through_operations(product_client, product, certificate_host):
    host = certificate_host
    url = f'/service/haproxy/certificates/{product.server.server_id}'
    response = product_client.get(url)
    assert response.status_code == 200
    assert response.json['certificates'][0]['can_update']
    assert 'PRIVATE KEY' not in response.text
    body = update_body(host, product.server)
    response = product_client.post(url, json=body)
    assert response.status_code == 202, response.text
    task_id = response.json['id']
    assert product_client.post(url, json=body).json['id'] == task_id
    task = models.InstallationTasks.get_by_id(task_id)
    assert 'PRIVATE KEY' not in task.operation_payload
    assert host.files[product.server.ip].read_text() == host.old
    assert run(task_id) == 'completed'
    assert run(task_id) == 'completed'
    normalized, _ = certificates.inspect_pem(host.new)
    assert host.files[product.server.ip].read_text() == normalized['fullchain'] + normalized['key']
    assert 'bundle' not in deserialize_operation_payload(models.InstallationTasks.get_by_id(task_id).operation_payload)
    response = product_client.get(f'/service/haproxy/certificates/operations/{task_id}')
    assert response.json['status'] == 'completed'
    assert response.json['targets'][0]['status'] == 'applied'
    assert 'PRIVATE KEY' not in response.text
    assert not list(host.root.rglob('pending.json'))


def test_slave_failure_rolls_back_master(product_client, product, certificate_host):
    host = certificate_host
    slave = models.Server.create(server_id=12, ip='192.0.2.12', hostname='Slave', group_id='1',
                                 master=product.server.server_id, haproxy=1)
    host.add(slave.ip, host.old)
    host.failed_hosts.add(slave.ip)
    response = product_client.post(f'/service/haproxy/certificates/{product.server.server_id}',
                                   json=update_body(host, product.server))
    assert response.status_code == 202, response.text
    assert run(response.json['id']) == 'failed'
    assert host.files[product.server.ip].read_text() == host.old
    assert host.active[str(host.files[product.server.ip])] == host.old
    assert host.files[slave.ip].read_text() == host.old
    state = product_client.get(f'/service/haproxy/certificates/operations/{response.json["id"]}').json
    assert state['status'] == 'failed'
    assert state['targets'][0]['status'] == 'rolled_back'


@pytest.mark.parametrize('phase', ['rollback', 'commit'])
def test_incomplete_recovery_can_resume_without_reapplying(product_client, product, certificate_host, monkeypatch, phase):
    host = certificate_host
    slave = models.Server.create(server_id=12, ip='192.0.2.12', hostname='Slave', group_id='1',
                                 master=product.server.server_id, haproxy=1)
    host.add(slave.ip, host.old)
    if phase == 'rollback':
        host.failed_hosts.add(slave.ip)
    request = certificates.remote
    interrupted = []
    recovery_hosts = []

    def interrupt_once(server, data):
        if data['operation'] == phase:
            recovery_hosts.append(server.ip)
            if server.ip == product.server.ip and not interrupted:
                interrupted.append(True)
                raise certificates.CertificateError('Connection unavailable', 'remote_failed')
        return request(server, data)

    monkeypatch.setattr(certificates, 'remote', interrupt_once)
    response = product_client.post(f'/service/haproxy/certificates/{product.server.server_id}',
                                   json=update_body(host, product.server))
    assert response.status_code == 202, response.text
    task_id = response.json['id']
    assert run(task_id) == 'failed'
    operation_url = f'/service/haproxy/certificates/operations/{task_id}'
    assert product_client.get(operation_url).json['retryable']
    assert slave.ip in recovery_hosts  # An unreachable master must not prevent recovery on its slaves.
    assert list(host.root.rglob('pending.json'))
    assert product_client.post(operation_url).status_code == 202
    assert run(task_id) == ('failed' if phase == 'rollback' else 'completed')
    assert not product_client.get(operation_url).json['retryable']
    assert not list(host.root.rglob('pending.json'))
    assert not list(host.root.rglob('previous.pem'))
    expected = host.old if phase == 'rollback' else host.new
    assert host.files[product.server.ip].read_text() == expected
    assert host.active[str(host.files[product.server.ip])] == expected


def test_catalog_distinguishes_loaded_certificate_from_disk(product_client, product, certificate_host):
    host = certificate_host
    host.files[product.server.ip].write_text(host.new)
    response = product_client.get(f'/service/haproxy/certificates/{product.server.server_id}')
    assert response.status_code == 200
    item = response.json['certificates'][0]
    assert item['disk_status'] == 'differs' and not item['can_update']
    assert item['disk']['fingerprint'] == certificates.certificate_metadata(host.new)['fingerprint']
    assert item['fingerprint'] == item['runtime']['fingerprint']
    assert 'PRIVATE KEY' not in response.text


@pytest.mark.parametrize('runtime_available', [True, False])
def test_catalog_includes_uploaded_files_without_exposing_keys(product_client, product, certificate_host, runtime_available):
    host = certificate_host
    folder = host.files[product.server.ip].parent
    bundle, _ = certificates.inspect_pem(host.new)
    (folder / 'uploaded.crt').write_text(bundle['fullchain'])
    (folder / 'uploaded.key').write_text(bundle['key'])
    (folder / 'unloaded.pem').write_text(host.new)
    (folder / 'unrelated.txt').write_text('not a certificate')
    host.unreachable = not runtime_available
    response = product_client.get(f'/service/haproxy/certificates/{product.server.server_id}')
    assert response.status_code == 200, response.text
    items = {item['name']: item for item in response.json['certificates']}
    assert set(items) == {'site.pem', 'uploaded.crt', 'uploaded.key', 'unloaded.pem'}
    assert items['uploaded.crt']['domains'] == ['example.test']
    for name in ('uploaded.crt', 'uploaded.key', 'unloaded.pem'):
        assert items[name]['can_view']
        assert items[name]['can_delete'] == runtime_available
        assert items[name]['disk_status'] == 'stored'
        assert not items[name]['can_update']
    assert 'PRIVATE KEY' not in response.text


def test_startup_discovery_runs_in_worker_and_changed_paths_are_rejected(product_client, product, certificate_host, monkeypatch):
    host = certificate_host
    discovery = []

    def settings(server, name, verify_startup=True):
        discovery.append(verify_startup)
        result = host.settings(server.ip)
        if verify_startup:
            result['cert_dir'] = '/changed/configuration'
        return result

    monkeypatch.setattr(certificates, 'deployment_settings', settings)
    response = product_client.post(f'/service/haproxy/certificates/{product.server.server_id}',
                                   json=update_body(host, product.server))
    assert response.status_code == 202, response.text
    assert discovery == [False]
    assert run(response.json['id']) == 'failed'
    assert discovery == [False, True]
    state = product_client.get(f'/service/haproxy/certificates/operations/{response.json["id"]}').json
    assert state['error_code'] == 'concurrent_change'
    assert state['targets'][0]['status'] == 'not_applied'
    assert host.files[product.server.ip].read_text() == host.old


def test_scope_roles_csrf_and_paths(product_client, product, certificate_host):
    url = f'/service/haproxy/certificates/{product.server.server_id}'
    body = update_body(certificate_host, product.server)
    assert product_client.get(f'/service/haproxy/certificates/{product.other.server_id}').status_code == 404
    assert product_client.post(f'/service/haproxy/certificates/{product.other.server_id}', json=body).status_code == 404
    assert product_client.post(url, json=body | {'name': '../site.pem'}).status_code == 400
    assert product_client.post(url, json=body | {'pem': 'invalid'}).status_code == 400
    token = product_client.environ_base.pop('HTTP_X_CSRF_TOKEN')
    assert product_client.post(url, json=body).status_code == 401
    product_client.environ_base['HTTP_X_CSRF_TOKEN'] = token
    models.UserGroups.update(user_role_id=4).where(models.UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.post(url, json=body).status_code == 403
    assert product_client.get(url).status_code == 200
    assert not product_client.get(url).json['certificates'][0]['can_update']
    assert not product_client.get(url).json['certificates'][0]['can_delete']


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
def test_file_actions_validate_scope_revision_and_permissions(product_client, product, certificate_host, service):
    host = certificate_host
    target = host.files[product.server.ip].parent / 'uploaded.pem'
    target.write_text(host.new)
    base = f'/service/{service}/certificates/{product.server.server_id}'
    item = next(item for item in product_client.get(base).json['certificates'] if item['name'] == 'uploaded.pem')
    url = base + '/file/' + item['file_token']
    response = product_client.get(url)
    assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
    assert 'BEGIN CERTIFICATE' in response.json['content'] and 'PRIVATE KEY' not in response.text
    other = f'/service/{service}/certificates/{product.other.server_id}/file/' + item['file_token']
    assert product_client.get(other).status_code == 404
    assert product_client.get(base + '/file/_p_invalid').status_code == 400
    assert product_client.delete(url, json={'revision': '0' * 64}).status_code == 409
    models.UserGroups.update(user_role_id=4).where(models.UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.delete(url, json={'revision': item['revision']}).status_code == 403
    models.UserGroups.update(user_role_id=1).where(models.UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.delete(url, json={'revision': item['revision']}).status_code == 200
    assert not target.exists()


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
@pytest.mark.parametrize('locale', LOCALES)
def test_all_locales_render_complete_certificate_labels(app, product_client, locale, service):
    baseline = app.jinja_env.get_template('languages/en.html').module.certificates
    translated = app.jinja_env.get_template(f'languages/{locale}.html').module.certificates
    assert set(translated) == set(baseline)
    assert all(translated.values())
    product_client.set_cookie('lang', locale)
    response = product_client.get(f'/service/{service}/ssl')
    assert response.status_code == 200
    assert translated['title'] in response.text
    assert 'id="runtime-certificates"' in response.text
    assert 'id="serv5"' not in response.text
    assert 'id="serv6"' not in response.text
    assert 'id="ssl_key_view"' not in response.text
    assert f'data-service="{service}"' in response.text
    assert 'id="cert-update-dialog"' in response.text
    assert ('id="cert-history-dialog"' in response.text) == (service == 'haproxy')


@pytest.mark.parametrize('service', ['nginx', 'apache'])
def test_service_catalog_uses_disk_and_own_service_permissions(product_client, product, certificate_host, monkeypatch, service):
    host = certificate_host
    bundle, _ = certificates.inspect_pem(host.new)
    folder = host.files[product.server.ip].parent
    (folder / 'uploaded.crt').write_text(bundle['fullchain'])
    (folder / 'uploaded.key').write_text(bundle['key'])

    def no_haproxy_settings(*args, **kwargs):
        pytest.fail('Disk catalog must not read HAProxy configuration')

    monkeypatch.setattr(certificates, 'deployment_settings', no_haproxy_settings)
    models.User.update(user_services=str(service_sql.select_service_id_by_slug(service))).where(
        models.User.user_id == product.admin.user_id).execute()
    url = f'/service/{service}/certificates/{product.server.server_id}'
    response = product_client.get(url)
    assert response.status_code == 200, response.text
    assert response.json['runtime_error'] is None
    assert response.json['operations'] == []
    items = {item['name']: item for item in response.json['certificates']}
    assert set(items) == {'site.pem', 'uploaded.crt', 'uploaded.key'}
    assert items['uploaded.crt']['domains'] == ['example.test']
    assert all(item['can_view'] and item['can_delete'] and not item['can_update'] for item in items.values())
    assert 'PRIVATE KEY' not in response.text
    assert host.calls == []
    assert product_client.get(f'/service/{service}/certificates/{product.other.server_id}').status_code == 404
    assert product_client.post(url, json={}).status_code == 405
    assert product_client.post(url + '/preview', json={}).status_code == 404
    assert product_client.get(f'/service/haproxy/certificates/{product.server.server_id}').status_code == 403

    models.UserGroups.update(user_role_id=4).where(models.UserGroups.user_id == product.admin.user_id).execute()
    assert not any(item['can_delete'] for item in product_client.get(url).json['certificates'])
    models.User.update(user_services='1').where(models.User.user_id == product.admin.user_id).execute()
    assert product_client.get(url).status_code == 403
