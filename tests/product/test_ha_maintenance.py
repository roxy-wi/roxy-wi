import copy
import json
from types import SimpleNamespace
import pytest
from playhouse.shortcuts import model_to_dict
from tests.product.test_ha_readiness import readiness_cluster
from app.modules.common.time import utc_now
from app.modules.db.db_model import (HaMaintenancePlan,InstallationTasks,ConfigChange,User,UserGroups,
    PacemakerCluster,OperationalAssessment,Server,HaCluster,HaClusterRouter,HaClusterSlave,HaClusterVip)
from app.modules.operations.queue import deserialize_operation_payload as unseal
from app.modules.service import ha_maintenance as maintenance,ha_readiness as audit
from app.modules.pacemaker import service,operations
from app.modules.roxywi.exception import RoxywiValidationError


@pytest.fixture
def maintenance_cluster(product,readiness_cluster,monkeypatch,app):
    values=model_to_dict(product.admin);values.pop('user_id');values.update(username='reviewer',email='reviewer@example.test',role_id='2')
    reviewer=User.create(**values);UserGroups.create(user_id=reviewer.user_id,user_group_id=1,user_role_id=2)
    state=SimpleNamespace(cluster=readiness_cluster.cluster,reviewer=reviewer,sessions=0,commands=[],
        resource_missing=False,configuration='a'*64,fail_command=False)
    state.live=dict(quorate=True,failures=0,source='one',quorum_details=dict(configured=True,votes=1,two_node=False),
        nodes=[dict(name=n,online='true',standby='false',unclean='false') for n in ('one','two')],
        resources=[dict(id='vip',target_id='vip',resource_agent='ocf:heartbeat:IPaddr2',active='true',managed='true',failed='false',blocked='false',nodes=['one'])])
    def view(cluster,target,returning=False):
        predicted=copy.deepcopy(state.live)
        for node in predicted['nodes']:
            if node['name']==target:node['standby']='false' if returning else 'true'
        for resource in predicted['resources']:resource['nodes']=['two']
        return dict(fingerprint=state.configuration,before=copy.deepcopy(state.live),predicted=predicted,
                    quorum=dict(current=3,member=1,remaining=2,required=2),vips=['192.0.2.100'])
    def run(args,**kwargs):
        state.commands.append(args)
        if state.fail_command:raise RuntimeError('SECRET REMOTE ERROR')
        if args[0]=='crm_standby':
            for node in state.live['nodes']:
                if node['name']==args[2]:node['standby']='true' if args[-1]=='on' else 'false'
            state.live['resources'][0]['nodes']=['two']
        return ''
    monkeypatch.setattr(maintenance,'pm_view',view)
    monkeypatch.setattr(service,'connection',lambda _:(SimpleNamespace(run=run),readiness_cluster.xml))
    monkeypatch.setattr(service,'status',lambda _:copy.deepcopy(state.live))
    monkeypatch.setattr(maintenance,'connections',lambda *_:state.sessions)
    monkeypatch.setattr('app.modules.pacemaker.witness_migration.verify',lambda *_:None)
    observe=maintenance.observe
    monkeypatch.setattr(maintenance,'observe',lambda *a,**kw:observe(*a,**dict(kw,seconds=0)))
    yield state


def create(product_client,state):
    response=product_client.post('/ha/api/maintenance',json=dict(provider='pacemaker',cluster_id=state.cluster.id,
        server_id=11,title='Maintain product node',capacity_confirmed=True,capacity_evidence='Load test with one surviving node passed'))
    assert response.status_code==201,response.text
    return HaMaintenancePlan.get_by_id(response.json['data']['id'])


@pytest.mark.parametrize('title,evidence', [('OS', '#7'), ('x', 'y')])
def test_short_maintenance_notes_are_accepted(product_client, maintenance_cluster, title, evidence):
    response = product_client.post('/ha/api/maintenance', json=dict(
        provider='pacemaker', cluster_id=maintenance_cluster.cluster.id, server_id=11,
        title=title, capacity_confirmed=True, capacity_evidence=evidence,
    ))
    assert response.status_code == 201, response.text
    assert response.json['data']['title'] == title
    assert response.json['data']['capacity_evidence'] == evidence


@pytest.mark.parametrize('field,value', [
    ('title', ''), ('title', '  '), ('title', 'x' * 256),
    ('capacity_evidence', ''), ('capacity_evidence', ' \n '),
    ('capacity_evidence', 'x' * 2001), ('capacity_confirmed', False),
])
def test_maintenance_still_requires_notes_and_capacity_confirmation(
    product_client, maintenance_cluster, field, value,
):
    body = dict(provider='pacemaker', cluster_id=maintenance_cluster.cluster.id, server_id=11,
                title='OS', capacity_confirmed=True, capacity_evidence='#7')
    body[field] = value
    response = product_client.post('/ha/api/maintenance', json=body)
    assert response.status_code == 400, response.text
    assert HaMaintenancePlan.select().count() == 0


@pytest.mark.parametrize('restriction', [None, 'disabled', 'service', 'role', 'group'])
def test_approval_guidance_names_only_eligible_other_administrators(
    product_client, product, maintenance_cluster, restriction,
):
    row = create(product_client, maintenance_cluster)
    reviewer = maintenance_cluster.reviewer
    if restriction == 'disabled':
        User.update(enabled=0).where(User.user_id == reviewer.user_id).execute()
    elif restriction == 'service':
        User.update(user_services='1 2 3 4 6').where(User.user_id == reviewer.user_id).execute()
    elif restriction == 'role':
        UserGroups.update(user_role_id=3).where(UserGroups.user_id == reviewer.user_id).execute()
    elif restriction == 'group':
        UserGroups.update(user_group_id=2).where(UserGroups.user_id == reviewer.user_id).execute()
    response = product_client.get('/ha/api/maintenance')
    assert response.status_code == 200, response.text
    plan = response.json['data'][0]
    assert plan['user_id'] == product.admin.user_id and plan['created_by'] == 'admin'
    eligible = {user['id']: user['name'] for user in plan['approvers']}
    assert product.admin.user_id not in eligible
    assert (reviewer.user_id in eligible) is (restriction is None)
    if restriction is None:
        assert eligible[reviewer.user_id] == 'reviewer'
    change = product_client.get(f'/changes/api/{row.change_id}')
    assert change.status_code == 200, change.text
    assert change.json['data']['maintenance'] == plan


def step(product_client,row,action,expected='completed'):
    response=product_client.post(f'/ha/api/maintenance/{row.id}/{action}',json={})
    assert response.status_code==202,response.text
    task=InstallationTasks.get_by_id(response.json['task_id'])
    assert operations.execute(task)==expected
    return HaMaintenancePlan.get_by_id(row.id)


def approve(app,row,reviewer):
    client=app.test_client();response=client.post('/login',json=dict(login=reviewer.username,**{'pass':'TestBootstrapPassword!','next':'/changes'}))
    assert response.status_code==200,response.text
    client.environ_base['HTTP_X_CSRF_TOKEN']=client.get_cookie('csrf_access_token').value
    response=client.post(f'/changes/api/{row.change_id}/approve',json={})
    assert response.status_code==200,response.text
    return client


def test_review_approval_drain_handover_and_reviewed_return(product_client,product,maintenance_cluster,app):
    row=create(product_client,maintenance_cluster)
    row=step(product_client,row,'review')
    assert row.status=='reviewed' and ConfigChange.get_by_id(row.change_id).status=='pending_approval'
    assert maintenance_cluster.commands==[]
    assert product_client.post(f'/changes/api/{row.change_id}/approve',json={}).status_code==403
    assert product_client.post(f'/ha/api/maintenance/{row.id}/drain',json={}).status_code==409
    reviewer=approve(app,row,maintenance_cluster.reviewer)
    assert product_client.post(f'/changes/api/{row.change_id}/deploy',json={}).status_code==400
    row=step(product_client,row,'drain')
    assert row.status=='ready' and unseal(row.payload)['drained_at']
    assert maintenance_cluster.commands==[['crm_standby','--node','one','--update','on']]
    assert json.loads(PacemakerCluster.get_by_id(row.cluster_id).corosync_settings)['node_maintenance']==row.id
    assert product_client.delete(f'/pacemaker/api/{row.cluster_id}').status_code==409
    assert product_client.post(f'/changes/api/{row.change_id}/cancel',json={}).status_code==409
    row=step(product_client,row,'review-return')
    assert row.status=='return-reviewed' and ConfigChange.get_by_id(row.change_id).approved_by is None
    approve(app,row,maintenance_cluster.reviewer)
    row=step(product_client,row,'resume')
    assert row.status=='completed' and 'node_maintenance' not in json.loads(PacemakerCluster.get_by_id(row.cluster_id).corosync_settings)
    proof=unseal(OperationalAssessment.get_by_id(row.assessment_id).result)['verified_test']
    assert proof['source']=='observed-drain-and-return' and proof['drained_at']
    _cluster,nodes=audit.subject('pacemaker',maintenance_cluster.cluster.id,1)
    report=audit.collect('pacemaker',maintenance_cluster.cluster,nodes,None)
    assert report['last_verified_test']['plan_id']==row.id


@pytest.mark.parametrize('problem',['sessions','failed-command','configuration','approver-disabled'])
def test_uncertain_or_stale_drain_never_hands_over_the_node(product_client,maintenance_cluster,app,problem):
    row=step(product_client,create(product_client,maintenance_cluster),'review');approve(app,row,maintenance_cluster.reviewer)
    if problem=='sessions':maintenance_cluster.sessions=2
    elif problem=='failed-command':maintenance_cluster.fail_command=True
    elif problem=='configuration':maintenance_cluster.configuration='b'*64
    else:User.update(enabled=0).where(User.user_id==maintenance_cluster.reviewer.user_id).execute()
    row=step(product_client,row,'drain',expected='failed')
    assert row.status!='ready' and not unseal(row.payload).get('drained_at')
    assert 'SECRET REMOTE ERROR' not in json.dumps(maintenance.public(row))
    if problem in ('configuration','approver-disabled'):assert not maintenance_cluster.commands
    else:assert row.status=='unknown'


def test_drain_can_be_verified_later_without_replaying_the_mutation(product_client,maintenance_cluster,app):
    row=step(product_client,create(product_client,maintenance_cluster),'review');approve(app,row,maintenance_cluster.reviewer)
    maintenance_cluster.sessions=1
    row=step(product_client,row,'drain',expected='failed')
    before=list(maintenance_cluster.commands);maintenance_cluster.sessions=0
    row=step(product_client,row,'verify')
    assert row.status=='ready' and maintenance_cluster.commands==before


def test_another_node_cannot_be_drained_while_one_is_handed_over(product_client,maintenance_cluster,app):
    row=step(product_client,create(product_client,maintenance_cluster),'review');approve(app,row,maintenance_cluster.reviewer)
    row=step(product_client,row,'drain')
    other=create(product_client,maintenance_cluster)
    assert product_client.post(f'/ha/api/maintenance/{other.id}/review',json={}).status_code==409
    assert len(maintenance_cluster.commands)==1


def test_queued_identity_drift_revoked_actor_and_other_groups_are_rejected(product_client,product,maintenance_cluster):
    row=create(product_client,maintenance_cluster)
    response=product_client.post(f'/ha/api/maintenance/{row.id}/review',json={});assert response.status_code==202
    Server.update(ip='192.0.2.77').where(Server.server_id==11).execute()
    assert operations.execute(InstallationTasks.get_by_id(response.json['task_id']))=='failed'
    assert not maintenance_cluster.commands
    row.group_id=2;row.save()
    assert product_client.post(f'/ha/api/maintenance/{row.id}/review',json={}).status_code==404


@pytest.mark.parametrize('text,nodeid',[
    ('Total votes: 2\nQuorum: 2\n0x00000001 1 A,V,NMW one\n',1),
    ('Total votes: 3\nQuorum: 2\n0x00000002 2 one\n',2),
    ('Flags: Quorate',1),
])
def test_unknown_or_insufficient_remaining_votes_are_rejected(text,nodeid):
    with pytest.raises(RoxywiValidationError):maintenance.vote_budget(text,nodeid)


def test_scheduler_cannot_lose_a_workload_or_leave_it_on_maintenance_target(maintenance_cluster):
    before=maintenance_cluster.live;after=copy.deepcopy(before)
    after['nodes'][0]['standby']='true';after['resources']=[]
    with pytest.raises(RoxywiValidationError,match='surviving'):maintenance.check_placement(before,after,'one')
    after['resources']=copy.deepcopy(before['resources'])
    with pytest.raises(RoxywiValidationError,match='owns'):maintenance.check_placement(before,after,'one')


@pytest.fixture
def keepalived_maintenance(product,maintenance_cluster,monkeypatch):
    cluster=HaCluster.create(name='product-vrrp',group_id=1,syn_flood=0,description='Fixture')
    router=HaClusterRouter.create(cluster_id=cluster,default=1)
    for ident in (11,33):HaClusterSlave.create(cluster_id=cluster,server_id=ident,router_id=router)
    HaClusterVip.create(cluster_id=cluster,router_id=router,vip='192.0.2.100/24')
    state=SimpleNamespace(cluster=cluster,actions=[],no_takeover=False,startup='enabled',startup_actions=[])
    state.nodes={11:dict(id=11,name=product.server.hostname,digest='a'*64,active=True,addresses=['192.0.2.100'],includes=False),
                 33:dict(id=33,name='Product standby',digest='b'*64,active=True,addresses=[],includes=False)}
    monkeypatch.setattr(audit,'keepalived_node',lambda c,n,s:copy.deepcopy(state.nodes[s.server_id]))
    def action(server,binding,operation):
        state.actions.append((server.server_id,operation));state.nodes[11]['active']=operation=='start'
        state.nodes[11]['addresses']=['192.0.2.100'] if operation=='start' else []
        state.nodes[33]['addresses']=[] if operation=='start' or state.no_takeover else ['192.0.2.100']
    monkeypatch.setattr(maintenance,'ka_action',action)
    def startup(server,operation,policy=None):
        state.startup_actions.append((server.server_id,operation,policy))
        if operation=='hold':state.startup='masked'
        elif operation=='restore':state.startup=policy
        return state.startup
    monkeypatch.setattr(maintenance,'ka_startup',startup)
    return state


def ka_create(product_client,state):
    response=product_client.post('/ha/api/maintenance',json=dict(provider='keepalived',cluster_id=state.cluster.id,
        server_id=11,title='Maintain VRRP node',capacity_confirmed=True,capacity_evidence='Load test on standby proxy passed'))
    assert response.status_code==201,response.text
    return HaMaintenancePlan.get_by_id(response.json['data']['id'])


def ka_step(product_client,row,action,expected='completed'):
    response=product_client.post(f'/ha/api/maintenance/{row.id}/{action}',json={});assert response.status_code==202,response.text
    assert maintenance.execute(InstallationTasks.get_by_id(response.json['task_id']))==expected
    return HaMaintenancePlan.get_by_id(row.id)


def test_keepalived_verified_handover_blocks_competing_service_actions(product_client,keepalived_maintenance,maintenance_cluster,app):
    row=ka_step(product_client,ka_create(product_client,keepalived_maintenance),'review')
    approve(app,row,maintenance_cluster.reviewer)
    row=ka_step(product_client,row,'drain')
    assert row.status=='ready' and keepalived_maintenance.nodes[33]['addresses']==['192.0.2.100']
    from app.modules.service.action import get_action_command
    with pytest.raises(Exception,match='maintenance'):get_action_command('keepalived','start',11)
    row=ka_step(product_client,row,'review-return');approve(app,row,maintenance_cluster.reviewer)
    row=ka_step(product_client,row,'resume')
    assert row.status=='completed' and keepalived_maintenance.actions==[(11,'stop'),(11,'start')]


def test_keepalived_failed_takeover_can_be_recovered_by_reviewed_return(product_client,keepalived_maintenance,maintenance_cluster,app):
    row=ka_step(product_client,ka_create(product_client,keepalived_maintenance),'review');approve(app,row,maintenance_cluster.reviewer)
    keepalived_maintenance.no_takeover=True
    row=ka_step(product_client,row,'drain',expected='failed')
    assert row.status=='unknown' and not unseal(row.payload).get('drained_at')
    row=ka_step(product_client,row,'review-return');approve(app,row,maintenance_cluster.reviewer)
    row=ka_step(product_client,row,'resume')
    assert row.status=='completed' and keepalived_maintenance.nodes[11]['addresses']==['192.0.2.100']
    assert 'verified_test' not in unseal(OperationalAssessment.get_by_id(row.assessment_id).result)


def test_vip_template_and_id_reference_are_resolved_but_dynamic_addresses_are_refused():
    from app.modules.pacemaker.xml import configuration
    xml='<cib><configuration><resources><template id="base" class="ocf" type="IPaddr2"><instance_attributes id="addr"><nvpair name="ip" value="192.0.2.100"/></instance_attributes></template><primitive id="vip" template="base"><instance_attributes id-ref="addr"/></primitive></resources></configuration></cib>'
    assert maintenance.configured_vips(configuration(xml))==['192.0.2.100']
    xml=xml.replace('<nvpair name="ip"','<rule id="rule"/><nvpair name="ip"')
    with pytest.raises(RoxywiValidationError,match='Conditional'):maintenance.configured_vips(configuration(xml))


def test_interrupted_keepalived_write_is_not_replayed(product_client,keepalived_maintenance,maintenance_cluster,app):
    row=ka_step(product_client,ka_create(product_client,keepalived_maintenance),'review');approve(app,row,maintenance_cluster.reviewer)
    response=product_client.post(f'/ha/api/maintenance/{row.id}/drain',json={});assert response.status_code==202
    task=InstallationTasks.get_by_id(response.json['task_id']);payload=unseal(task.operation_payload);payload['started']=True
    task.operation_payload=maintenance.seal(payload);task.save()
    assert maintenance.execute(task)=='failed'
    assert keepalived_maintenance.actions==[]
    row=HaMaintenancePlan.get_by_id(row.id)
    assert row.status=='unknown' and row.active_task_id is None


def test_queued_protected_node_cannot_be_changed_by_a_demoted_operator(product_client,product,maintenance_cluster,app):
    row=step(product_client,create(product_client,maintenance_cluster),'review');approve(app,row,maintenance_cluster.reviewer)
    response=product_client.post(f'/ha/api/maintenance/{row.id}/drain',json={});assert response.status_code==202
    Server.update(protected=1).where(Server.server_id==11).execute()
    UserGroups.update(user_role_id=3).where(UserGroups.user_id==product.admin.user_id).execute()
    assert operations.execute(InstallationTasks.get_by_id(response.json['task_id']))=='failed'
    assert not maintenance_cluster.commands


def test_drained_nodes_need_a_surviving_promoted_workload(maintenance_cluster):
    before=copy.deepcopy(maintenance_cluster.live);before['resources'][0]['role']='Promoted'
    after=copy.deepcopy(before);after['nodes'][0]['standby']='true';after['resources'][0].update(role='Unpromoted',nodes=['two'])
    with pytest.raises(RoxywiValidationError,match='promoted'):maintenance.check_placement(before,after,'one')
