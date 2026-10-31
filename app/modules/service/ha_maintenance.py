"""Reviewed node maintenance; uncertain drains never become a maintenance handover."""
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import time
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator
from peewee import SqliteDatabase

from app.modules.common.file_lock import file_lock
from app.modules.common.execution_context import group_settings
from app.modules.common.time import utc_now,utc_iso
from app.modules.db.db_model import (HaMaintenancePlan,ConfigChange,InstallationTasks,OperationalAssessment,
    PacemakerCluster,HaClusterVip,User,UserGroups)
from app.modules.db import user as user_sql
from app.modules.operations.queue import serialize_operation_payload as seal,deserialize_operation_payload as unseal
from app.modules.pacemaker import service
from app.modules.pacemaker.remote import Remote
from app.modules.pacemaker.xml import configuration,summary
from app.modules.service import ha_readiness as audit,ha_maintenance_remote as helper
from app.modules.roxywi.exception import RoxywiConflictError,RoxywiResourceNotFound,RoxywiValidationError,RoxywiPublicError,RoxywiPermissionError
from app.modules.subscription.access import CHANGE_CENTER,require_feature
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.service.ha_topology import topology_guarded, change_lock


class Create(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    provider: Literal['pacemaker','keepalived']
    cluster_id: int=Field(gt=0)
    server_id: int=Field(gt=0)
    title: str=Field(min_length=1,max_length=255,pattern=r'^[^\r\n<>]+$')
    capacity_confirmed: bool=Field(strict=True)
    capacity_evidence: str=Field(min_length=1,max_length=2000)


class ListQuery(BaseModel):
    """Scope maintenance history to a cluster while retaining the existing group list."""
    model_config = ConfigDict(extra='forbid')
    provider: Literal['pacemaker', 'keepalived'] | None = None
    cluster_id: int | None = Field(default=None, gt=0)
    before: int | None = Field(default=None, gt=0)
    change_id: int | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def paired_cluster(self) -> 'ListQuery':
        if (self.provider is None) != (self.cluster_id is None):
            raise ValueError('Provider and cluster are required together')
        return self


def plans(group_id: int, query: ListQuery) -> tuple[list[HaMaintenancePlan], int | None, str | None]:
    """Fetch active plans plus one bounded history page for this registration."""
    rows = HaMaintenancePlan.select(HaMaintenancePlan, ConfigChange).join(
        ConfigChange, on=(HaMaintenancePlan.change_id == ConfigChange.id)
    ).where((HaMaintenancePlan.group_id == group_id) & (ConfigChange.group_id == group_id))
    registration = None
    if query.provider is not None:
        cluster, _nodes = audit.subject(query.provider, query.cluster_id, group_id)
        registration = cluster.readiness_key
        rows = rows.where((HaMaintenancePlan.provider == query.provider) & (HaMaintenancePlan.cluster_id == query.cluster_id))
    terminal = (HaMaintenancePlan.status == 'completed') | (ConfigChange.status == 'cancelled')
    active = list(rows.where(~terminal).order_by(HaMaintenancePlan.id.desc()))
    history = rows.where(terminal)
    if query.before:
        history = history.where(HaMaintenancePlan.id < query.before)
    page = list(history.order_by(HaMaintenancePlan.id.desc()).limit(51))
    result = active + page[:50]
    if query.change_id and not any(row.change_id == query.change_id for row in result):
        result.extend(rows.where(HaMaintenancePlan.change_id == query.change_id))
    if registration is not None:
        result = [row for row in result if unseal(row.payload).get('registration_key') == registration]
    return result, page[49].id if len(page) > 50 else None, registration


def get(ident,group_id):
    row=HaMaintenancePlan.get_or_none((HaMaintenancePlan.id==ident)&(HaMaintenancePlan.group_id==group_id))
    if row is None:raise RoxywiResourceNotFound('Maintenance plan not found')
    cluster,_nodes=audit.subject(row.provider,row.cluster_id,group_id)
    if unseal(row.payload).get('registration_key')!=cluster.readiness_key:
        raise RoxywiConflictError('Cluster registration changed; this maintenance plan belongs to its previous registration')
    return row


def parent(row):
    change=ConfigChange.get_or_none((ConfigChange.id==row.change_id)&(ConfigChange.group_id==row.group_id)&(ConfigChange.action=='ha-maintenance'))
    if change is None:raise RoxywiConflictError('Maintenance review is missing')
    return change


def approvers(group_id: int) -> list[dict]:
    """List enabled HA administrators in the active group for approval guidance."""
    users = User.select(User.user_id, User.username, User.user_services).join(
        UserGroups, on=(User.user_id == UserGroups.user_id)
    ).where(
        (UserGroups.user_group_id == group_id)
        & UserGroups.user_role_id.in_((1, 2))
        & (User.enabled == 1)
    ).distinct().order_by(User.username)
    return [dict(id=user.user_id, name=user.username) for user in users if '5' in user.user_services.split()]


def public(row, *, available_approvers: list[dict] | None = None) -> dict:
    from app.modules.change.service import name_for_user

    data=unseal(row.payload);change=parent(row)
    task=InstallationTasks.get_or_none(InstallationTasks.id==row.active_task_id) if row.active_task_id else None
    if available_approvers is None:
        available_approvers = approvers(row.group_id)
    return dict(id=row.id,provider=row.provider,cluster_id=row.cluster_id,server_id=row.server_id,
        title=change.title,cluster_name=data.get('cluster_name',str(row.cluster_id)),node_name=data.get('node_name',str(row.server_id)),
        can_cancel=not row.active_task_id and not data.get('drained_at') and row.status in ('draft','reviewed','review-failed') and change.status in ('draft','validation_failed','pending_approval','approved'),
        status='cancelled' if change.status=='cancelled' else row.status,change_id=change.id,
        change_status=change.status,user_id=change.user_id,created_by=name_for_user(change.user_id),
        approved_by=change.approved_by,approved_by_name=name_for_user(change.approved_by),
        approvers=[user for user in available_approvers if user['id'] != change.user_id],
        operation=dict(id=task.id,status=task.status,error=task.error) if task else None,
        capacity_evidence=data['capacity_evidence'],review=data.get('review'),events=data.get('events',[]),
        updated_at=utc_iso(row.updated_at))


def create(body,group_id,user_id):
    require_feature(CHANGE_CENTER)
    if not body.capacity_confirmed:raise RoxywiValidationError('Confirm remaining application capacity and record its evidence')
    cluster,nodes=audit.subject(body.provider,body.cluster_id,group_id)
    if body.server_id not in {s.server_id for _n,s in nodes}:raise ValueError('Select a cluster member')
    database=HaMaintenancePlan._meta.database
    with database.atomic('IMMEDIATE') if isinstance(database,SqliteDatabase) else database.atomic():
        audit.lock_registration(cluster,group_id)
        row=HaMaintenancePlan.create(group_id=group_id,user_id=user_id,provider=body.provider,cluster_id=cluster.id,
            server_id=body.server_id,payload=seal(dict(capacity_evidence=body.capacity_evidence,events=[],
                cluster_name=cluster.name,registration_key=cluster.readiness_key,
                node_name=next(n for n,s in nodes if s.server_id==body.server_id))))
        change=ConfigChange.create(server_id=body.server_id,group_id=group_id,user_id=user_id,service='cluster',
            action='ha-maintenance',title=body.title,description='Reviewed HA node maintenance; capacity is operator-attested.',
            remote_path=f'ha://{body.provider}/{cluster.id}/{body.server_id}',draft_path='',rollback_path='',
            requires_approval=1,status='draft')
        row.change_id=change.id;row.save()
        assessment=OperationalAssessment.create(group_id=group_id,user_id=user_id,kind='ha-maintenance',subject=audit.subject_key(body.provider,cluster))
        row.assessment_id=assessment.id;row.save()
    return row


def path_lock(row):
    directory=Path(GetConfigVar().get_config_var('main','lib_path'))/'ha-maintenance-locks'
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    return directory/f'{row.provider}-{row.cluster_id}.lock'


def assert_idle(provider,cluster_id,group_id,plan_id=None):
    busy=HaMaintenancePlan.select().where((HaMaintenancePlan.provider==provider)&
        (HaMaintenancePlan.cluster_id==cluster_id)&(HaMaintenancePlan.group_id==group_id)&
        (HaMaintenancePlan.status.in_(('draining','ready','unknown','resuming','return-reviewed'))|HaMaintenancePlan.active_task_id.is_null(False)))
    if any(row.id!=plan_id for row in busy):
        raise RoxywiConflictError('A node is reserved for maintenance; use its reviewed return workflow first')


def assert_server_idle(server_id):
    from app.modules.db.db_model import HaClusterSlave,Server
    server=Server.get_by_id(server_id)
    for member in HaClusterSlave.select().where(HaClusterSlave.server_id==server_id):
        assert_idle('keepalived',member.cluster_id_id,int(server.group_id))


@topology_guarded
def enqueue(row,user_id,action):
    require_feature(CHANGE_CENTER)
    if action not in ('review','drain','verify','review-return','resume'):raise ValueError('Invalid maintenance action')
    with change_lock(path_lock(row)):
        row=get(row.id,row.group_id);change=parent(row)
        if row.active_task_id:raise RoxywiConflictError('A maintenance operation is already pending')
        allowed={'review':('draft','reviewed','review-failed'),'drain':('reviewed',),
            'verify':('draining','unknown'),'review-return':('ready','draining','unknown','return-reviewed'),
            'resume':('return-reviewed',)}
        if change.status=='cancelled' or row.status not in allowed[action]:raise RoxywiConflictError('This action is not available in the current maintenance state')
        if action in ('drain','resume') and (change.status!='approved' or change.approved_by is None):
            raise RoxywiConflictError('Another administrator must approve the current checks before this action')
        cluster,nodes=audit.subject(row.provider,row.cluster_id,row.group_id)
        assert_idle(row.provider,row.cluster_id,row.group_id,row.id)
        if action in ('drain','resume') and any(s.server_id==row.server_id and s.protected for _n,s in nodes) and int(user_sql.get_user_role_in_group(user_id,row.group_id))>2:
            raise RoxywiPermissionError('An administrator must execute maintenance on this protected server')
        data=dict(plan_id=row.id,action=action,identities=audit.identities(nodes))
        if row.provider=='pacemaker':
            from app.modules.pacemaker import operations
            task=operations.enqueue(cluster,user_id,'node-maintenance',data)
        else:
            task=InstallationTasks.create(service_name=f'HA maintenance #{row.id}: {action}',group_id=row.group_id,
                user_id=user_id,server_ids=[s.server_id for _n,s in nodes],operation_id=str(uuid4()),
                operation_type='ha-maintenance',status='created',updated_at=utc_now(),operation_payload=seal(data))
        row.active_task_id=task.id;row.save()
        ConfigChange.update(active_task_id=task.id,last_task_id=task.id,updated_at=utc_now()).where(ConfigChange.id==change.id).execute()
        return task


def persist(row,data,status,message,*,change_status=None):
    data.setdefault('events',[]).append(dict(at=utc_iso(utc_now()),state=status,message=message))
    row.payload=seal(data);row.status=status;row.updated_at=utc_now();row.save()
    if change_status:
        ConfigChange.update(status=change_status,updated_at=utc_now()).where(ConfigChange.id==row.change_id).execute()


def vote_budget(text,nodeid):
    def value(label):
        match=re.search(r'^'+re.escape(label)+r':\s+(\d+)\b',text,re.M)
        if not match:raise RoxywiValidationError('Cannot establish the remaining quorum budget')
        return int(match[1])
    votes=[]
    for line in text.splitlines():
        match=re.match(r'^\s*(0x[0-9a-fA-F]+|\d+)\s+(\d+)\s+',line)
        if match and int(match[1],16 if match[1].startswith('0x') else 10)==nodeid:votes.append(int(match[2]))
    if len(votes)!=1:raise RoxywiValidationError('Cannot identify this member vote weight')
    remaining=value('Total votes')-votes[0];required=value('Quorum')
    if required<1 or remaining<required:raise RoxywiValidationError('Taking this member offline would lose quorum')
    return dict(current=value('Total votes'),member=votes[0],remaining=remaining,required=required)


def workloads(state):
    return {r['target_id'] for r in state['resources'] if r['active']=='true' and not str(r['resource_agent']).startswith('stonith:')}


def configured_vips(config):
    indexed={element.get('id'):element for element in config.iter() if element.get('id')}
    values=[]
    for resource in config.findall('./resources//primitive'):
        template=indexed.get(resource.get('template'))
        attributes=dict(template.attrib) if template is not None else {}
        attributes.update(resource.attrib)
        if attributes.get('type') not in ('IPaddr','IPaddr2'):continue
        parameters={}
        for origin in ([template,resource] if template is not None else [resource]):
            for group in origin.findall('./instance_attributes'):
                if group.get('id-ref'):group=indexed.get(group.get('id-ref'))
                if group is None or group.find('rule') is not None:
                    raise RoxywiValidationError('Conditional or unresolved VIP addresses cannot be automatically drained')
                parameters.update({value.get('name'):value.get('value') for value in group.findall('nvpair')})
        try:values.append(str(ipaddress.ip_address(parameters['ip'])))
        except (KeyError,ValueError):raise RoxywiValidationError('A VIP address could not be verified from the resource configuration') from None
    return sorted(set(values))


def check_placement(before,after,target,*,returning=False):
    if not after['quorate'] or after['failures'] or any(r['failed']=='true' or r['blocked']=='true' for r in after['resources']):
        raise RoxywiValidationError('The scheduler or observed cluster reports a failed workload')
    if workloads(before)-workloads(after):raise RoxywiValidationError('At least one active workload would have no surviving instance')
    promoted=lambda state:{r['target_id'] for r in state['resources'] if r.get('active')=='true' and r.get('role') in ('Master','Promoted')}
    if promoted(before)-promoted(after):raise RoxywiValidationError('A promoted workload would lose its active role')
    if {n['name'] for n in before['nodes']}!={n['name'] for n in after['nodes']} or any(n['online']!='true' or n['unclean']=='true' or
        (n['name']!=target and n['standby']=='true') for n in after['nodes']):
        raise RoxywiValidationError('Remaining members must stay online, clean and available')
    if not returning and any(target in r['nodes'] for r in after['resources'] if r['active']=='true'):
        raise RoxywiValidationError('The selected node still owns cluster resources')
    target_nodes=[n for n in after['nodes'] if n['name']==target]
    if len(target_nodes)!=1 or target_nodes[0]['online']!='true' or target_nodes[0]['unclean']=='true':
        raise RoxywiValidationError('Selected member must be online and clean')
    if target_nodes[0]['standby']!=('false' if returning else 'true'):
        raise RoxywiValidationError('The node has not reached the requested standby state')


def pm_view(cluster,target,*,returning=False):
    remote,xml=service.connection(cluster)
    before=summary(remote.run(['crm_mon','--one-shot','--output-as=xml'],allowed=(0,1,2)))
    config=configuration(xml)
    props={v.get('name'):v.get('value') for v in config.findall('./crm_config/cluster_property_set/nvpair')}
    if props.get('maintenance-mode','false').lower() in ('true','1') or props.get('stonith-enabled','true').lower() in ('false','0'):
        raise RoxywiValidationError('Leave cluster maintenance mode off and fencing enabled')
    if any(r['managed']!='true' for r in before['resources'] if r['active']=='true'):
        raise RoxywiValidationError('Unmanaged workloads cannot be safely drained')
    checked=service.members(cluster);member=next(m for m,_s in checked if m.name==target)
    quorum=remote.run(['env','LC_ALL=C','corosync-quorumtool','-s'],allowed=(0,2))
    if len(checked)==2 or audit.details(quorum)['configured']:
        from app.modules.pacemaker.witness_migration import verify
        verify([cluster])
    budget=vote_budget(quorum,member.nodeid)
    source=Path(helper.__file__).read_text()+'\nimport sys\nd=json.load(sys.stdin)\nprint(simulate(d["xml"],d["target"],returning=d["returning"]))\n'
    predicted=summary(remote.run(['python3','-c',source],data=json.dumps(dict(xml=xml,target=target,returning=returning)),timeout=150))
    check_placement(before,predicted,target,returning=returning)
    return dict(fingerprint=helper.fingerprint(xml,target),before=before,predicted=predicted,quorum=budget,vips=configured_vips(config))


def ka_view(cluster,nodes,target,*,returning=False):
    from app.modules.db import service as service_sql
    if any(bool(getattr(s,'keepalived_active',False)) for _n,s in nodes):
        raise RoxywiValidationError('Disable independent Keepalived Auto Start before planned maintenance')
    values=[audit.keepalived_node(cluster,n,s) for n,s in nodes]
    surviving=[v for v in values if v['id']!=target]
    if not returning and (not surviving or not all(v['active'] for v in surviving)):
        raise RoxywiValidationError('Every surviving Keepalived member must be active before draining this node')
    vips=sorted({str(ipaddress.ip_interface(v.vip).ip) for v in HaClusterVip.select().where(HaClusterVip.cluster_id==cluster.id)})
    if not vips:raise RoxywiValidationError('Register the cluster VIPs before planning maintenance')
    if any(value.get('includes') for value in values):raise RoxywiValidationError('Included Keepalived files require a reviewed supported configuration before automatic maintenance')
    owners={vip:[v['id'] for v in values if vip in v['addresses']] for vip in vips}
    if any(len(names)>1 for names in owners.values()) or (not returning and not all(len(names)==1 for names in owners.values())):
        raise RoxywiValidationError('Every registered VIP must have one verified owner; duplicate owners cannot be automatically recovered')
    bindings={str(s.server_id):dict(dockerized=service_sql.select_service_setting(s.server_id,'keepalived','dockerized')) for _n,s in nodes}
    from app.modules.service import container_settings
    for _n,s in nodes:
        if bindings[str(s.server_id)]['dockerized']=='1':
            bindings[str(s.server_id)].update(runtime=container_settings.runtime(s.server_id,'keepalived'),name=container_settings.name(s.server_id,'keepalived'))
    if not returning and bindings[str(target)]['dockerized']=='1':
        raise RoxywiValidationError('Automatic container maintenance requires a verified persistent startup hold')
    fingerprint=hashlib.sha256(json.dumps(dict(registration_key=cluster.readiness_key,
        digests={str(v['id']):v['digest'] for v in values},bindings=bindings,vips=vips),sort_keys=True).encode()).hexdigest()
    return dict(fingerprint=fingerprint,nodes=values,vips=vips,owners=owners,bindings=bindings)


SOCKETS=r'''
import ipaddress,json,subprocess,sys
def normalized(value):
    address=ipaddress.ip_address(value)
    return str(address.ipv4_mapped if isinstance(address,ipaddress.IPv6Address) and address.ipv4_mapped else address)
vips={normalized(value) for value in json.load(sys.stdin)}
result=subprocess.run(['ss','-Hnt','state','established'],check=True,capture_output=True,text=True,timeout=15)
if len(result.stdout)>1048576:raise ValueError('Too many sessions to verify')
count=0
for line in result.stdout.splitlines():
    fields=line.split()
    if len(fields)<4:raise ValueError('Unsupported socket output')
    # ss without the state column: Recv-Q Send-Q Local Peer.
    address=fields[2].rsplit(':',1)[0].strip('[]')
    try:address=normalized(address)
    except ValueError:raise ValueError('Unsupported socket address')
    if address in vips:count+=1
print(count)
'''


def connections(server,vips):
    result=Remote(server).run(['python3','-c',SOCKETS],data=json.dumps(vips)).strip()
    if not re.fullmatch(r'\d{1,8}',result):raise RoxywiValidationError('Cannot establish VIP session drain')
    return int(result)


def ka_action(server,binding,action):
    if binding['dockerized']=='1':
        from app.modules.connectors import containers
        code=containers.embedded()+'import json,sys,subprocess\nd=json.load(sys.stdin)\nsubprocess.run(module.lifecycle(d["runtime"],d["name"],d["action"]),check=True,timeout=90)\n'
        Remote(server).run(['python3','-c',code],data=json.dumps(dict(binding,action=action)),timeout=120)
    else:Remote(server).run(['systemctl',action,'keepalived'],timeout=90)


def ka_startup(server,action,policy=None):
    """Use a persistent mask; masking retains the original enablement links."""
    remote=Remote(server)
    def read():
        value=remote.run(['systemctl','is-enabled','keepalived'],allowed=(0,1,3,4)).strip()
        if value not in ('enabled','disabled','static','indirect','masked'):
            raise RoxywiValidationError('Cannot verify the native Keepalived startup policy')
        return value
    if action=='read':return read()
    if action=='hold':
        remote.run(['systemctl','mask','keepalived'],timeout=90)
        if read()!='masked':raise RoxywiValidationError('Keepalived must remain persistently masked during maintenance')
        return 'masked'
    if action!='restore' or policy not in ('enabled','disabled','static','indirect'):
        raise RoxywiValidationError('The original Keepalived startup policy is unavailable')
    remote.run(['systemctl','unmask','keepalived'],timeout=90)
    if policy in ('enabled','disabled'):
        remote.run(['systemctl','enable' if policy=='enabled' else 'disable','keepalived'],timeout=90)
    if read()!=policy:raise RoxywiValidationError('Keepalived startup policy restoration could not be verified')
    return policy


def ka_hold(row,server,binding,data):
    if binding['dockerized']=='1':return
    journal=data.get('keepalived_startup')
    if journal is None:
        policy=ka_startup(server,'read')
        if policy=='masked':raise RoxywiValidationError('Keepalived is already masked outside this maintenance plan')
        data['keepalived_startup']=dict(policy=policy,phase='mask-requested')
        # Durable encrypted intent and original policy precede the first remote write.
        persist(row,data,'draining','Original Keepalived startup policy recorded; persistent maintenance mask requested.')
    ka_startup(server,'hold')
    data['keepalived_startup']['phase']='held'
    persist(row,data,'draining','Keepalived is persistently masked before stopping the service.')


def ka_restore(row,server,binding,data):
    if binding['dockerized']=='1':return
    journal=data.get('keepalived_startup')
    if journal is None:return  # An interrupted operation may have made no remote write.
    journal['phase']='restore-requested'
    persist(row,data,'resuming','Approved return requested restoration of the original Keepalived startup policy.')
    ka_startup(server,'restore',journal['policy'])
    journal['phase']='restored'
    persist(row,data,'resuming','Original Keepalived startup policy restored for the approved return.')


def reserve(cluster,ident):
    settings=json.loads(cluster.corosync_settings);existing=settings.get('node_maintenance')
    if existing not in (None,ident):raise RoxywiConflictError('Another node is reserved for maintenance')
    settings['node_maintenance']=ident
    PacemakerCluster.update(corosync_settings=json.dumps(settings)).where(PacemakerCluster.id==cluster.id).execute()


def observe(row,cluster,nodes,target,server,data,*,returning=False,seconds=90,heartbeat=lambda:None):
    deadline=time.monotonic()+seconds
    while True:
        try:
            with group_settings(row.group_id):
                if row.provider=='pacemaker':
                    state=service.status(cluster)
                    check_placement(data['review']['view']['before'],state,target,returning=returning)
                    if len(nodes)==2 or state.get('quorum_details',{}).get('configured'):
                        from app.modules.pacemaker.witness_migration import verify
                        verify([cluster])
                else:
                    state=ka_view(cluster,nodes,row.server_id,returning=returning)
                    if not all(len(owners)==1 for owners in state['owners'].values()):
                        raise RoxywiValidationError('VIP ownership is not restored')
                    selected=next(v for v in state['nodes'] if v['id']==row.server_id)
                    if selected['active']!=returning:raise RoxywiValidationError('Keepalived has not reached the requested service state')
                    if not returning and any(row.server_id in owners for owners in state['owners'].values()):raise RoxywiValidationError('VIPs have not left the selected node')
                    if not all(v['active'] for v in state['nodes'] if v['id']!=row.server_id):raise RoxywiValidationError('A remaining Keepalived member is not active')
                    if not returning and state['bindings'][str(row.server_id)]['dockerized']!='1':
                        if data.get('keepalived_startup',{}).get('phase')!='held' or ka_startup(server,'read')!='masked':
                            raise RoxywiValidationError('Persistent Keepalived maintenance mask is not verified')
                pending=connections(server,data['review']['view']['vips']) if not returning else 0
                if pending:raise RoxywiValidationError('Established VIP sessions have not drained')
            return state
        except Exception:
            if time.monotonic()>=deadline:raise RoxywiValidationError('Drain/return is not verified; inspect the node and use Verify drain or Review return. The workflow has not handed over the node.') from None
            heartbeat();time.sleep(2)


def execute_step(task,row,action,renew=lambda:None):
    row=get(row.id,row.group_id);data=unseal(row.payload);change=parent(row)
    cluster,nodes=audit.subject(row.provider,row.cluster_id,row.group_id)
    target,server=next((n,s) for n,s in nodes if s.server_id==row.server_id)
    def heartbeat():
        renew()
        InstallationTasks.update(updated_at=utc_now()).where(InstallationTasks.id==task.id).execute()
    def view(returning=False):
        with group_settings(row.group_id):return pm_view(cluster,target,returning=returning) if row.provider=='pacemaker' else ka_view(cluster,nodes,row.server_id,returning=returning)
    if action in ('review','review-return'):
        returning=action=='review-return'
        if returning and row.provider=='pacemaker' and json.loads(cluster.corosync_settings).get('node_maintenance')!=row.id:
            raise RoxywiConflictError('This plan does not own the cluster maintenance reservation')
        reviewed=view(returning)
        if returning and data.get('keepalived_startup'):
            reviewed['startup_policy']=data['keepalived_startup']['policy']
        if not returning:
            report=audit.collect(row.provider,cluster,nodes,audit.profile(row.provider,cluster.id,row.group_id),heartbeat)
            blocked=[c['key'] for c in report['checks'] if c['state']=='fail']
            if blocked:raise RoxywiValidationError('Resolve failed HA readiness checks before draining a node')
        data['review']=dict(returning=returning,view=reviewed,identities=audit.identities(nodes),reviewed_at=utc_iso(utc_now()))
        persist(row,data,'return-reviewed' if returning else 'reviewed','Return review completed' if returning else 'Drain review completed',change_status='pending_approval')
        ConfigChange.update(approved_by=None,diff=json.dumps(data['review'],sort_keys=True),
            validation_output='Read-only placement/quorum review completed. Application capacity is operator-attested.').where(ConfigChange.id==row.change_id).execute()
        return
    if not data.get('review') or data['review']['identities']!=audit.identities(nodes):raise RoxywiConflictError('Member/SSH identities changed; create a fresh review')
    if action in ('drain','resume'):
        assert_idle(row.provider,row.cluster_id,row.group_id,row.id)
        returning=action=='resume'
        if change.status!='approved' or not change.approved_by or data['review']['returning']!=returning:
            raise RoxywiConflictError('Approve the current matching checks before changing the node')
        approver=User.get_or_none(User.user_id==change.approved_by)
        if not approver or not approver.enabled or approver.user_id==change.user_id or '5' not in user_sql.select_user_services(approver.user_id).split() or int(user_sql.get_user_role_in_group(approver.user_id,row.group_id))>2:
            raise RoxywiValidationError('The independent approver no longer has the required permissions; review again')
        current=view(returning)
        if current['fingerprint']!=data['review']['view']['fingerprint']:raise RoxywiConflictError('Configuration changed after review; review again before changing the node')
        heartbeat()
        if row.provider=='pacemaker':reserve(cluster,row.id)
        persist(row,data,'resuming' if returning else 'draining','Return requested' if returning else 'Drain requested',change_status='deploying')
        if row.provider=='pacemaker':
            remote,_xml=service.connection(cluster)
            remote.run(['crm_standby','--node',target,'--update','off' if returning else 'on'],timeout=90)
        else:
            binding=current['bindings'][str(row.server_id)]
            if returning:ka_restore(row,server,binding,data)
            else:
                ka_hold(row,server,binding,data)
                # Masking may require SSH round trips; refresh survivor health again before stop.
                fresh=view()
                if fresh['fingerprint']!=data['review']['view']['fingerprint']:
                    raise RoxywiConflictError('Configuration changed before stopping Keepalived; review return before recovery')
            ka_action(server,binding,'start' if returning else 'stop')
    returning=action=='resume'
    observed=observe(row,cluster,nodes,target,server,data,returning=returning,heartbeat=heartbeat)
    if not returning:
        data['drained_at']=utc_iso(utc_now());data['drained']=observed
        persist(row,data,'ready','Registered resources and VIP sessions are drained; node handed over for maintenance.',change_status='paused')
    else:
        result=audit.collect(row.provider,cluster,nodes,audit.profile(row.provider,cluster.id,row.group_id),heartbeat)
        if any(c['state']=='fail' for c in result['checks']):
            raise RoxywiValidationError('Workload return was observed, but HA readiness still has failed checks; review return again after resolving them')
        if row.provider=='pacemaker':
            current=service.get_cluster(cluster.id,cluster.group_id);settings=json.loads(current.corosync_settings)
            if settings.get('node_maintenance')!=row.id:raise RoxywiConflictError('Maintenance reservation changed')
            settings.pop('node_maintenance')
            PacemakerCluster.update(corosync_settings=json.dumps(settings)).where(PacemakerCluster.id==cluster.id).execute()
        data['returned_at']=utc_iso(utc_now())
        persist(row,data,'completed','Node returned with observed cluster health.',change_status='deployed')
        proof=dict(kind='planned-node-maintenance',source='observed-drain-and-return',plan_id=row.id,
            task_id=task.id,drained_at=data.get('drained_at'),returned_at=data['returned_at'],fingerprint=result['fingerprint'])
        result=dict(events=data['events'],recovery_completed=not bool(data.get('drained_at')))
        if data.get('drained_at'):result['verified_test']=proof
        OperationalAssessment.update(result=seal(result),created_at=utc_now(),task_id=task.id).where(OperationalAssessment.id==row.assessment_id).execute()


def process(task,data,*,heartbeat=lambda:None):
    row=None
    try:
        row=get(data['plan_id'],task.group_id_id)
        if row.active_task_id!=task.id:raise RoxywiConflictError('This task no longer owns the maintenance plan')
        actor=User.get_or_none(User.user_id==task.user_id_id)
        if not actor or not actor.enabled or '5' not in user_sql.select_user_services(actor.user_id).split() or int(user_sql.get_user_role_in_group(actor.user_id,task.group_id_id))>3:
            raise RoxywiValidationError('Maintenance permissions were revoked')
        require_feature(CHANGE_CENTER)
        cluster,nodes=audit.subject(row.provider,row.cluster_id,row.group_id)
        if data['action'] in ('drain','resume') and any(s.server_id==row.server_id and s.protected for _n,s in nodes) and int(user_sql.get_user_role_in_group(actor.user_id,row.group_id))>2:
            raise RoxywiPermissionError('An administrator must execute maintenance on this protected server')
        if data['identities']!=audit.identities(nodes):raise RoxywiConflictError('Member/SSH identities changed after queuing')
        execute_step(task,row,data['action'],heartbeat)
    except Exception as error:
        if row:
            row=get(row.id,row.group_id);values=unseal(row.payload)
            status='unknown' if row.status in ('draining','resuming','ready','unknown','return-reviewed') or values.get('drained_at') else 'review-failed'
            persist(row,values,status,error.public_message if isinstance(error,RoxywiPublicError) else 'Operation could not be verified. No automatic handover or return was performed.',
                change_status='deployment_interrupted' if status=='unknown' else 'validation_failed')
        raise
    finally:
        if row:
            HaMaintenancePlan.update(active_task_id=None).where((HaMaintenancePlan.id==row.id)&(HaMaintenancePlan.active_task_id==task.id)).execute()
            ConfigChange.update(active_task_id=None).where((ConfigChange.id==row.change_id)&(ConfigChange.active_task_id==task.id)).execute()


def release_failed_task(task,plan_id):
    row=HaMaintenancePlan.get_or_none((HaMaintenancePlan.id==plan_id)&(HaMaintenancePlan.group_id==task.group_id_id)&(HaMaintenancePlan.active_task_id==task.id))
    if row is None:return
    data=unseal(row.payload)
    persist(row,data,'unknown' if row.status in ('draining','resuming','ready','unknown','return-reviewed') or data.get('drained_at') else 'review-failed',
        'Interrupted or rejected operation requires fresh review/observation.',change_status='deployment_interrupted')
    HaMaintenancePlan.update(active_task_id=None).where(HaMaintenancePlan.id==row.id).execute()
    ConfigChange.update(active_task_id=None).where((ConfigChange.id==row.change_id)&(ConfigChange.active_task_id==task.id)).execute()


def execute(task):
    data=unseal(task.operation_payload)
    row=HaMaintenancePlan.get_or_none((HaMaintenancePlan.id==data['plan_id'])&(HaMaintenancePlan.group_id==task.group_id_id))
    if row is None:
        InstallationTasks.update(status='failed',error='Maintenance plan no longer exists',finish_date=utc_now(),updated_at=utc_now()).where(InstallationTasks.id==task.id).execute()
        return 'failed'
    with file_lock(path_lock(row)):
        task=InstallationTasks.get_by_id(task.id)
        if task.status in ('completed','failed'):return task.status
        if data.get('started'):
            row=get(row.id,row.group_id);persist(row,unseal(row.payload),'unknown','Interrupted operation requires a fresh observation.',change_status='deployment_interrupted')
            state,error='failed','Interrupted maintenance is not replayed; verify drain or review return'
            HaMaintenancePlan.update(active_task_id=None).where(HaMaintenancePlan.id==row.id).execute()
            ConfigChange.update(active_task_id=None).where(ConfigChange.id==row.change_id).execute()
        else:
            data['started']=True;InstallationTasks.update(operation_payload=seal(data)).where(InstallationTasks.id==task.id).execute()
            try:process(task,data);state,error='completed',None
            except Exception:
                state,error='failed','Maintenance did not reach a verified state; inspect its review and node status'
                release_failed_task(task,row.id)
        InstallationTasks.update(status=state,error=error,finish_date=utc_now(),updated_at=utc_now()).where(InstallationTasks.id==task.id).execute()
        return state
