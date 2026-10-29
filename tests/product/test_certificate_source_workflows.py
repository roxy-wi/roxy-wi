"""Real authenticated routes, provider retrieval and certificate runtime workflow."""
import pytest

from app.modules.connectors.certificates import CertWarden
from app.modules.db import db_model as models
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.service import certificate_sources as sources


API = '/service/certificate-sources/api'


def source_body(server_id=11):
    return dict(name='Public TLS', provider='certwarden', settings=dict(
        url='https://certwarden.example.test', certificate='example.test',
        certificate_api_key='SyntheticCertificateKey', private_key_api_key='SyntheticPrivateKey'),
        server_id=server_id, pem_name='site.pem', domains=['example.test'])


def assert_no_secrets(response):
    for secret in ('SyntheticCertificateKey', 'SyntheticPrivateKey', 'PRIVATE KEY', 'fernet:', 'operation_payload'):
        assert secret not in response.text


def test_source_forms_create_check_sync_and_remove(product_client, product, certificate_host, monkeypatch):
    monkeypatch.setattr(CertWarden, 'fetch', lambda _: certificate_host.new)
    response = product_client.get('/service/certificate-sources')
    assert response.status_code == 200 and 'source-form' in response.text
    assert product_client.get('/service/certificate-sources/choices').json['providers'][0]['id'] == 'certwarden'
    response = product_client.post(API, json=source_body())
    assert response.status_code == 201, response.text
    ident = response.json['data']['id']
    assert_no_secrets(response)
    assert 'Synthetic' not in models.CertificateSource.get_by_id(ident).configuration
    response = product_client.post(f'{API}/{ident}/check', json={})
    assert response.status_code == 202, response.text
    check = models.InstallationTasks.get_by_id(response.json['task_id'])
    assert sources.execute(check) == 'completed'
    assert certificate_host.stored_on == []
    response = product_client.post(f'{API}/{ident}/sync', json={})
    assert response.status_code == 202, response.text
    assert product_client.delete(f'{API}/{ident}').status_code == 409
    task = models.InstallationTasks.get_by_id(response.json['task_id'])
    assert sources.execute(task) == 'completed'
    assert certificate_host.files[product.server.ip].read_text() == certificate_host.new
    for response in (product_client.get(API), product_client.get(f'{API}/{ident}')):
        assert response.status_code == 200
        assert_no_secrets(response)
    response = product_client.get(f'{API}/{ident}')
    body = response.json['data']
    body = {key: body[key] for key in sources.SourceRequest.model_fields if key in body}
    body['name'] = 'Renamed'
    assert product_client.put(f'{API}/{ident}', json=body).status_code == 200
    assert product_client.put(f'{API}/{ident}', json=body).status_code == 409
    assert product_client.delete(f'{API}/{ident}').status_code == 200
    assert product_client.get(f'{API}/{ident}').status_code == 404
    assert certificate_host.files[product.server.ip].read_text() == certificate_host.new


def test_unchanged_source_compares_disk_sha256_and_runtime_agreement_without_redeploy(product_client,certificate_host,monkeypatch):
    monkeypatch.setattr(CertWarden,'fetch',lambda _:certificate_host.new)
    response=product_client.post(API,json=source_body());ident=response.json['data']['id']
    for _index in range(2):
        queued=product_client.post(f'{API}/{ident}/sync',json={})
        assert queued.status_code==202
        assert sources.execute(models.InstallationTasks.get_by_id(queued.json['task_id']))=='completed'
    assert models.InstallationTasks.select().where(models.InstallationTasks.operation_type=='certificate').count()==1


def test_same_leaf_with_changed_pem_bundle_still_deploys(product_client,certificate_host,monkeypatch):
    import re
    supplied=[certificate_host.new]
    monkeypatch.setattr(CertWarden,'fetch',lambda _:supplied[0])
    response=product_client.post(API,json=source_body());ident=response.json['data']['id']
    first=None
    for index in range(2):
        if index:
            supplied[0]+=re.search(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',certificate_host.new,re.S).group(0)+'\n'
        queued=product_client.post(f'{API}/{ident}/sync',json={})
        assert sources.execute(models.InstallationTasks.get_by_id(queued.json['task_id']))=='completed'
        current=models.CertificateSource.get_by_id(ident).fingerprint
        if first is None:first=current
        else:assert current==first
    assert models.InstallationTasks.select().where(models.InstallationTasks.operation_type=='certificate').count()==2


def test_source_rechecks_actual_role_and_protected_target(product_client, product):
    models.Server.update(protected=1).where(models.Server.server_id == 11).execute()
    models.UserGroups.update(user_role_id=3).where(models.UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.post(API, json=source_body()).status_code == 403
    models.UserGroups.update(user_role_id=4).where(models.UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.get(API).status_code == 403
    assert not models.CertificateSource.select().exists()


def test_source_group_and_service_permissions(product_client, product):
    response = product_client.post(API, json=source_body(22))
    assert response.status_code == 404
    assert not models.CertificateSource.select().exists()
    models.User.update(user_services='2 3').where(models.User.user_id == product.admin.user_id).execute()
    assert product_client.get(API).status_code == 403
    assert product_client.post(API, json=source_body()).status_code == 403


@pytest.mark.parametrize('change', [dict(provider='module.path'), dict(domains=['not a domain']),
    dict(pem_name='../private.pem'), dict(settings={'url':'http://insecure.test'}), dict(interval_minutes=1)])
def test_source_invalid_fields_are_rejected_without_leaking_keys(product_client, product, change):
    response = product_client.post(API, json=dict(source_body(), **change))
    assert response.status_code == 400, response.text
    assert_no_secrets(response)
    assert not models.CertificateSource.select().exists()


def test_source_csrf_is_required(product_client, product):
    product_client.environ_base.pop('HTTP_X_CSRF_TOKEN')
    assert product_client.post(API, json=source_body()).status_code == 401


@pytest.mark.parametrize('lost', ['server', 'cluster'])
def test_lost_source_registration_keeps_other_sources_manageable(product_client, product, lost, monkeypatch):
    from types import SimpleNamespace
    from app.modules.server import server as server_module
    monkeypatch.setattr(server_module, 'subprocess', SimpleNamespace(run=lambda *_args, **_kwargs: None))
    from app.modules.pacemaker import service
    from app.modules.pacemaker.schemas import ClusterCreate
    spare = models.Server.create(hostname='source-spare', ip='192.0.2.33', group_id='1', cred_id=11, haproxy=1)
    healthy = product_client.post(API, json=dict(source_body(spare.server_id), pem_name='healthy.pem')).json['data']
    body = source_body()
    if lost == 'cluster':
        cluster = service.register(ClusterCreate(name='source-cluster', members=[
            dict(server_id=s.server_id, name=f'source-node-{i}', address=s.ip, nodeid=i)
            for i, s in enumerate([product.server, spare], 1)]), 1)
        body['cluster_id'] = cluster.id
    response = product_client.post(API, json=body)
    assert response.status_code == 201, response.text
    ident = response.json['data']['id']
    if lost == 'server':
        assert product_client.delete('/server/11').status_code == 204
    else:
        assert product_client.delete('/pacemaker/api/' + str(cluster.id)).status_code == 200
    rows = product_client.get(API)
    assert rows.status_code == 200, rows.text
    assert {row['id'] for row in rows.json['data']} == {ident, healthy['id']}
    stale = product_client.get(f'{API}/{ident}')
    assert stale.status_code == 200 and stale.json['data']['binding_status'] == 'unavailable'
    assert_no_secrets(stale)
    assert product_client.post(f'{API}/{ident}/sync', json={}).status_code == 404
    replacement = dict(body, server_id=spare.server_id, cluster_id=None, revision=stale.json['data']['revision'])
    assert product_client.put(f'{API}/{ident}', json=replacement).status_code == 200
    assert product_client.get(f'{API}/{ident}').json['data']['binding_status'] == 'ready'
    assert product_client.delete('/server/' + str(spare.server_id)).status_code == 204
    assert product_client.delete(f'{API}/{ident}').status_code == 200
    assert product_client.delete(f'{API}/{healthy["id"]}').status_code == 200


def test_certificate_container_fallback_uses_server_group_without_request(product, app, monkeypatch):
    from flask import g
    from app.modules.service import certificates
    from app import cache
    for setting in list(models.Setting.select().where(models.Setting.group_id == 1)):
        if setting.param != 'haproxy_container_name':
            models.Setting.create(param=setting.param, section=setting.section, value=setting.value,
                desc=setting.desc, group_id=2)
    models.Setting.create(param='haproxy_container_name', section='haproxy', value='team-two-haproxy', desc='Fixture', group_id=2)
    cache.clear()
    with app.test_request_context():
        g.user_params = dict(group_id=2)
        requested = certificates.deployment_settings(product.other, 'test.pem', verify_startup=False)
    worker = certificates.deployment_settings(product.other, 'test.pem', verify_startup=False)
    assert requested['container'] == worker['container'] == 'team-two-haproxy'


@pytest.mark.parametrize('source_count, limit', [(1, 25), (3, 25), (3, 2)])
def test_source_automatic_sync_still_respects_direct_deployment_policy(
        product_client, product, monkeypatch, source_count, limit):
    for index in range(source_count):
        response = product_client.post(API, json=dict(
            source_body(), enabled=True, name=f'Source {index}', pem_name=f'site-{index}.pem'))
        assert response.status_code == 201, response.text
    before = sources.utc_now()
    monkeypatch.setattr('app.modules.config.deployment_policy.direct_deployment_allowed', lambda *_: False)
    assert sources.dispatch_due(limit=limit) == 0
    deferred = models.CertificateSource.select().where(models.CertificateSource.next_check > before)
    assert deferred.count() == min(source_count, limit)
    assert all(row.active_task_id is None for row in models.CertificateSource.select())
    assert not models.InstallationTasks.select().where(models.InstallationTasks.operation_type == 'certificate-source').exists()
    assert product_client.post(f'{API}/{response.json["data"]["id"]}/sync', json={}).status_code == 403


def test_source_automatic_sync_queues_multiple_sources_with_a_batch_limit(product_client, product):
    for index in range(3):
        response = product_client.post(API, json=dict(
            source_body(), enabled=True, name=f'Source {index}', pem_name=f'site-{index}.pem'))
        assert response.status_code == 201, response.text
    assert sources.dispatch_due(limit=2) == 2
    assert sources.dispatch_due() == 1
    assert sources.dispatch_due() == 0
    jobs = models.InstallationTasks.select().where(models.InstallationTasks.operation_type == 'certificate-source')
    assert jobs.count() == 3
    assert {row.active_task_id for row in models.CertificateSource.select()} == {job.id for job in jobs}
