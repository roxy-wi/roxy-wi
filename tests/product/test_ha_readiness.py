import json
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import pytest
from app.modules.common.time import utc_now, utc_iso
from app.modules.db.db_model import (PacemakerCluster, Server, InstallationTasks, HaReadinessProfile,
    OperationalAssessment, UserGroups, HaCluster, HaClusterRouter, HaClusterSlave, HaClusterVip)
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.service import ha_readiness as audit


@pytest.mark.parametrize('active,expected', [
    ('Yes (client certificate sent)', True), ('Yes', True),
    ('No', False), ('Yesterday', False), ('', False),
])
def test_qdevice_tls_observation_accepts_live_certificate_annotation(monkeypatch, active, expected):
    # Debian 13 and Rocky 9 append the client-certificate detail to TLS active.
    client = ('QNetd host:\t\t192.0.2.99:5403\nTLS:\t\t\tRequired\n'
              'State:\t\t\tConnected\nTLS active:\t\t' + active + '\nConnected since:\t2026-10-29T01:13:29\n')
    def run(argv, **_kwargs):
        return {'corosync-cmapctl': 'totem.cluster_name (str) = product-ha',
                'cibadmin': '<cib><configuration/></cib>', 'python3': 'a' * 64,
                'crm_mon': 'state', 'corosync-quorumtool': 'quorum',
                'corosync-qdevice-tool': client}[argv[2] if argv[0] == 'env' else argv[0]]
    monkeypatch.setattr(audit, 'Remote', lambda _server: SimpleNamespace(run=run))
    monkeypatch.setattr(audit, 'summary', lambda _: dict(quorate=True))
    monkeypatch.setattr(audit, 'details', lambda _: dict(configured=True, votes=1))
    node = audit.pacemaker_node(SimpleNamespace(name='product-ha'), 'one', SimpleNamespace(server_id=11))
    assert node['witness'] == dict(tls=expected, host='192.0.2.99:5403')


@pytest.fixture
def readiness_cluster(product,monkeypatch):
    second=Server.create(server_id=33,hostname='Product standby',ip='192.0.2.33',group_id='1',cred_id=11,haproxy=1)
    cluster=PacemakerCluster.create(name='product-ha',group_id=1,servers=json.dumps([
        dict(server_id=11,name='one',address='192.0.2.11',nodeid=1),dict(server_id=33,name='two',address='192.0.2.33',nodeid=2)]))
    xml='<cib><configuration><crm_config/><resources><primitive id="fence" class="stonith" type="fence_pve"><instance_attributes id="p"><nvpair name="pcmk_host_list" value="one two"/><nvpair name="passwd" value="NeverExposeThisSecret"/></instance_attributes></primitive></resources></configuration></cib>'
    observations={name:dict(id=ident,name=name,digest='a'*64,corosync_digest='b'*64,
        state=dict(quorate=True,nodes=[dict(name=n,online='true',unclean='false') for n in ('one','two')],failures=0,resources=[]),
        quorum=dict(configured=True,votes=1,two_node=False),witness=dict(tls=True,host='192.0.2.99:5403'),_xml=xml)
        for name,ident in [('one',11),('two',33)]}
    calls=[]
    def observe(_cluster,name,server):calls.append(server.server_id);return deepcopy(observations[name])
    monkeypatch.setattr(audit,'pacemaker_node',observe)
    return SimpleNamespace(cluster=cluster,second=second,observations=observations,calls=calls,xml=xml)


def run(product_client,state):
    response=product_client.post(f'/ha/api/readiness/pacemaker/{state.cluster.id}/run',json={})
    assert response.status_code==202,response.text
    task=InstallationTasks.get_by_id(response.json['task_id'])
    assert audit.execute(task)=='completed'
    row=OperationalAssessment.get_by_id(response.json['id'])
    assert row.result.startswith('fernet:')
    return row,deserialize_operation_payload(row.result)


def test_audit_reads_every_member_and_never_calls_configured_fencing_tested(product_client,readiness_cluster):
    row,result=run(product_client,readiness_cluster)
    assert readiness_cluster.calls==[11,33]
    checks={check['key']:check for check in result['checks']}
    assert checks['witness']['state']=='observed' and checks['fencing']['state']=='configured'
    assert checks['verification']['state']=='unknown' and result['last_verified_test'] is None
    assert checks['domain:hypervisor']['state']=='unknown'
    assert 'NeverExposeThisSecret' not in json.dumps(result)
    response=product_client.get(f'/ha/api/readiness/pacemaker/{readiness_cluster.cluster.id}')
    assert response.status_code==200 and response.json['assessments'][0]['id']==row.id


@pytest.mark.parametrize('field,value',[('votes',0),('tls',False),('host','192.0.2.88:5403')])
def test_quorate_cluster_with_zero_or_mismatched_witness_evidence_fails(product_client,readiness_cluster,field,value):
    node=readiness_cluster.observations['two']
    node['quorum' if field=='votes' else 'witness'][field]=value
    _row,result=run(product_client,readiness_cluster)
    assert next(c for c in result['checks'] if c['key']=='witness')['state']=='fail'


def test_unreachable_member_never_yields_success_or_raw_ssh_errors(product_client,readiness_cluster,monkeypatch):
    def unavailable(_cluster,name,server):
        if name=='two':raise RuntimeError('PRIVATE SSH CREDENTIAL')
        return deepcopy(readiness_cluster.observations[name])
    monkeypatch.setattr(audit,'pacemaker_node',unavailable)
    _row,result=run(product_client,readiness_cluster)
    assert next(c for c in result['checks'] if c['key']=='members')['state']=='fail'
    assert 'PRIVATE SSH' not in json.dumps(result)


def test_failure_domains_are_group_scoped_and_versioned(product_client,readiness_cluster):
    url=f'/ha/api/readiness/pacemaker/{readiness_cluster.cluster.id}/profile'
    body=dict(revision=0,domains={'11':dict(hypervisor='pve-one'),'33':dict(hypervisor='pve-one')})
    response=product_client.post(url,json=body)
    assert response.status_code==200,response.text
    assert product_client.post(url,json=body).status_code==409
    assert product_client.post(url,json=dict(revision=response.json['profile']['revision'],domains={'22':dict(power='secret')})).status_code==400
    _row,result=run(product_client,readiness_cluster)
    assert next(c for c in result['checks'] if c['key']=='domain:hypervisor')['evidence']['shared']==['pve-one']


def test_operator_test_record_remains_attested_and_becomes_stale_after_drift(product_client,readiness_cluster):
    row,_result=run(product_client,readiness_cluster)
    body=dict(kind='fencing',result='passed',tested_at=utc_iso(utc_now()),note='External ticket with test procedure',assessment_id=row.id)
    url=f'/ha/api/readiness/pacemaker/{readiness_cluster.cluster.id}/attest'
    assert product_client.post(url,json=dict(body,tested_at=utc_iso(utc_now()+timedelta(days=1)))).status_code==400
    assert product_client.post(url,json=body).status_code==200
    _row,result=run(product_client,readiness_cluster)
    assert result['attestations'][0]['source']=='operator-attestation'
    assert result['attestations'][0]['configuration_current'] and result['last_verified_test'] is None
    readiness_cluster.observations['two']['corosync_digest']='c'*64
    _row,result=run(product_client,readiness_cluster)
    assert not result['attestations'][0]['configuration_current']


@pytest.mark.parametrize('change',['identity','role','disabled'])
def test_queued_audit_rechecks_permissions_and_host_identity(product_client,product,readiness_cluster,change):
    response=product_client.post(f'/ha/api/readiness/pacemaker/{readiness_cluster.cluster.id}/run',json={})
    if change=='identity':Server.update(ip='192.0.2.77').where(Server.server_id==33).execute()
    elif change=='role':UserGroups.update(user_role_id=4).where(UserGroups.user_id==product.admin.user_id).execute()
    else:product.admin.enabled=0;product.admin.save()
    task=InstallationTasks.get_by_id(response.json['task_id'])
    assert audit.execute(task)=='failed'
    assert readiness_cluster.calls==[]


def test_cross_group_requests_and_viewer_mutations_do_not_reach_hosts(product_client,product,readiness_cluster):
    other=PacemakerCluster.create(name='private-ha',group_id=2,servers=readiness_cluster.cluster.servers)
    assert product_client.get(f'/ha/api/readiness/pacemaker/{other.id}').status_code==404
    UserGroups.update(user_role_id=4).where(UserGroups.user_id==product.admin.user_id).execute()
    assert product_client.post(f'/ha/api/readiness/pacemaker/{readiness_cluster.cluster.id}/run',json={}).status_code==403
    assert readiness_cluster.calls==[]


def test_duplicate_audits_do_not_flood_the_operations_queue(product_client,readiness_cluster):
    url=f'/ha/api/readiness/pacemaker/{readiness_cluster.cluster.id}/run'
    assert product_client.post(url,json={}).status_code==202
    assert product_client.post(url,json={}).status_code==409
    assert OperationalAssessment.select().count()==1


def test_registered_witness_can_have_its_failure_domains_declared(product_client,product,readiness_cluster):
    witness=Server.create(server_id=44,hostname='Product witness',ip='192.0.2.99',group_id='1',cred_id=11)
    readiness_cluster.cluster.corosync_settings=json.dumps(dict(qdevice_server_id=witness.server_id));readiness_cluster.cluster.save()
    url=f'/ha/api/readiness/pacemaker/{readiness_cluster.cluster.id}'
    assert product_client.get(url).json['profile']['nodes'][-1]['name']=='Witness: Product witness'
    assert product_client.post(url+'/profile',json=dict(revision=0,domains={'11':dict(power='shared'),'44':dict(power='shared')})).status_code==200
    _row,result=run(product_client,readiness_cluster)
    assert next(c for c in result['checks'] if c['key']=='domain:power')['evidence']['shared']==['shared']


def test_real_node_observation_parses_quorum_tls_and_redacts_cib(product,readiness_cluster,monkeypatch):
    from app.modules.service.ha_readiness import pacemaker_node
    def remote(server):
        def command(args,**kwargs):
            if args[0]=='corosync-cmapctl':return 'totem.cluster_name (str) = product-ha'
            if args[0]=='cibadmin':return readiness_cluster.xml
            if args[0]=='python3':return 'b'*64
            if args[0]=='crm_mon':return '<pacemaker-result><summary><current_dc name="one" with_quorum="true"/></summary><nodes/><resources/></pacemaker-result>'
            if args[-1]=='-v':return 'QNetd host: 192.0.2.99:5403\nTLS active: Yes\n'
            return 'Flags: Quorate Qdevice\n 0 1 Qdevice\n'
        return SimpleNamespace(run=command)
    monkeypatch.setattr(audit,'Remote',remote)
    result=pacemaker_node(readiness_cluster.cluster,'one',product.server)
    assert result['quorum']['votes']==1 and result['witness']['tls']
    assert result['witness']['host']=='192.0.2.99:5403'


@pytest.mark.parametrize('attributes',['<instance_attributes id-ref="other"/>','<instance_attributes id="other"><rule id="r"/></instance_attributes>'])
def test_conditional_fencing_coverage_is_never_reported_static(attributes):
    xml='<cib><configuration><resources><primitive id="fence" class="stonith">'+attributes+'</primitive></resources></configuration></cib>'
    result=audit.fencing(xml,{'one','two'})
    assert result['state']=='warning' and result['evidence']['dynamic_or_conditional']


def test_keepalived_duplicate_vip_owner_is_not_healthy(product_client,product,readiness_cluster,monkeypatch):
    cluster=HaCluster.create(name='product-vrrp',group_id=1,syn_flood=0,description='Fixture')
    router=HaClusterRouter.create(cluster_id=cluster,default=1)
    for ident in (11,33):HaClusterSlave.create(cluster_id=cluster,server_id=ident,router_id=router)
    HaClusterVip.create(cluster_id=cluster,router_id=router,vip='192.0.2.100/24')
    monkeypatch.setattr(audit,'keepalived_node',lambda c,n,s:dict(id=s.server_id,name=n,digest='a'*64,active=True,addresses=['192.0.2.100'],includes=True))
    row=audit.enqueue('keepalived',cluster.id,1,product.admin.user_id)
    assert audit.execute(InstallationTasks.get_by_id(row.task_id))=='completed'
    result=audit.get_report(row.id,1)['report'];checks={c['key']:c for c in result['checks']}
    assert checks['vip-ownership']['state']=='fail' and checks['quorum']['state']=='not-applicable'
    assert checks['includes']['state']=='unknown' and result['last_verified_test'] is None


def test_assessment_history_remains_readable_after_atomic_key_rotation(product_client, readiness_cluster, monkeypatch):
    import os
    from cryptography.fernet import Fernet
    from rotate_credential_secret import rotate_credentials
    row, report=run(product_client,readiness_cluster)
    old=os.environ['ROXYWI_SECRET_PHRASE']; new=Fernet.generate_key().decode()
    monkeypatch.setenv('ROXYWI_OLD_SECRET_PHRASE',old)
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE',new)
    assert rotate_credentials()>0
    assert OperationalAssessment.get_by_id(row.id).result!=row.result
    assert audit.get_report(row.id,1)['report']==report
    response=product_client.get(f'/ha/api/readiness/pacemaker/{readiness_cluster.cluster.id}')
    assert response.status_code==200 and response.json['assessments'][0]['report']==report
    assert rotate_credentials()==0


def test_invalid_assessment_rolls_back_entire_key_rotation(product_client, readiness_cluster, monkeypatch):
    import os
    from cryptography.fernet import Fernet
    from rotate_credential_secret import rotate_credentials
    from app.modules.db.db_model import Cred
    row,_=run(product_client,readiness_cluster)
    credential=Cred.get_by_id(11); before=credential.password
    task=InstallationTasks.get_by_id(row.task_id); payload=task.operation_payload
    OperationalAssessment.update(result='fernet:invalid').where(OperationalAssessment.id==row.id).execute()
    monkeypatch.setenv('ROXYWI_OLD_SECRET_PHRASE',os.environ['ROXYWI_SECRET_PHRASE'])
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE',Fernet.generate_key().decode())
    with pytest.raises(RuntimeError):rotate_credentials()
    assert Cred.get_by_id(11).password==before
    assert InstallationTasks.get_by_id(task.id).operation_payload==payload


def keepalived_registration(product, monkeypatch):
    cluster=HaCluster.create(name='product-vrrp',group_id=1,description='Fixture')
    router=HaClusterRouter.create(cluster_id=cluster,default=1)
    for ident in (11,33):HaClusterSlave.create(cluster_id=cluster,server_id=ident,router_id=router)
    def observe(c,n,s):
        return dict(id=s.server_id,name=n,digest=('a' if s.server_id==11 else 'b')*64,
                    active=True,addresses=[],includes=False)
    monkeypatch.setattr(audit,'keepalived_node',observe)
    return cluster


def test_keepalived_missing_members_returns_actionable_error(product_client):
    cluster = HaCluster.create(name='Incomplete cluster', group_id=1, description='No registered nodes')
    response = product_client.post(f'/ha/api/readiness/keepalived/{cluster.id}/run', json={})
    assert response.status_code == 409
    assert response.json['error'] == 'A readiness audit requires 2–32 registered cluster members'
    assert not InstallationTasks.select().where(InstallationTasks.operation_type == 'ha-readiness').exists()


def test_duplicate_keepalived_names_cannot_hide_first_member_drift(product_client, product, readiness_cluster, monkeypatch):
    Server.update(hostname='same-name').where(Server.server_id.in_([11,33])).execute()
    cluster=keepalived_registration(product,monkeypatch)
    row=audit.enqueue('keepalived',cluster.id,1,product.admin.user_id)
    assert audit.execute(InstallationTasks.get_by_id(row.task_id))=='completed'
    first=audit.get_report(row.id,1)['report']
    check=next(c for c in first['checks'] if c['key']=='configuration')
    assert check['state']=='warning'
    assert check['evidence']['digests']=={'11':'a'*64,'33':'b'*64}
    audit.attest('keepalived',cluster.id,1,product.admin.user_id,audit.Attestation(
        kind='network-partition',result='passed',tested_at=utc_now(),note='Synthetic prior attestation',assessment_id=row.id))
    monkeypatch.setattr(audit,'keepalived_node',lambda c,n,s:dict(id=s.server_id,name=n,digest='b'*64,active=True,addresses=[],includes=False))
    row=audit.enqueue('keepalived',cluster.id,1,product.admin.user_id)
    assert audit.execute(InstallationTasks.get_by_id(row.task_id))=='completed'
    changed=audit.get_report(row.id,1)['report']
    assert first['fingerprint']!=changed['fingerprint']
    assert not changed['attestations'][0]['configuration_current']


@pytest.mark.parametrize('metadata', [
    '<meta_attributes id-ref="disabled"/>',
    '<meta_attributes id-ref="missing"/>',
    '<meta_attributes id="conditional"><rule id="r"/><nvpair name="target-role" value="Started"/></meta_attributes>',
    '<meta_attributes id="m"><nvpair id-ref="stopped-value"/></meta_attributes>',
])
def test_fencing_metadata_references_never_claim_static_coverage(metadata):
    xml=('<cib><configuration><resources><primitive id="one" class="stonith">'
         '<instance_attributes id="a"><nvpair name="pcmk_host_list" value="one two"/></instance_attributes>'
         '<meta_attributes id="disabled"><nvpair id="stopped-value" name="target-role" value="Stopped"/></meta_attributes>'
         '</primitive><primitive id="two" class="stonith">'
         '<instance_attributes id="b"><nvpair name="pcmk_host_list" value="one two"/></instance_attributes>'
         +metadata+'</primitive></resources></configuration></cib>')
    result=audit.fencing(xml,{'one','two'})
    assert result['state']=='warning'
    assert result['evidence']['coverage']=={'one':[],'two':[]}
    assert result['evidence']['dynamic_or_conditional']


def fencing_fixture(defaults='', metadata='', wrapper='{}'):
    resource=('<primitive id="fence" class="stonith">'
              '<instance_attributes id="hosts"><nvpair name="pcmk_host_list" value="one two"/></instance_attributes>'
              +metadata+'</primitive>')
    return '<cib><configuration><rsc_defaults>'+defaults+'</rsc_defaults><resources>'+wrapper.format(resource)+'</resources></configuration></cib>'


@pytest.mark.parametrize('name,disabled,enabled', [('target-role','Stopped','Started'),('is-managed','false','true')])
@pytest.mark.parametrize('override', [None,'enabled','disabled'])
def test_fencing_resource_defaults_and_explicit_overrides(name,disabled,enabled,override):
    defaults=f'<meta_attributes id="defaults"><nvpair name="{name}" value="{disabled}"/></meta_attributes>'
    value=enabled if override=='enabled' else disabled
    metadata='' if override is None else f'<meta_attributes id="resource"><nvpair name="{name}" value="{value}"/></meta_attributes>'
    result=audit.fencing(fencing_fixture(defaults,metadata),{'one','two'})
    covered=override=='enabled'
    assert result['state']==('configured' if covered else 'warning')
    assert result['evidence']['coverage']=={name:['fence'] if covered else [] for name in ('one','two')}
    assert not result['evidence']['dynamic_or_conditional']


@pytest.mark.parametrize('name,value', [('target-role','Stopped'),('is-managed','false')])
def test_fencing_unrelated_metadata_does_not_clear_disabled_default(name,value):
    defaults=f'<meta_attributes id="defaults"><nvpair name="{name}" value="{value}"/></meta_attributes>'
    metadata='<meta_attributes id="resource"><nvpair name="resource-stickiness" value="100"/></meta_attributes>'
    result=audit.fencing(fencing_fixture(defaults,metadata),{'one','two'})
    assert result['state']=='warning'
    assert result['evidence']['coverage']=={'one':[],'two':[]}


@pytest.mark.parametrize('name,enabled,disabled', [('target-role','Started','Stopped'),('is-managed','true','false')])
def test_fencing_explicit_disable_overrides_enabled_default(name,enabled,disabled):
    defaults=f'<meta_attributes id="defaults"><nvpair name="{name}" value="{enabled}"/></meta_attributes>'
    metadata=f'<meta_attributes id="resource"><nvpair name="{name}" value="{disabled}"/></meta_attributes>'
    result=audit.fencing(fencing_fixture(defaults,metadata),{'one','two'})
    assert result['state']=='warning'
    assert result['evidence']['coverage']=={'one':[],'two':[]}


@pytest.mark.parametrize('overrides,covered', [
    ('<nvpair name="target-role" value="Started"/>',False),
    ('<nvpair name="is-managed" value="true"/>',False),
    ('<nvpair name="target-role" value="Started"/><nvpair name="is-managed" value="true"/>',True),
])
def test_fencing_each_disabled_default_needs_its_own_override(overrides,covered):
    defaults=('<meta_attributes id="defaults"><nvpair name="target-role" value="Stopped"/>'
              '<nvpair name="is-managed" value="false"/></meta_attributes>')
    result=audit.fencing(fencing_fixture(defaults,'<meta_attributes id="resource">'+overrides+'</meta_attributes>'),{'one','two'})
    assert result['state']==('configured' if covered else 'warning')
    assert result['evidence']['coverage']=={name:['fence'] if covered else [] for name in ('one','two')}


@pytest.mark.parametrize('wrapper', ['group','clone'])
@pytest.mark.parametrize('override', [False,True])
def test_fencing_metadata_inheritance_prefers_nearest_resource(wrapper,override):
    defaults='<meta_attributes id="defaults"><nvpair name="is-managed" value="true"/></meta_attributes>'
    parent=('<'+wrapper+' id="parent"><meta_attributes id="parent-meta">'
            '<nvpair name="is-managed" value="false"/></meta_attributes>{}</'+wrapper+'>')
    metadata='<meta_attributes id="resource"><nvpair name="is-managed" value="true"/></meta_attributes>' if override else ''
    result=audit.fencing(fencing_fixture(defaults,metadata,parent),{'one','two'})
    assert result['state']==('configured' if override else 'warning')
    assert result['evidence']['coverage']=={name:['fence'] if override else [] for name in ('one','two')}


@pytest.mark.parametrize('defaults', [
    '<meta_attributes id-ref="missing"/>',
    '<meta_attributes id="defaults"><rule id="conditional"/><nvpair name="is-managed" value="true"/></meta_attributes>',
    '<meta_attributes id="defaults"><nvpair id-ref="missing"/></meta_attributes>',
    '<meta_attributes id="first"><nvpair name="is-managed" value="false"/></meta_attributes>'
    '<meta_attributes id="second"><nvpair name="is-managed" value="true"/></meta_attributes>',
    '<meta_attributes id="defaults"><nvpair name="is-managed" value="#default"/></meta_attributes>',
])
def test_fencing_unresolved_defaults_never_claim_static_coverage(defaults):
    result=audit.fencing(fencing_fixture(defaults),{'one','two'})
    assert result['state']=='warning'
    assert result['evidence']['coverage']=={'one':[],'two':[]}
    assert result['evidence']['dynamic_or_conditional']


def test_fencing_defaults_apply_independently_to_each_device():
    xml=fencing_fixture('<meta_attributes id="defaults"><nvpair name="is-managed" value="false"/></meta_attributes>',
                        '<meta_attributes id="resource"><nvpair name="is-managed" value="true"/></meta_attributes>')
    second=('<primitive id="inherited" class="stonith"><instance_attributes id="other-hosts">'
            '<nvpair name="pcmk_host_list" value="one two"/></instance_attributes></primitive>')
    result=audit.fencing(xml.replace('</resources>',second+'</resources>'),{'one','two'})
    assert result['state']=='configured'
    assert result['evidence']['coverage']=={'one':['fence'],'two':['fence']}


@pytest.mark.parametrize('provider',['pacemaker','keepalived'])
def test_reused_cluster_id_cannot_inherit_history_domains_attestations_or_queued_work(
        product_client,product,readiness_cluster,monkeypatch,provider):
    from app.modules.roxywi.exception import RoxywiResourceNotFound
    old=readiness_cluster.cluster if provider=='pacemaker' else keepalived_registration(product,monkeypatch)
    url=f'/ha/api/readiness/{provider}/{old.id}'
    assert product_client.post(url+'/profile',json=dict(revision=0,domains={'11':{'power':'old-location'}})).status_code==200
    row=audit.enqueue(provider,old.id,1,product.admin.user_id)
    assert audit.execute(InstallationTasks.get_by_id(row.task_id))=='completed'
    assert product_client.post(url+'/attest',json=dict(kind='fencing',result='passed',tested_at=utc_iso(utc_now()),
        note='Test evidence for original registration',assessment_id=row.id)).status_code==200
    queued=audit.enqueue(provider,old.id,1,product.admin.user_id)
    values={k:v for k,v in old.__data__.items() if k not in ('id','readiness_key')}
    old.delete_instance(recursive=True)
    replacement=type(old).create(**values)
    assert replacement.id==old.id and replacement.readiness_key!=old.readiness_key
    if provider=='keepalived':
        router=HaClusterRouter.create(cluster_id=replacement,default=1)
        for ident in (11,33):HaClusterSlave.create(cluster_id=replacement,server_id=ident,router_id=router)
    data=product_client.get(url).json
    assert data['assessments']==[] and data['profile']['domains']=={} and data['profile']['attestations']==[]
    assert data['profile']['revision']==0
    with pytest.raises(RoxywiResourceNotFound):audit.get_report(row.id,1)
    assert product_client.post(url+'/attest',json=dict(kind='fencing',result='passed',tested_at=utc_iso(utc_now()),
        note='Attempt to reuse previous evidence',assessment_id=row.id)).status_code==404
    assert audit.execute(InstallationTasks.get_by_id(queued.task_id))=='failed'
    assert product_client.post(url+'/profile',json=dict(revision=0,registration_key=old.readiness_key,domains={})).status_code==409
    assert product_client.post(url+'/profile',json=dict(revision=0,registration_key=replacement.readiness_key,domains={'11':{'power':'new'}})).status_code==200


def test_registration_migration_is_idempotent_and_does_not_guess_legacy_evidence_owner():
    import importlib
    from peewee import SqliteDatabase
    from playhouse.migrate import SqliteMigrator, migrate
    from app.modules.db.db_model import HaClusterService, HaClusterVirt, PacemakerEvent
    from app.modules.db import ha_cluster as ha_sql
    migration=importlib.import_module('app.modules.db.migrations.20261029040000_readiness_registration_identity')
    database=SqliteDatabase(':memory:', pragmas={'foreign_keys': 1})
    models=[HaCluster,PacemakerCluster,HaReadinessProfile,Server,HaClusterRouter,
            HaClusterSlave,HaClusterVip,HaClusterService,HaClusterVirt,PacemakerEvent]
    with database.bind_ctx(models,bind_refs=False,bind_backrefs=False):
        database.create_tables(models)
        one=PacemakerCluster.create(name='legacy-pcmk',group_id=1)
        two=HaCluster.create(name='legacy-vrrp',group_id=1,description='')
        server=Server.create(hostname='Master',ip='192.0.2.1',group_id='1')
        router=HaClusterRouter.create(cluster_id=two,default=1)
        member=HaClusterSlave.create(cluster_id=two,router_id=router,server_id=server,master=1,eth='ens3')
        vip=HaClusterVip.create(cluster_id=two,router_id=router,vip='192.0.2.100')
        HaClusterVirt.create(cluster_id=two,virt_id=server,vip_id=vip)
        HaClusterService.create(cluster_id=two,service_id='1')
        event=PacemakerEvent.create(cluster=one,user_id=1,action='Created cluster',status='completed')
        old=HaReadinessProfile.create(group_id=1,provider='pacemaker',cluster_id=one.id,
            domains='{"11":{"power":"legacy"}}',attestations='[{"result":"passed"}]')
        migrator=SqliteMigrator(database)
        for index in database.get_indexes('ha_readiness_profiles'):
            if index.unique:migrate(migrator.drop_index('ha_readiness_profiles',index.name))
        for table,field in [('ha_clusters','readiness_key'),('pacemaker_clusters','readiness_key'),
                            ('ha_readiness_profiles','registration_key')]:
            database.execute_sql(f'ALTER TABLE {table} DROP COLUMN {field}')
        migrate(migrator.add_index('ha_readiness_profiles',('group_id','provider','cluster_id'),unique=True))
        migration.up()
        key=PacemakerCluster.get_by_id(one.id).readiness_key
        assert len(key)==32 and key!=HaCluster.get_by_id(two.id).readiness_key
        assert HaReadinessProfile.get_by_id(old.id).registration_key==''
        assert HaReadinessProfile.get_by_id(old.id).domains==old.domains
        migration.up()
        assert PacemakerCluster.get_by_id(one.id).readiness_key==key
        assert HaClusterRouter.get_by_id(router.id).default==1
        assert HaClusterSlave.get_by_id(member.id).server_id_id==server.server_id
        assert HaClusterVip.get_by_id(vip.id).vip=='192.0.2.100'
        assert HaClusterVirt.select().count()==1 and HaClusterService.select().count()==1
        assert PacemakerEvent.get_by_id(event.id).action=='Created cluster'
        # Existing HA screens expect master and interface at these tuple offsets.
        rows=list(ha_sql.select_cluster_slaves(two.id,router.id))
        assert rows[0][:3]==(server.server_id,'Master','192.0.2.1')
        assert rows[0][31:34]==(1,'ens3',router.id)
        assert list(ha_sql.select_cluster_master_slaves(two.id,1,router.id))==rows
        assert list(ha_sql.select_cluster_master_slaves(two.id,2,router.id))==[]
        assert database.execute_sql('PRAGMA foreign_keys').fetchone()==(1,)
        assert database.execute_sql('PRAGMA foreign_key_check').fetchall()==[]
        HaReadinessProfile.create(group_id=1,provider='pacemaker',cluster_id=one.id,registration_key=key)
    database.close()


def test_deleted_registration_cannot_receive_a_late_attestation(product_client,product,readiness_cluster,monkeypatch):
    cluster=readiness_cluster.cluster
    row,_=run(product_client,readiness_cluster)
    original=audit.get_report
    def replaced(ident,group):
        report=original(ident,group)
        values={k:v for k,v in cluster.__data__.items() if k not in ('id','readiness_key')}
        cluster.delete_instance(recursive=True)
        replacement=PacemakerCluster.create(**values)
        assert replacement.id==cluster.id
        return report
    monkeypatch.setattr(audit,'get_report',replaced)
    body=audit.Attestation(kind='fencing',result='passed',tested_at=utc_now(),note='Original external test',assessment_id=row.id)
    from app.modules.roxywi.exception import RoxywiConflictError
    with pytest.raises(RoxywiConflictError):audit.attest('pacemaker',cluster.id,1,product.admin.user_id,body)
    assert audit.public_profile('pacemaker',cluster.id,1)['attestations']==[]


def test_observed_maintenance_proof_is_bound_to_current_registration(product, readiness_cluster):
    from app.modules.operations.queue import serialize_operation_payload
    cluster=readiness_cluster.cluster
    _cluster,nodes=audit.subject('pacemaker',cluster.id,1)
    proof=dict(source='observed-drain-and-return',plan_id=9,fingerprint='old-configuration')
    OperationalAssessment.create(group_id=1,user_id=product.admin.user_id,kind='ha-maintenance',
        subject=audit.subject_key('pacemaker',cluster),
        result=serialize_operation_payload(dict(verified_test=proof)))
    report=audit.collect('pacemaker',cluster,nodes,None)
    assert report['last_verified_test']['plan_id']==9
    assert not report['last_verified_test']['configuration_current']
    values={k:v for k,v in cluster.__data__.items() if k not in ('id','readiness_key')}
    cluster.delete_instance(recursive=True)
    replacement=PacemakerCluster.create(**values)
    assert replacement.id==cluster.id and replacement.readiness_key!=cluster.readiness_key
    _cluster,nodes=audit.subject('pacemaker',replacement.id,1)
    assert audit.collect('pacemaker',replacement,nodes,None)['last_verified_test'] is None



@pytest.mark.parametrize('status,task_id', [
    ('draining',None),('ready',None),('unknown',None),('resuming',None),
    ('return-reviewed',None),('draft',42),
])
def test_registration_migration_rejects_legacy_busy_plans_before_schema_changes(status,task_id):
    import importlib
    from peewee import SqliteDatabase
    migration=importlib.import_module('app.modules.db.migrations.20261029040000_readiness_registration_identity')
    database=SqliteDatabase(':memory:')
    models=[HaCluster,PacemakerCluster,HaReadinessProfile]
    with database.bind_ctx(models,bind_refs=False,bind_backrefs=False):
        database.create_tables(models)
        missing=[('ha_clusters','readiness_key'),('pacemaker_clusters','readiness_key'),
                 ('ha_readiness_profiles','registration_key')]
        # Remove the index first because it references registration_key.
        for index in database.get_indexes('ha_readiness_profiles'):
            if index.unique:database.execute_sql(f'DROP INDEX {index.name}')
        for table,field in missing:
            database.execute_sql(f'ALTER TABLE {table} DROP COLUMN {field}')
        database.execute_sql('CREATE TABLE ha_maintenance_plans (status TEXT, active_task_id INTEGER)')
        database.execute_sql('INSERT INTO ha_maintenance_plans (status,active_task_id) VALUES (?,?)',(status,task_id))
        with pytest.raises(RuntimeError,match='approved return before upgrading'):
            migration.up()
        for table,field in missing:
            assert field not in {column.name for column in database.get_columns(table)}
        assert database.execute_sql('SELECT status,active_task_id FROM ha_maintenance_plans').fetchone()==(status,task_id)
        database.execute_sql("UPDATE ha_maintenance_plans SET status='completed',active_task_id=NULL")
        migration.up()
        for table,field in missing:
            assert field in {column.name for column in database.get_columns(table)}
        # With identities already present, a later active plan must not block a repeat.
        database.execute_sql("UPDATE ha_maintenance_plans SET status='ready'")
        migration.up()
    database.close()



@pytest.mark.parametrize('provider',['keepalived','pacemaker'])
@pytest.mark.parametrize('status,task_id', [('ready',None),('draft',42)])
def test_maintenance_guard_migration_rejects_unbound_plans_after_identity_migration(monkeypatch,provider,status,task_id):
    import importlib
    from cryptography.fernet import Fernet
    from peewee import SqliteDatabase
    from app.modules.db.db_model import HaMaintenancePlan
    from app.modules.operations.queue import serialize_operation_payload
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE',Fernet.generate_key().decode())
    migration=importlib.import_module('app.modules.db.migrations.20261029050000_maintenance_registration_guard')
    database=SqliteDatabase(':memory:')
    with database.bind_ctx([HaCluster,PacemakerCluster,HaMaintenancePlan],bind_refs=False,bind_backrefs=False):
        database.create_tables([HaCluster,PacemakerCluster,HaMaintenancePlan])
        model=HaCluster if provider=='keepalived' else PacemakerCluster
        cluster=model.create(name='already-migrated',group_id=1,description='')
        plan=HaMaintenancePlan.create(group_id=1,user_id=1,provider=provider,cluster_id=cluster.id,
            server_id=11,status=status,active_task_id=task_id,payload=serialize_operation_payload(dict(events=[])))
        before=plan.payload
        with pytest.raises(RuntimeError,match='approved return before upgrading'):
            migration.up()
        assert HaMaintenancePlan.get_by_id(plan.id).payload==before
        assert model.get_by_id(cluster.id).readiness_key==cluster.readiness_key
        # Only a previously recorded matching identity allows an active plan.
        bound=serialize_operation_payload(dict(registration_key=cluster.readiness_key))
        HaMaintenancePlan.update(payload=bound).where(HaMaintenancePlan.id==plan.id).execute()
        migration.up()
        migration.up()
        assert HaMaintenancePlan.get_by_id(plan.id).payload==bound
    database.close()



@pytest.mark.parametrize('payload', ['fernet:invalid','not-json','[]','{"registration_key":"wrong"}'])
def test_maintenance_guard_migration_invalid_active_payload_is_safe_and_completed_legacy_allowed(monkeypatch,payload):
    import importlib
    from cryptography.fernet import Fernet
    from peewee import SqliteDatabase
    from app.modules.db.db_model import HaMaintenancePlan
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE',Fernet.generate_key().decode())
    migration=importlib.import_module('app.modules.db.migrations.20261029050000_maintenance_registration_guard')
    database=SqliteDatabase(':memory:')
    with database.bind_ctx([HaCluster,PacemakerCluster,HaMaintenancePlan],bind_refs=False,bind_backrefs=False):
        database.create_tables([HaCluster,PacemakerCluster,HaMaintenancePlan])
        cluster=PacemakerCluster.create(name='current',group_id=1)
        plan=HaMaintenancePlan.create(group_id=1,user_id=1,provider='pacemaker',cluster_id=cluster.id,
            server_id=11,status='ready',payload=payload)
        with pytest.raises(RuntimeError) as error:
            migration.up()
        assert str(error.value)==migration.ERROR
        assert payload not in str(error.value)
        assert HaMaintenancePlan.get_by_id(plan.id).payload==payload
        HaMaintenancePlan.update(status='completed').where(HaMaintenancePlan.id==plan.id).execute()
        migration.up()
        assert HaMaintenancePlan.get_by_id(plan.id).payload==payload
    database.close()

