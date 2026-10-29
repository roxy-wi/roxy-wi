import copy
from datetime import timedelta
from types import SimpleNamespace
import pytest
from app.modules.common.time import utc_now
from app.modules.db.db_model import ServedTlsMonitor, InstallationTasks, CertificateSource, Server, UserGroups
from app.modules.operations.queue import deserialize_operation_payload as unseal, serialize_operation_payload as seal
from app.modules.service import served_tls as tls, certificates, proxy_assessments
from tests.product.test_proxy_diagnostics import diagnostic_host
from tests.product.test_service_map import discover
from tests.fixtures.certificate_runtime import make_pem


@pytest.fixture
def tls_host(diagnostic_host,monkeypatch):
    state=SimpleNamespace(metadata=certificates.certificate_metadata(make_pem()),peer=None,unreachable=False,untrusted=False)
    def rpc(server,operation,data,**kwargs):
        assert operation=='probe' and data['tls'] and not data['http']
        diagnostic_host.calls.append(('tls',data))
        if state.unreachable:return dict(ip=data['ip'],port=data['port'],tcp='refused',tls='not-requested')
        metadata=state.peer if state.peer and server.server_id!=11 else state.metadata
        return dict(ip=data['ip'],port=data['port'],tcp='connected',tls='untrusted' if state.untrusted else 'verified',fingerprint=metadata['fingerprint'],certificate=metadata)
    monkeypatch.setattr(proxy_assessments,'rpc',rpc)
    monkeypatch.setattr(tls.network,'resolve',lambda _:['192.0.2.11'])
    def probe(data):
        diagnostic_host.calls.append(('tls-controller',data));assert not data['http']
        return dict(ip=data['ip'],port=data['port'],tcp='connected',tls='verified',fingerprint=state.metadata['fingerprint'],certificate=state.metadata)
    monkeypatch.setattr(tls.network,'probe',probe)
    return state


def body(ident,**values):
    return dict(name='Published application',domain='example.test',port=443,targets=[dict(assessment_id=ident,frontend_id='frontend:public')],**values)


def save(client,ident,**values):
    response=client.post('/insights/api/tls',json=body(ident,**values));assert response.status_code==201,response.text
    return response.json['data']


def run(client,monitor):
    response=client.post('/insights/api/tls/'+str(monitor['id'])+'/run',json={});assert response.status_code==202,response.text
    assert tls.execute(InstallationTasks.get_by_id(response.json['task_id']))=='completed'
    return client.get('/insights/api/tls').json['data'][0]['report']


def test_tls_checks_actual_listener_and_expected_source_with_encrypted_history(product_client,tls_host):
    ident=discover(product_client)
    source=CertificateSource.create(group_id=1,user_id=1,name='Provider certificate',provider='certwarden',configuration=seal({}),status='current',fingerprint=tls_host.metadata['fingerprint'])
    monitor=save(product_client,ident,source_id=source.id)
    assert ServedTlsMonitor.get_by_id(monitor['id']).configuration.startswith('fernet:')
    report=run(product_client,monitor)
    assert report['state']=='verified' and report['peer_consistent'] and report['expected_match']
    history=product_client.get('/insights/api/tls/'+str(monitor['id'])+'/history').json['data']
    assert history[0]['status']=='completed' and history[0]['report']['endpoints'][0]['certificate']['not_after']


def test_old_cert_on_second_proxy_is_a_mismatch(product_client,product,tls_host):
    first=discover(product_client)
    Server.create(server_id=33,hostname='Peer',ip='192.0.2.33',group_id='1',cred_id=11,haproxy=1)
    response=product_client.post('/insights/api/services/discover',json=dict(service='haproxy',server_id=33))
    assert proxy_assessments.execute(InstallationTasks.get_by_id(response.json['task_id']))=='completed'
    tls_host.peer=certificates.certificate_metadata(make_pem(serial=2))
    values=body(first);values['targets'].append(dict(assessment_id=response.json['id'],frontend_id='frontend:public'))
    response=product_client.post('/insights/api/tls',json=values);assert response.status_code==201
    report=run(product_client,response.json['data'])
    assert report['state']=='mismatch' and not report['peer_consistent']


def test_public_snapshot_keeps_polling_when_worker_finishes_during_serialization(product_client,tls_host,monkeypatch):
    monitor=save(product_client,discover(product_client))
    queued=product_client.post('/insights/api/tls/'+str(monitor['id'])+'/run',json={}).json
    row=ServedTlsMonitor.get_by_id(monitor['id'])
    original=tls.authorize
    def finish(*args,**kwargs):
        monkeypatch.setattr(tls,'authorize',original)
        assert tls.execute(InstallationTasks.get_by_id(queued['task_id']))=='completed'
        return original(*args,**kwargs)
    monkeypatch.setattr(tls,'authorize',finish)
    snapshot=tls.public(row,1)
    assert snapshot['active_task_id']==queued['task_id']
    assert product_client.get('/insights/api/tls').json['data'][0]['report']['state']=='verified'


def test_public_snapshot_reloads_a_row_fetched_before_task_completion(product_client,tls_host):
    monitor=save(product_client,discover(product_client))
    queued=product_client.post('/insights/api/tls/'+str(monitor['id'])+'/run',json={}).json
    stale=ServedTlsMonitor.get_by_id(monitor['id'])
    assert tls.execute(InstallationTasks.get_by_id(queued['task_id']))=='completed'
    snapshot=tls.public(stale,1)
    assert snapshot['active_task_id'] is None
    assert snapshot['report']['state']=='verified'


@pytest.mark.parametrize('failure',['unreachable','untrusted','expiry'])
def test_incomplete_untrusted_and_expiring_are_not_verified(product_client,tls_host,failure):
    ident=discover(product_client);monitor=save(product_client,ident)
    if failure=='expiry':tls_host.metadata['not_after']=(utc_now()+timedelta(days=2)).isoformat()+'+00:00'
    else:setattr(tls_host,failure,True)
    report=run(product_client,monitor)
    assert report['state']==('expiring' if failure=='expiry' else 'partial')


def test_expected_source_change_queues_verification_before_interval_and_never_reports_delivery_as_served(product_client,tls_host):
    ident=discover(product_client)
    source=CertificateSource.create(group_id=1,user_id=1,name='Provider',provider='certwarden',configuration=seal({}),status='current',fingerprint=tls_host.metadata['fingerprint'])
    monitor=save(product_client,ident,source_id=source.id,enabled=True)
    assert run(product_client,monitor)['state']=='verified'
    assert tls.dispatch_due()==0
    CertificateSource.update(fingerprint='f'*64).where(CertificateSource.id==source.id).execute()
    assert product_client.get('/insights/api/tls').json['data'][0]['expectation_current'] is False
    assert tls.dispatch_due()==1 and tls.dispatch_due()==0
    row=ServedTlsMonitor.get_by_id(monitor['id']);assert tls.execute(InstallationTasks.get_by_id(row.active_task_id))=='completed'
    assert product_client.get('/insights/api/tls').json['data'][0]['report']['state']=='mismatch'


def test_chain_only_deployment_triggers_verification_after_source_finishes(product_client,tls_host):
    ident=discover(product_client)
    source=CertificateSource.create(group_id=1,user_id=1,name='Provider chain',provider='certwarden',configuration=seal({}),status='current',fingerprint=tls_host.metadata['fingerprint'])
    monitor=save(product_client,ident,source_id=source.id,enabled=True);run(product_client,monitor)
    CertificateSource.update(deployment_task_id=77,active_task_id=99).where(CertificateSource.id==source.id).execute()
    assert tls.dispatch_due()==0 # no verification is claimed during delivery
    CertificateSource.update(active_task_id=None).where(CertificateSource.id==source.id).execute()
    assert tls.dispatch_due()==1
    row=ServedTlsMonitor.get_by_id(monitor['id']);assert tls.execute(InstallationTasks.get_by_id(row.active_task_id))=='completed'


def test_target_domain_port_private_key_and_unknown_fields_are_rejected_before_probing(product_client,tls_host,diagnostic_host):
    ident=discover(product_client)
    for values in (dict(domain='unknown.test'),dict(port=4443),dict(ca_pem=make_pem()),dict(shell='echo injected')):
        data=body(ident);data.update(values)
        assert product_client.post('/insights/api/tls',json=data).status_code==400
    assert diagnostic_host.calls==[]


def test_queued_role_and_identity_changes_prevent_probes(product_client,product,tls_host,diagnostic_host):
    monitor=save(product_client,discover(product_client))
    response=product_client.post('/insights/api/tls/'+str(monitor['id'])+'/run',json={})
    UserGroups.update(user_role_id=4).where(UserGroups.user_id==product.admin.user_id).execute()
    assert tls.execute(InstallationTasks.get_by_id(response.json['task_id']))=='failed' and diagnostic_host.calls==[]
    assert product_client.post('/insights/api/tls/'+str(monitor['id'])+'/run',json={}).status_code==403


def test_revision_conflict_tenant_and_duplicate_queue_are_enforced(product_client,product,tls_host):
    ident=discover(product_client);monitor=save(product_client,ident)
    assert product_client.put('/insights/api/tls/'+str(monitor['id']),json=body(ident,revision=2)).status_code==409
    assert product_client.post('/insights/api/tls/'+str(monitor['id'])+'/run',json={}).status_code==202
    assert product_client.post('/insights/api/tls/'+str(monitor['id'])+'/run',json={}).status_code==409
    ServedTlsMonitor.update(group_id=2).where(ServedTlsMonitor.id==monitor['id']).execute()
    assert product_client.get('/insights/api/tls/'+str(monitor['id'])+'/history').status_code==404


def test_changed_config_is_stale_and_does_not_probe_changed_targets(product_client,tls_host,diagnostic_host):
    monitor=save(product_client,discover(product_client));diagnostic_host.drift=True
    report=run(product_client,monitor)
    assert report['state']=='stale'
    assert not any(kind=='tls' for kind,_ in diagnostic_host.calls)
