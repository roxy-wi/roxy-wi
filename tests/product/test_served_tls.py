"""Deployment receipts and live listener observations have independent outcomes."""
import pytest

from app.modules.connectors.certificates import CertWarden
from app.modules.db import db_model as m
from app.modules.operations.queue import deserialize_operation_payload as unseal
from app.modules.service import served_tls as tls, certificates, certificate_operations as operations, certificate_sources
from tests.product.test_runtime_certificates import update_body, run
from tests.product.test_certificate_source_workflows import source_body


def deploy(client, product, host):
    queued = client.post('/service/haproxy/certificates/11', json=update_body(host, product.server))
    assert queued.status_code == 202, queued.text
    assert host.served_calls == []
    assert run(queued.json['id']) == 'completed'
    response = client.get('/service/haproxy/certificates/operations/' + str(queued.json['id']))
    assert response.status_code == 200
    return response.json, m.InstallationTasks.get_by_id(queued.json['id'])


def test_completed_deployment_compares_actual_leaf_after_commit(product_client, product, certificate_host, monkeypatch):
    host = certificate_host
    original = certificates.remote
    committed = []
    def remote(server, data):
        result = original(server, data)
        if data['operation'] == 'commit':committed.append(server.server_id)
        return result
    monkeypatch.setattr(certificates, 'remote', remote)
    probe = tls.assessments.rpc
    def observe(server, *args, **kwargs):
        assert committed == [11]
        return probe(server, *args, **kwargs)
    monkeypatch.setattr(tls.assessments, 'rpc', observe)
    result, task = deploy(product_client, product, host)
    report = result['served_tls']
    assert report['state'] == 'verified' and report['peer_consistent']
    assert report['expected_fingerprint'] == certificates.certificate_metadata(host.new)['fingerprint']
    assert report['endpoints'][0]['tls'] == 'untrusted'  # Pinned leaf identity, not a CA-monitoring claim.
    assert result['status'] == 'completed' and result['targets'][0]['status'] == 'applied'
    assert task.operation_payload.startswith('fernet:')
    assert 'bundle' not in unseal(task.operation_payload)
    history = product_client.get('/service/haproxy/certificates/11/history').json['operations'][0]
    assert history['served_tls'] == report
    assert 'PRIVATE KEY' not in str(result)
    before = list(host.served_calls)
    assert run(task.id) == 'completed' and host.served_calls == before


@pytest.mark.parametrize('observed,state', [
    ({'tcp':'connected','tls':'verified','fingerprint':'f'*64}, 'mismatch'),
    ({'tcp':'refused','tls':'not-requested'}, 'incomplete'),
    ({'tcp':'connected','tls':'handshake-failed'}, 'incomplete'),
])
def test_old_or_unreachable_listener_never_falsifies_deployment_success(
        product_client, product, certificate_host, observed, state):
    certificate_host.served_overrides[11] = observed
    result, _ = deploy(product_client, product, certificate_host)
    assert result['status'] == 'completed' and result['served_tls']['state'] == state
    assert certificates.certificate_metadata(certificate_host.files[product.server.ip].read_text())['fingerprint'] == \
        certificates.certificate_metadata(certificate_host.new)['fingerprint']


def test_all_selected_replicas_compare_against_provider_and_each_other(product_client, product, certificate_host):
    peer = m.Server.create(server_id=12, hostname='Peer', ip='192.0.2.12', group_id='1', master=11, haproxy=1)
    certificate_host.add(peer.ip, certificate_host.old)
    certificate_host.served_overrides[12] = dict(tcp='connected', tls='verified',
        fingerprint=certificates.certificate_metadata(certificate_host.old)['fingerprint'])
    result, _ = deploy(product_client, product, certificate_host)
    assert result['served_tls']['state'] == 'mismatch' and not result['served_tls']['peer_consistent']
    assert {item['server_id'] for item in result['served_tls']['endpoints']} == {11, 12}


def test_provider_sync_exposes_evidence_without_separate_monitor(product_client, product, certificate_host, monkeypatch):
    monkeypatch.setattr(CertWarden, 'fetch', lambda _: certificate_host.new)
    api = '/service/certificate-sources/api'
    ident = product_client.post(api, json=source_body()).json['data']['id']
    check = product_client.post(f'{api}/{ident}/check', json={}).json
    assert certificate_sources.execute(m.InstallationTasks.get_by_id(check['task_id'])) == 'completed'
    assert certificate_host.served_calls == []
    queued = product_client.post(f'{api}/{ident}/sync', json={}).json
    assert certificate_sources.execute(m.InstallationTasks.get_by_id(queued['task_id'])) == 'completed'
    row = product_client.get(f'{api}/{ident}').json['data']
    assert row['status'] == 'current' and row['served_tls']['state'] == 'verified'
    assert row['served_tls']['expected_fingerprint'] == row['fingerprint']
    for path in ('/insights/tls', '/insights/api/tls'):
        assert product_client.get(path).status_code == 404
    assert not m.InstallationTasks.select().where(m.InstallationTasks.operation_type == 'served-tls').exists()
    assert not hasattr(m, 'ServedTlsMonitor')


def test_rollback_does_not_start_listener_verification(product_client, product, certificate_host):
    certificate_host.failed_hosts.add(product.server.ip)
    queued = product_client.post('/service/haproxy/certificates/11', json=update_body(certificate_host, product.server))
    assert run(queued.json['id']) == 'failed'
    assert not certificate_host.served_calls
    assert operations.public_task(m.InstallationTasks.get_by_id(queued.json['id']))['served_tls'] is None


@pytest.fixture
def verify_target(product, certificate_host):
    server = m.Server.get_by_id(product.server.server_id)
    settings = certificates.deployment_settings(server, 'site.pem')
    return {'11': dict(address=server.ip, settings=settings,
        identity=dict(ip=server.ip, port=server.port, cred_id=server.cred_id))}


@pytest.mark.parametrize('change', ['role','address','runtime'])
def test_changed_authority_or_runtime_prevents_probe(product, certificate_host, verify_target, monkeypatch, change):
    if change == 'role':m.UserGroups.update(user_role_id=4).where(m.UserGroups.user_id == product.admin.user_id).execute()
    elif change == 'address':verify_target['11']['address'] = '192.0.2.99'
    else:verify_target['11']['settings']['docker'] = True
    result = tls.verify(verify_target, certificates.certificate_metadata(certificate_host.new), 1, product.admin.user_id)
    assert result['state'] == 'incomplete' and not certificate_host.served_calls


def test_passive_node_is_not_presented_as_listener_verified(product, certificate_host, verify_target):
    verify_target['11']['settings']['cluster_proof'] = {'mode':'passive'}
    result = tls.verify(verify_target, certificates.certificate_metadata(certificate_host.new), 1, product.admin.user_id)
    assert result['state'] == 'incomplete' and result['endpoints'][0]['state'] == 'passive-staged'
    assert not certificate_host.served_calls


def test_bounded_probes_and_mixed_http_tls_listeners(product, certificate_host, verify_target, monkeypatch):
    def discover(*_):
        found = tls.inventory.parse('haproxy', 'frontend public\n bind *:80\n bind *:8443 ssl crt /site.pem\n')
        return dict(found, binding=None, running_sources_verified=True)
    monkeypatch.setattr(tls.inventory, 'discover', discover)
    result = tls.verify(verify_target, certificates.certificate_metadata(certificate_host.old), 1, product.admin.user_id)
    assert result['state'] == 'verified' and certificate_host.served_calls[0][1]['port'] == 8443
    certificate_host.served_calls.clear()
    metadata = dict(certificates.certificate_metadata(certificate_host.old), domains=[f'n{i}.example.test' for i in range(100)])
    result = tls.verify(verify_target, metadata, 1, product.admin.user_id)
    assert len(certificate_host.served_calls) == tls.MAX_PROBES and result['state'] == 'incomplete'


def test_config_drift_invalidates_observation(product, certificate_host, verify_target, monkeypatch):
    discover = tls.inventory.discover
    calls = []
    def changed(*args):
        value = discover(*args)
        calls.append(True)
        if len(calls) > 1:value['fingerprint'] = 'changed'
        return value
    monkeypatch.setattr(tls.inventory, 'discover', changed)
    result = tls.verify(verify_target, certificates.certificate_metadata(certificate_host.old), 1, product.admin.user_id)
    assert result['state'] == 'incomplete' and result['endpoints'][0]['state'] == 'configuration-changed'


def test_wildcard_uses_only_a_discovered_matching_sni(product, certificate_host, verify_target, monkeypatch):
    metadata = dict(certificates.certificate_metadata(certificate_host.old), domains=['*.example.test'])
    report = tls.verify(verify_target, metadata, 1, product.admin.user_id)
    assert report['state'] == 'incomplete' and not certificate_host.served_calls
    def discover(*_):
        found = tls.inventory.parse('haproxy', 'frontend public\n bind *:443 ssl crt /site.pem\n acl site hdr(host) -i app.example.test unrelated.test\n')
        return dict(found, binding=None, running_sources_verified=True)
    monkeypatch.setattr(tls.inventory, 'discover', discover)
    assert tls.verify(verify_target, metadata, 1, product.admin.user_id)['state'] == 'verified'
    assert [data['domain'] for _, data in certificate_host.served_calls] == ['app.example.test']


def test_unexpected_verifier_error_is_incomplete_not_failed_delivery(product_client, product, certificate_host, monkeypatch):
    monkeypatch.setattr(tls, '_verify', lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError('PRIVATE_DETAIL')))
    result, _ = deploy(product_client, product, certificate_host)
    assert result['status'] == 'completed' and result['served_tls']['state'] == 'incomplete'
    assert 'PRIVATE_DETAIL' not in str(result)
