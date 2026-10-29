"""Passive certificate updates never manufacture a running cluster resource."""
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from app.modules.config import haproxy_discovery
from app.modules.service import certificate_cluster, certificates
from app.scripts import certificate_cluster_remote as cluster, certificate_remote as remote
from tests.fixtures.certificate_runtime import make_pem


CIB='<cib><configuration><resources><primitive id="proxy" class="systemd" type="haproxy"/></resources></configuration></cib>'
STATUS='''<pacemaker-result><summary><current_dc with_quorum="true"/></summary><nodes>
<node name="first" online="true" unclean="false"/><node name="second" online="true" unclean="false"/>
</nodes><resources><resource id="proxy" managed="true" failed="false" blocked="false" active="true"><node name="first"/></resource></resources></pacemaker-result>'''


def proof(node='second'):
    config=cluster.parse(CIB).find('configuration')
    return dict(cluster='fixture',node=node,cib=cluster.configuration_digest(CIB),
                declaration=cluster.declaration(config.find('./resources/primitive'),config),mode='passive' if node=='second' else 'active')


@pytest.mark.parametrize('node,expected',[('first','active'),('second','passive')])
def test_resource_placement_is_observed(node,expected):
    assert cluster.role(cluster.parse(STATUS),'proxy',node)==expected


@pytest.mark.parametrize('before,after',[
    ('with_quorum="true"','with_quorum="false"'),('online="true"','online="false"'),
    ('unclean="false"','unclean="true"'),('managed="true"','managed="false"'),
    ('failed="false"','failed="true"'),('blocked="false"','blocked="true"'),('active="true"','active="false"')])
def test_unproved_or_failed_cluster_is_never_staged(before,after):
    with pytest.raises(ValueError):cluster.role(cluster.parse(STATUS.replace(before,after)),'proxy','second')


def test_matching_requires_one_exact_binding_and_rejects_conditional_rules():
    config=cluster.parse(CIB).find('configuration')
    settings=dict(docker=False,service_unit='haproxy.service',config_path='/etc/haproxy/haproxy.cfg')
    assert certificate_cluster.matching(config,settings,1)['id']=='proxy'
    import xml.etree.ElementTree as ET
    config.find('resources').append(ET.fromstring('<primitive id="another" class="systemd" type="haproxy"/>'))
    with pytest.raises(Exception,match='exactly one'):certificate_cluster.matching(config,settings,1)
    resource=config.find('./resources/primitive')
    resource.append(ET.fromstring('<instance_attributes id="dynamic"><rule id="r"/></instance_attributes>'))
    with pytest.raises(ValueError,match='Conditional'):cluster.declaration(resource,config)


@pytest.fixture
def passive(tmp_path,monkeypatch):
    old,new=make_pem(1),make_pem(2)
    certs=tmp_path/'certs';certs.mkdir();file=certs/'site.pem';file.write_text(old)
    main=tmp_path/'haproxy.cfg'
    main.write_text('global\ndefaults\n mode tcp\n timeout connect 1s\n timeout client 1s\n timeout server 1s\nfrontend tls\n bind 127.0.0.1:10443 ssl crt '+str(file)+'\n')
    data=dict(cert_dir=str(certs),pem_name='site.pem',config_path=str(main),root=str(tmp_path),
        service_unit='haproxy',docker=False,runtime_port=1999,apply_mode='disk_stage',
        cluster_proof=proof(),transaction='passive-test',pem=new,validation=dict(service='haproxy',action='check',
        target=str(main),main=str(main),root=str(tmp_path),sources=[str(main)],container=''))
    monkeypatch.setattr(remote,'ROOT',tmp_path/'journals')
    def metadata(argv,**kwargs):
        if argv[0]=='cibadmin':return CIB
        if argv[0]=='crm_mon':return STATUS
        if argv[0]=='corosync-cmapctl':return 'totem.cluster_name (str) = fixture'
        if argv[0]=='systemctl':return 'ActiveState=inactive\nMainPID=0'
        if argv[0]=='pgrep':return ''
        raise AssertionError('Unexpected cluster action: '+repr(argv))
    monkeypatch.setattr(cluster,'run',metadata)
    monkeypatch.setattr(haproxy_discovery,'systemd_sources',lambda _:([str(main)],[],False))
    monkeypatch.setattr(remote,'runtime_request',lambda *_:pytest.fail('A passive member must not use Runtime API'))
    if not shutil.which('haproxy'):
        monkeypatch.setattr(cluster,'validate_offline',lambda data:True)
        monkeypatch.setattr(remote.passive,'validate_material',lambda *args:None)
    return SimpleNamespace(data=data,file=file,main=main,old=old,new=new)


@pytest.mark.parametrize('phase',['commit','rollback'])
def test_passive_stage_is_journaled_validated_and_recoverable(passive,phase):
    item=remote.passive.inspect(passive.data,remote)
    data=dict(passive.data,passive_binding=item['binding'],expected_revision=item['revision'])
    assert remote.deploy(data)['verification']=='disk-staged'
    assert passive.file.read_text()==passive.new
    # Redelivery after a lost deployment acknowledgement keeps the same journal.
    remote.deploy(data)
    finished=dict(data,operation=phase,expected_digest=hashlib.sha256(passive.new.encode()).hexdigest())
    assert remote.finish_deployment(finished)['verification']=='disk-staged'
    assert passive.file.read_text()==(passive.new if phase=='commit' else passive.old)
    assert not list(remote.ROOT.rglob('pending.json'))
    assert remote.finish_deployment(finished)['verification']=='disk-staged'


def test_unchanged_candidate_rechecks_offline_startup(passive,monkeypatch):
    calls=[]
    monkeypatch.setattr(cluster,'validate_offline',lambda data:calls.append(data))
    remote.passive.inspect(dict(passive.data,verify_passive_digest=hashlib.sha256(passive.old.encode()).hexdigest()),remote)
    assert len(calls)==1


@pytest.mark.parametrize('mutation',['config','file','placement','cib'])
def test_external_changes_are_rejected_before_overwrite(passive,mutation,monkeypatch):
    initial=remote.passive.inspect(passive.data,remote)
    if mutation=='config':passive.main.write_text(passive.main.read_text()+'# changed\n')
    elif mutation=='file':passive.file.write_text(make_pem(3))
    elif mutation=='placement':
        original=cluster.run
        monkeypatch.setattr(cluster,'run',lambda argv,**kw:STATUS.replace('name="first"/></resource>','name="second"/></resource>') if argv[0]=='crm_mon' else original(argv,**kw))
    else:
        original=cluster.run
        monkeypatch.setattr(cluster,'run',lambda argv,**kw:CIB.replace('id="proxy"','id="changed"') if argv[0]=='cibadmin' else original(argv,**kw))
    baseline=passive.file.read_bytes()
    with pytest.raises(ValueError):remote.deploy(dict(passive.data,passive_binding=initial['binding'],expected_revision=initial['revision']))
    assert passive.file.read_bytes()==baseline


def test_unknown_file_blocks_rollback_and_preserves_recovery_journal(passive):
    remote.deploy(passive.data)
    outsider=make_pem(3);passive.file.write_text(outsider)
    with pytest.raises(ValueError,match='unknown file'):remote.finish_deployment(dict(passive.data,operation='rollback'))
    assert passive.file.read_text()==outsider and list(remote.ROOT.rglob('pending.json'))


def test_noop_commit_requires_file_receipt_and_offline_validation(passive):
    remote.deploy(passive.data)
    final=dict(passive.data,operation='commit',expected_digest=hashlib.sha256(passive.new.encode()).hexdigest())
    remote.finish_deployment(final)
    passive.file.write_text(passive.old)
    with pytest.raises(remote.CertificateFailure,match='verification_failed'):remote.finish_deployment(final)


def test_passive_context_does_not_require_running_startup_discovery(passive,monkeypatch):
    server=SimpleNamespace(ip='192.0.2.2')
    monkeypatch.setattr(certificates,'deployment_settings',lambda s,n,**kw:dict(passive.data) if kw['verify_startup'] is False else pytest.fail('Passive node must not use live discovery'))
    calls=[]
    def request(server,data):
        calls.append(data['operation'])
        return cluster.context(data) if data['operation']=='passive-context' else remote.passive.inspect(data,remote)
    monkeypatch.setattr(certificates,'remote',request)
    settings,item=certificates.passive_inspection(server,'site.pem',proof())
    assert calls==['passive-context','passive-inspect'] and item['certificate']['fingerprint']
    assert settings['apply_mode']=='disk_stage' and item['can_stage']


@pytest.mark.skipif(not shutil.which('haproxy'),reason='Real HAProxy binary required')
def test_invalid_pem_never_replaces_passive_file(passive):
    with pytest.raises(RuntimeError):remote.deploy(dict(passive.data,pem='invalid material'))
    assert passive.file.read_text()==passive.old


@pytest.mark.parametrize('loaded_candidate',[False,True])
def test_staged_member_that_becomes_active_requires_observed_runtime_certificate(passive,monkeypatch,loaded_candidate):
    remote.deploy(passive.data)
    original=cluster.run
    monkeypatch.setattr(cluster,'run',lambda argv,**kw:STATUS.replace('name="first"/></resource>','name="second"/></resource>') if argv[0]=='crm_mon' else original(argv,**kw))
    monkeypatch.setattr(remote,'runtime_certificate',lambda data:dict(fingerprint=remote.pem_fingerprint(passive.new if loaded_candidate else passive.old)))
    active=dict(passive.data,operation='commit',cluster_proof=dict(passive.data['cluster_proof'],mode='active'))
    if loaded_candidate:
        assert remote.finish_deployment(active)['verification']=='runtime'
        assert not list(remote.ROOT.rglob('pending.json'))
    else:
        with pytest.raises(remote.CertificateFailure):remote.finish_deployment(active)
        assert list(remote.ROOT.rglob('pending.json'))


def test_clone_and_template_bindings_remain_exact():
    cloned=STATUS.replace('id="proxy"','id="proxy:0"')
    assert cluster.role(cluster.parse(cloned),'proxy','first')=='active'
    config=cluster.parse('''<configuration><resources><template id="t" class="ocf" provider="heartbeat" type="podman">
    <instance_attributes id="a"><nvpair name="image" value="local-image"/></instance_attributes></template>
    <primitive id="proxy" template="t"><instance_attributes id-ref="a"/></primitive></resources></configuration>''')
    declared=cluster.declaration(config.find('./resources/primitive'),config)
    assert declared['type']=='podman' and declared['parameters']==dict(image='local-image')


def test_removed_quadlet_uses_only_static_local_definition(passive,tmp_path,monkeypatch):
    unit=tmp_path/'proxy.container'
    unit.write_text('[Container]\nImage=local-image\nUser=0\nGroup=root\nContainerName=proxy\nVolume='+str(tmp_path)+':/fixture\nExec=haproxy -W -f /fixture/haproxy.cfg\n')
    checked=[]
    monkeypatch.setattr(cluster.runtime,'verify_unit',lambda spec,name:checked.append((spec,name)))
    original=cluster.run
    monkeypatch.setattr(cluster,'run',lambda argv,**kwargs:str(unit) if 'SourcePath' in ' '.join(argv) else original(argv,**kwargs))
    settings=dict(passive.data,docker=True,container='proxy',container_runtime=dict(engine='podman',owner='root',unit='proxy.service'))
    monkeypatch.setattr(cluster,'declared_container',lambda data:data['cluster_proof']['declaration'])
    declaration=cluster.quadlet_container(settings)
    assert checked and declaration['type']=='podman'
    assert declaration['parameters']['image']=='local-image'
    for option in ('PodmanArgs=--privileged','EnvironmentFile=/secret','Exec=haproxy -f %h/haproxy.cfg','User=1000','Group=1000'):
        unit.write_text('[Container]\nImage=local-image\n'+option+'\n')
        with pytest.raises(ValueError):cluster.quadlet_container(settings)


def test_offline_validator_reads_ssh_owned_files_without_relaxing_host_permissions(tmp_path,monkeypatch):
    calls=[]
    def execute(argv,**kwargs):
        calls.append(argv)
        environment=Path(argv[argv.index('--env-file')+1])
        assert environment.stat().st_mode&0o777==0o600
        assert environment.read_text()=='FIXTURE_SECRET=not-in-argv\n'
        assert 'not-in-argv' not in str(argv)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(cluster.subprocess,'run',execute)
    record=dict(Image='sha256:'+'a'*64,Config=dict(Env=['FIXTURE_SECRET=not-in-argv']),
        Mounts=[dict(Type='bind',Source=str(tmp_path),Destination='/config')])
    cluster.run_validator(dict(container_runtime=dict(engine='podman')),record,['-f','/config/haproxy.cfg'])
    args=calls[0]
    assert args[args.index('--network')+1]=='none' and '--read-only' in args
    assert args[args.index('--cap-drop')+1]=='ALL'
    assert [args[index+1] for index,value in enumerate(args[:-1]) if value=='--cap-add']==['DAC_READ_SEARCH']
    assert all(args[index+1].endswith(',readonly') for index,value in enumerate(args[:-1]) if value=='--mount')
