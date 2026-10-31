import copy
import json
from types import SimpleNamespace
import pytest
from app.modules.db.db_model import InstallationTasks,OperationalAssessment,UserGroups,ServiceSetting,Server
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.service import proxy_assessments as diagnostic,published_endpoints as inventory

HAPROXY='''global
defaults
 mode http
frontend public
 bind *:443 ssl crt /private/site.pem
 acl site hdr(host) -i example.test
 use_backend pool if site
backend pool
 server app 192.0.2.88:8080
'''


@pytest.fixture
def diagnostic_host(product,monkeypatch):
    state=SimpleNamespace(discoveries=[],calls=[],drift=False,dns=['192.0.2.11'],tls='verified')
    parsed=inventory.parse('haproxy',HAPROXY)
    def discover(server,service):
        state.discoveries.append((server.server_id,service));result=copy.deepcopy(parsed)
        result.update(binding=None,running_sources_verified=True,service=service,server_id=server.server_id)
        if state.drift and len(state.discoveries)>1:result['fingerprint']='changed'
        return result
    def rpc(server,operation,data,binding=None):
        state.calls.append((operation,copy.deepcopy(data)))
        if operation=='resolve':return ['192.0.2.88'] if data['host']=='192.0.2.88' else ['192.0.2.11']
        return dict(ip=data['ip'],port=data['port'],tcp='refused' if data['port']==8080 else 'connected',tls=state.tls if data.get('tls') else 'not-requested',http=200 if data.get('http') else 'not-requested')
    monkeypatch.setattr(inventory,'discover',discover)
    monkeypatch.setattr(diagnostic,'interfaces',lambda _:['192.0.2.11'])
    monkeypatch.setattr(diagnostic,'rpc',rpc)
    monkeypatch.setattr(diagnostic.network,'resolve',lambda _:state.dns)
    def probe(data):
        state.calls.append(('controller-probe',copy.deepcopy(data)))
        return dict(ip=data['ip'],port=data['port'],tcp='connected',tls=state.tls,http=503)
    monkeypatch.setattr(diagnostic.network,'probe',probe)
    return state


def queue(client,server_id=11,**values):
    return client.post('/insights/api/diagnostics',json=dict(service='haproxy',server_id=server_id,url='https://example.test/',**values))


def finish(response):
    assert response.status_code==202,response.text
    assert diagnostic.execute(InstallationTasks.get_by_id(response.json['task_id']))=='completed'
    row=OperationalAssessment.get_by_id(response.json['id']);assert row.result.startswith('fernet:')
    return deserialize_operation_payload(row.result)


def test_request_path_uses_discovered_targets_and_distinguishes_backend_refusal(product_client,diagnostic_host):
    response=queue(product_client);report=finish(response)
    assert 'backend refuses' in report['summary']
    assert {s['key'] for s in report['stages']} >= {'dns-controller','dns-proxy-host','vip','tcp','tls-sni','frontend','http','backends'}
    assert all(data['ip'] in ('192.0.2.11','192.0.2.88','127.0.0.1') for kind,data in diagnostic_host.calls if 'probe' in kind or kind=='probe')
    assert product_client.get('/insights/api/assessments/'+str(response.json['id'])).status_code==200
    assert product_client.get('/insights/api/diagnostics?service=haproxy&server_id=11').json['data'][0]['id']==response.json['id']


def test_history_row_read_before_worker_finishes_includes_its_terminal_report(product_client,diagnostic_host):
    response=queue(product_client)
    assert response.status_code==202
    stale=OperationalAssessment.get_by_id(response.json['id'])
    assert stale.result==''
    assert diagnostic.execute(InstallationTasks.get_by_id(response.json['task_id']))=='completed'
    row=diagnostic.public(stale)
    assert row['status']=='completed' and 'backend refuses' in row['report']['summary']


def test_dns_answer_outside_authorized_listener_is_not_contacted(product_client,diagnostic_host):
    diagnostic_host.dns=['203.0.113.66']
    report=finish(queue(product_client))
    assert not any(kind=='controller-probe' for kind,_data in diagnostic_host.calls)
    assert next(s for s in report['stages'] if s['key']=='vip')['state']=='unknown'
    assert '203.0.113.66' in json.dumps(report)


def test_tls_failure_is_not_reported_as_a_successful_application_path(product_client,diagnostic_host):
    diagnostic_host.tls='untrusted';report=finish(queue(product_client))
    assert 'TLS trust' in report['summary'] and next(s for s in report['stages'] if s['key']=='tls-sni')['state']=='fail'


def test_changed_configuration_marks_the_result_stale(product_client,diagnostic_host):
    diagnostic_host.drift=True;report=finish(queue(product_client))
    assert report['stale'] and 'changed during' in report['summary']


@pytest.mark.parametrize('url',['file:///etc/passwd','http://user:password@example.test/','https://example.test/#fragment','https://example.test/%0d%0aHost:evil'])
def test_unsafe_urls_are_rejected_before_host_access(product_client,diagnostic_host,url):
    response=product_client.post('/insights/api/diagnostics',json=dict(service='haproxy',server_id=11,url=url))
    assert response.status_code==400 and not diagnostic_host.discoveries and not diagnostic_host.calls


def test_arbitrary_frontend_target_cannot_override_discovery(product_client,diagnostic_host):
    report=finish(queue(product_client,frontend_id='http://169.254.169.254/latest/'))
    assert 'unique frontend' in report['summary'] and not diagnostic_host.calls


@pytest.mark.parametrize('change',['ip','role','runtime'])
def test_queued_identity_permission_and_runtime_changes_prevent_probes(product_client,product,diagnostic_host,change):
    response=queue(product_client);assert response.status_code==202
    if change=='ip':Server.update(ip='192.0.2.77').where(Server.server_id==11).execute()
    elif change=='role':UserGroups.update(user_role_id=4).where(UserGroups.user_id==product.admin.user_id).execute()
    else:ServiceSetting.create(server_id=11,service='haproxy',setting='dockerized',value='1')
    assert diagnostic.execute(InstallationTasks.get_by_id(response.json['task_id']))=='failed'
    assert diagnostic_host.discoveries==[] and diagnostic_host.calls==[]


def test_group_isolation_and_duplicate_queue_are_enforced(product_client,product,diagnostic_host):
    response=queue(product_client);assert response.status_code==202
    assert queue(product_client).status_code==409
    assert queue(product_client,server_id=22).status_code==404
    UserGroups.update(user_role_id=2).where(UserGroups.user_id==product.admin.user_id).execute()
    assert product_client.get('/insights/api/diagnostics?service=haproxy&server_id=22').status_code==404


def test_metadata_parser_never_exports_configuration_passwords():
    text=HAPROXY.replace('acl site hdr(host) -i example.test','acl secret hdr(Authorization) -m str NeverExposeSecret\n acl site hdr(host) -i example.test')
    parsed=inventory.parse('haproxy',text)
    assert parsed['frontends'][0]['domains']==['example.test']
    assert 'NeverExposeSecret' not in json.dumps(parsed) and '/private/' not in json.dumps(parsed)
    apache=inventory.parse('apache','<VirtualHost *:443>\nServerName example.test\nSSLEngine on\nProxyPass / http://user:NeverExposeSecret@backend:80/\n</VirtualHost>')
    assert 'NeverExposeSecret' not in json.dumps(apache)


def test_duplicate_backend_targets_are_probed_once_per_assessment(product_client, diagnostic_host, monkeypatch):
    original = inventory.discover

    def discover(server, service):
        result = original(server, service)
        backend = result['frontends'][0]['backends'][0]
        result['frontends'][0]['backends'].append(dict(backend, id='second-reference'))
        return result

    monkeypatch.setattr(inventory, 'discover', discover)
    for _ in range(2):
        diagnostic_host.calls.clear()
        report = finish(queue(product_client))
        backends = next(stage for stage in report['stages'] if stage['key'] == 'backends')['details']['targets']
        assert len(backends) == 2
        assert backends[0]['probes'] == backends[1]['probes']
        assert len([data for operation, data in diagnostic_host.calls
                    if operation == 'resolve' and data['host'] == '192.0.2.88']) == 1
        assert len([data for operation, data in diagnostic_host.calls
                    if operation == 'probe' and data['port'] == 8080]) == 1


def test_invalid_encrypted_payload_finishes_failed_without_logging_secrets(product_client, diagnostic_host, monkeypatch):
    response = queue(product_client)
    task = InstallationTasks.get_by_id(response.json['task_id'])
    InstallationTasks.update(operation_payload='NeverExposeSecret').where(InstallationTasks.id == task.id).execute()
    logged = []
    monkeypatch.setattr(diagnostic.logger, 'error', lambda *args, **kwargs: logged.append((args, kwargs)))
    assert diagnostic.execute(task) == 'failed'
    assert logged[0][1]['task_id'] == task.id
    assert logged[0][1]['error_type']
    assert 'NeverExposeSecret' not in json.dumps(logged)
    assert not diagnostic_host.calls
    # Terminal tasks must not be probed again on redelivery.
    assert diagnostic.execute(task) == 'failed'
    assert len(logged) == 1


def test_diagnostics_links_redirect_to_service_cards_and_preserve_context(product_client):
    response = product_client.get('/insights/diagnostics?service=nginx&server_id=11')
    assert response.status_code == 302
    assert response.location.endswith('/service/nginx?diagnostics=11')
    assert product_client.get('/insights/diagnostics?service=haproxy&server_id=22').status_code == 404
    assert product_client.get('/insights/diagnostics?service=keepalived').status_code == 403


@pytest.mark.parametrize(('partial', 'unresolved', 'expected'), [
    (False, 0, 'not-applicable'),
    (True, 0, 'warning'),
    (False, 1, 'warning'),
])
def test_empty_backends_only_skip_complete_inventory(
    product_client, diagnostic_host, monkeypatch, partial, unresolved, expected,
):
    original = inventory.discover

    def discover(server, service):
        result = original(server, service)
        result['partial'] = partial
        result['frontends'][0].update(backends=[], unresolved_routes=unresolved)
        return result

    monkeypatch.setattr(inventory, 'discover', discover)
    report = finish(queue(product_client))
    stage = next(stage for stage in report['stages'] if stage['key'] == 'backends')
    assert stage['state'] == expected
    assert stage['details']['targets'] == []
    assert not any(data.get('port') == 8080 for _operation, data in diagnostic_host.calls)
