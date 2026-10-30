"""Read-only HA observations. Configuration and attestations are never test proof."""
import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Literal
from uuid import uuid4
from peewee import SqliteDatabase

from pydantic import BaseModel, ConfigDict, Field
from app.modules.common.time import utc_now, utc_iso, as_naive_utc
from app.modules.common.execution_context import group_settings
from app.modules.db.db_model import (HaCluster, HaClusterSlave, HaClusterVip, PacemakerCluster,
    OperationalAssessment, HaReadinessProfile, InstallationTasks, User, Server)
from app.modules.db import server as server_sql, user as user_sql
from app.modules.operations.queue import serialize_operation_payload, deserialize_operation_payload
from app.modules.pacemaker import service
from app.modules.pacemaker.remote import Remote
from app.modules.pacemaker.xml import configuration, digest, summary
from app.modules.pacemaker.quorum import details
from app.modules.roxywi.exception import RoxywiResourceNotFound, RoxywiConflictError


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    revision: int = Field(ge=0)
    registration_key: str | None = Field(default=None, min_length=32, max_length=32)
    domains: dict[int, dict[Literal['hypervisor', 'power', 'uplink', 'storage'], str]]


class Attestation(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Literal['planned-switchover', 'fencing', 'network-partition']
    result: Literal['passed', 'failed']
    tested_at: datetime
    note: str = Field(min_length=10, max_length=2000)
    assessment_id: int = Field(gt=0)


def subject(provider, cluster_id, group_id):
    if provider == 'pacemaker':
        cluster = service.get_cluster(cluster_id, group_id)
        nodes = [(member.name, server) for member, server in service.members(cluster)]
    elif provider == 'keepalived':
        cluster = HaCluster.get_or_none((HaCluster.id == cluster_id) & (HaCluster.group_id == group_id))
        if cluster is None:
            raise RoxywiResourceNotFound('Cluster not found in the active group')
        ids = sorted({row.server_id_id for row in HaClusterSlave.select().where(HaClusterSlave.cluster_id == cluster_id)})
        nodes = []
        for ident in ids:
            server = server_sql.get_server_with_group(ident, group_id)
            if not server.enabled or server.type_ip:
                raise ValueError('Cluster members must be enabled physical server entries')
            nodes.append((server.hostname, server))
    else:
        raise ValueError('Select Keepalived or Pacemaker')
    if not re.fullmatch(r'[0-9a-f]{32}',cluster.readiness_key):
        raise RoxywiConflictError('Cluster registration identity is missing; complete the database migration')
    if not 2 <= len(nodes) <= 32:
        raise ValueError('A readiness audit requires 2–32 registered cluster members')
    return cluster, nodes


def subject_key(provider, cluster):
    return f'{provider}:{cluster.id}:{cluster.readiness_key}'


def profile(provider, cluster_id, group_id):
    cluster, _nodes = subject(provider, cluster_id, group_id)
    return HaReadinessProfile.get_or_none((HaReadinessProfile.group_id == group_id) &
        (HaReadinessProfile.provider == provider) & (HaReadinessProfile.cluster_id == cluster_id) &
        (HaReadinessProfile.registration_key == cluster.readiness_key))


def lock_registration(cluster, group_id):
    model=type(cluster)
    query=model.select().where((model.id==cluster.id)&(model.group_id==group_id))
    if not isinstance(model._meta.database,SqliteDatabase): query=query.for_update()
    current=query.first()
    if current is None or current.readiness_key!=cluster.readiness_key:
        raise RoxywiConflictError('Cluster registration changed; reload before continuing')


def domain_nodes(provider,cluster,nodes):
    result=list(nodes)
    if provider=='pacemaker':
        settings=json.loads(cluster.corosync_settings)
        ident=settings.get('qdevice_server_id')
        witness=None
        if ident:
            witness=server_sql.get_server_with_group(ident,cluster.group_id)
        elif settings.get('qdevice_host'):
            matches=list(Server.select().where((Server.group_id==str(cluster.group_id)) & (Server.ip==settings['qdevice_host'])))
            if len(matches)==1:witness=matches[0]
        if witness and witness.enabled and not witness.type_ip and witness.server_id not in {s.server_id for _n,s in nodes}:
            result.append(('Witness: '+witness.hostname,witness))
    return result


def public_profile(provider, cluster_id, group_id):
    cluster, nodes = subject(provider, cluster_id, group_id)
    row = profile(provider, cluster_id, group_id)
    return dict(registration_key=cluster.readiness_key, revision=row.revision if row else 0, domains=json.loads(row.domains) if row else {},
        attestations=json.loads(row.attestations) if row else [],
        nodes=[dict(id=server.server_id, name=name, ip=server.ip) for name, server in domain_nodes(provider,cluster,nodes)])


def save_profile(provider, cluster_id, group_id, body):
    cluster, nodes = subject(provider, cluster_id, group_id)
    if body.registration_key is not None and body.registration_key != cluster.readiness_key:
        raise RoxywiConflictError('Cluster registration changed; reload before saving')
    allowed = {server.server_id for _name, server in domain_nodes(provider,cluster,nodes)}
    if set(body.domains) - allowed or any(len(value) > 128 or any(ord(c) < 32 for c in value)
                                        for tags in body.domains.values() for value in tags.values()):
        raise ValueError('Failure domains must describe registered members with short labels')
    database=HaReadinessProfile._meta.database
    with database.atomic('IMMEDIATE') if isinstance(database,SqliteDatabase) else database.atomic():
        lock_registration(cluster,group_id)
        row = profile(provider, cluster_id, group_id)
        if row is None:
            if body.revision != 0:
                raise RoxywiConflictError('Failure domains changed; refresh the profile')
            row = HaReadinessProfile.create(group_id=group_id, provider=provider, cluster_id=cluster_id,
                registration_key=cluster.readiness_key)
            expected = row.revision
        else:
            expected = body.revision
        updated = HaReadinessProfile.update(domains=json.dumps(body.domains), revision=row.revision + 1).where(
            (HaReadinessProfile.id == row.id) & (HaReadinessProfile.revision == expected)).execute()
        if updated != 1:
            raise RoxywiConflictError('Failure domains changed; refresh the profile')
    return public_profile(provider, cluster_id, group_id)


def identities(nodes):
    return {str(server.server_id): dict(ip=server.ip, port=server.port, cred_id=server.cred_id, name=name)
            for name, server in nodes}


def enqueue(provider, cluster_id, group_id, user_id):
    cluster, nodes = subject(provider, cluster_id, group_id)
    label = subject_key(provider, cluster)
    database=OperationalAssessment._meta.database
    with database.atomic('IMMEDIATE') if isinstance(database,SqliteDatabase) else database.atomic():
        lock_registration(cluster,group_id)
        if (OperationalAssessment.select().join(InstallationTasks,on=(OperationalAssessment.task_id==InstallationTasks.id)).where(
            (OperationalAssessment.group_id==group_id) & (OperationalAssessment.kind=='ha-readiness') &
            (OperationalAssessment.subject==label) & InstallationTasks.status.in_(('created','published','running'))).exists()):
            raise RoxywiConflictError('A readiness audit is already queued or running')
        row = OperationalAssessment.create(group_id=group_id, user_id=user_id, kind='ha-readiness', subject=label)
        task = InstallationTasks.create(service_name=f'HA readiness: {cluster.name}', group_id=group_id,
            user_id=user_id, server_ids=[server.server_id for _name, server in nodes], operation_id=str(uuid4()),
            operation_type='ha-readiness', status='created', updated_at=utc_now(),
            operation_payload=serialize_operation_payload(dict(assessment_id=row.id, provider=provider,
                cluster_id=cluster_id, registration_key=cluster.readiness_key, identities=identities(nodes))))
        row.task_id=task.id; row.save()
    return row


def get_report(assessment_id, group_id):
    row=OperationalAssessment.get_or_none((OperationalAssessment.id == assessment_id) &
        (OperationalAssessment.group_id == group_id) & (OperationalAssessment.kind == 'ha-readiness'))
    if row is None:
        raise RoxywiResourceNotFound('Assessment not found')
    parts=row.subject.split(':')
    if len(parts)!=3:
        raise RoxywiResourceNotFound('Legacy assessment has no verified registration identity')
    provider, ident, registration=parts
    cluster, _nodes=subject(provider,int(ident),group_id)
    if registration != cluster.readiness_key:
        raise RoxywiResourceNotFound('Assessment belongs to a previous cluster registration')
    task=InstallationTasks.get_or_none(InstallationTasks.id == row.task_id)
    return dict(id=row.id, created_at=utc_iso(row.created_at), status=task.status if task else 'missing',
                error=task.error if task else None, report=deserialize_operation_payload(row.result) if row.result else None)


def attest(provider, cluster_id, group_id, user_id, body):
    cluster, _nodes=subject(provider,cluster_id,group_id)
    report=get_report(body.assessment_id,group_id)
    row=OperationalAssessment.get_by_id(body.assessment_id)
    if row.subject != subject_key(provider,cluster) or not report['report']:
        raise ValueError('Select a completed assessment of this cluster')
    tested=as_naive_utc(body.tested_at)
    if tested > utc_now() + timedelta(minutes=5):
        raise ValueError('A test cannot have a future date')
    if profile(provider,cluster_id,group_id) is None:
        save_profile(provider,cluster_id,group_id,ProfileRequest(revision=0,domains={}))
    database=HaReadinessProfile._meta.database
    with database.atomic('IMMEDIATE') if isinstance(database,SqliteDatabase) else database.atomic():
        lock_registration(cluster,group_id)
        current=profile(provider,cluster_id,group_id)
        values=json.loads(current.attestations)
        values.append(dict(kind=body.kind,result=body.result,tested_at=utc_iso(tested),note=body.note,
            recorded_at=utc_iso(utc_now()),user_id=user_id,source='operator-attestation',
            fingerprint=report['report']['fingerprint'],assessment_id=body.assessment_id))
        if HaReadinessProfile.update(attestations=json.dumps(values[-100:]),revision=current.revision+1).where(
            (HaReadinessProfile.id == current.id) & (HaReadinessProfile.revision == current.revision)).execute()!=1:
            raise RoxywiConflictError('Test records changed; refresh and retry')
    return public_profile(provider,cluster_id,group_id)


def check(key, state, message, evidence=None):
    return dict(key=key,state=state,message=message,evidence=evidence or {})


def fencing_metadata(config, resource, parents):
    """Resolve unconditional metadata from defaults to the nearest resource."""
    lineage=[]
    ancestor=resource
    while ancestor is not None:
        lineage.append(ancestor.findall('./meta_attributes'))
        ancestor=parents.get(ancestor)
    levels=[config.findall('./rsc_defaults/meta_attributes'), *reversed(lineage)]
    effective={}
    for groups in levels:
        values={}
        for group in groups:
            if group.find('.//rule') is not None or any(node.get('id-ref') for node in group.iter()):
                return None
            for pair in group.findall('nvpair'):
                name,value=pair.get('name'),pair.get('value')
                if not name or value is None or value.lower()=='#default':
                    return None
                # Conflicting sets at one level need Pacemaker's score/rule
                # resolution. Do not guess their precedence from XML order.
                if name in values and values[name]!=value:
                    return None
                values[name]=value
        effective.update(values)
    return effective


def fencing(xml, names):
    config=configuration(xml)
    # Rule/template/id-ref dependent coverage cannot be established by this read.
    properties={v.get('name'):v.get('value') for v in config.findall('./crm_config/cluster_property_set/nvpair')}
    enabled=properties.get('stonith-enabled','true').lower() not in ('false','0','off')
    result={name:[] for name in names}; uncertain=False
    parents={child:parent for parent in config.iter() for child in parent}
    for resource in config.findall('./resources//primitive'):
        if resource.get('class')!='stonith':
            if resource.get('template'): uncertain=True
            continue
        metadata=fencing_metadata(config,resource,parents)
        if resource.get('template') or metadata is None:
            uncertain=True
            continue
        groups=resource.findall('./instance_attributes')
        if any(g.get('id-ref') or g.find('rule') is not None for g in groups): uncertain=True; continue
        params={v.get('name'):v.get('value','') for group in groups for v in group.findall('nvpair')}
        role=metadata.get('target-role','Started').lower()
        managed=metadata.get('is-managed','true').lower()
        if role not in ('started','stopped','unpromoted','promoted','master','slave') or managed not in ('true','1','on','yes','y','false','0','off','no','n'):
            uncertain=True
            continue
        if role=='stopped' or managed in ('false','0','off','no','n'):
            continue
        hosts=set(re.split(r'[\s,;]+',params.get('pcmk_host_list','')))
        hosts.update(item.split(':',1)[0] for item in params.get('pcmk_host_map','').split(';'))
        if not (params.get('pcmk_host_list') or params.get('pcmk_host_map')): uncertain=True
        for name in names:
            if name in hosts: result[name].append(resource.get('id'))
    return check('fencing','fail' if not enabled else 'warning' if not all(result.values()) or uncertain else 'configured',
        'Static fencing coverage is configuration evidence only; successful isolation has not been tested by this audit.',
        dict(enabled=enabled,coverage=result,dynamic_or_conditional=uncertain))


def pacemaker_node(cluster, name, server):
    remote=Remote(server)
    actual=remote.run(['corosync-cmapctl','totem.cluster_name']).strip().split(' = ',1)[-1]
    if actual!=cluster.name: raise ValueError('Cluster identity changed')
    xml=remote.run(['cibadmin','--query'])
    corosync_digest=remote.run(['python3','-c',
        "import hashlib,pathlib; p=pathlib.Path('/etc/corosync/corosync.conf'); b=p.read_bytes(); assert len(b)<=1048576; print(hashlib.sha256(b).hexdigest())"]).strip()
    if not re.fullmatch(r'[0-9a-f]{64}',corosync_digest): raise ValueError('Invalid Corosync configuration hash')
    state=summary(remote.run(['crm_mon','--one-shot','--output-as=xml'],allowed=(0,1,2)))
    quorum=details(remote.run(['env','LC_ALL=C','corosync-quorumtool','-s'],allowed=(0,2)))
    client=''
    if quorum['configured']:
        try: client=remote.run(['env','LC_ALL=C','corosync-qdevice-tool','-s','-v'])
        except Exception: pass
    witness=re.search(r'^QNetd host:\s+(\S+)\s*$',client,re.M)
    return dict(id=server.server_id,name=name,digest=digest(xml),corosync_digest=corosync_digest,state=state,quorum=quorum,
        witness=dict(tls=bool(re.search(r'^TLS active:[ \t]+Yes(?:[ \t]+\([^\r\n]*\))?[ \t]*$',client,re.M)),
                     host=witness[1] if witness else None),_xml=xml)


KEEPALIVED_PROBE=r'''
import hashlib,json,pathlib,subprocess,sys
data=json.load(sys.stdin)
path=pathlib.Path(data['path'])
if not path.is_absolute() or path.is_symlink() or path.stat().st_size>1048576:raise ValueError('Unsupported configuration file')
text=path.read_text()
# Do not return auth_pass, scripts, comments or configuration text.
active=subprocess.run(['systemctl','is-active','keepalived'],capture_output=True,text=True,timeout=10).stdout.strip()=='active'
addresses=json.loads(subprocess.run(['ip','-j','address','show'],check=True,capture_output=True,text=True,timeout=10).stdout)
print(json.dumps(dict(digest=hashlib.sha256(text.encode()).hexdigest(),active=active,
    includes=bool(__import__('re').search(r'^\s*include\s',text,__import__('re').M)),
    addresses=sorted({a['local'] for i in addresses for a in i.get('addr_info',[])}))))
'''


def keepalived_node(cluster, name, server):
    from app.modules.db import sql, service as service_sql
    from app.modules.service import container_settings
    info=json.loads(Remote(server).run(['python3','-c',KEEPALIVED_PROBE],
        data=json.dumps(dict(path=sql.get_setting('keepalived_config_path',group_id=cluster.group_id)))))
    if service_sql.select_service_setting(server.server_id,'keepalived','dockerized')=='1':
        state=container_settings.keepalived_state(server)
        info['active']=state in ('MASTER','BACKUP','FAULT','INIT')
        info['runtime_state']=state
    return dict(id=server.server_id,name=name,**info)


def domain_checks(nodes, domains):
    result=[]
    for kind in ('hypervisor','power','uplink','storage'):
        labels={str(node['id']):domains.get(str(node['id']),{}).get(kind,'') for node in nodes}
        known=[label for label in labels.values() if label]
        shared=sorted({label for label in known if known.count(label)>1})
        result.append(check('domain:'+kind,'warning' if shared else 'unknown' if len(known)!=len(nodes) else 'declared',
            'Operator-declared failure domains; guest identity does not prove physical independence.',dict(labels=labels,shared=shared)))
    return result


def collect(provider, cluster, nodes, current_profile, heartbeat=lambda:None):
    observations=[]
    for name,server in nodes:
        try:
            with group_settings(cluster.group_id):
                value=(pacemaker_node if provider=='pacemaker' else keepalived_node)(cluster,name,server)
        except Exception:
            value=dict(id=server.server_id,name=name,error='Node could not be verified; inspect SSH access and cluster identity')
        observations.append(value)
        heartbeat()
    readable=[value for value in observations if not value.get('error')]
    checks=[check('members','observed' if len(readable)==len(nodes) else 'fail',
        'Read every registered member independently.',dict(reachable=len(readable),registered=len(nodes)))]
    digests={str(value['id']):value['digest'] for value in readable}
    checks.append(check('configuration','observed' if len(set(digests.values()))==1 and len(readable)==len(nodes) else 'warning',
        'Persistent configuration hashes; Keepalived role/priority differences can be intentional.',dict(digests=digests)))
    if provider=='pacemaker':
        names={name for name,_server in nodes}
        healthy=bool(readable) and len(readable)==len(nodes) and all(v['state']['quorate'] and
            {n['name'] for n in v['state']['nodes'] if n['online']=='true' and n['unclean']!='true'}==names and
            not v['state']['failures'] for v in readable)
        checks.append(check('quorum','observed' if healthy else 'fail','Quorum, member visibility and failures on every member.'))
        checks.append(check('corosync-configuration','observed' if len(readable)==len(nodes) and len({v['corosync_digest'] for v in readable})==1 else 'warning',
            'Corosync configuration hashes from every member.',dict(digests={str(v['id']):v['corosync_digest'] for v in readable})))
        witness_required=len(nodes)==2 or any(v['quorum']['configured'] for v in readable)
        working=bool(readable) and len(readable)==len(nodes) and len({v['witness']['host'] for v in readable})==1 and all(v['quorum']['votes']>=1 and v['witness']['tls'] and v['witness']['host'] for v in readable)
        checks.append(check('witness','observed' if working else 'fail' if witness_required else 'not-applicable',
            'An overall quorate state does not prove a working witness vote. A witness is recommended for two members.',
            dict(nodes={str(v['id']):dict(**v['quorum'],**v['witness']) for v in readable})))
        witnesses={v['witness']['host'] for v in readable if v['witness']['host']}
        checks.append(check('witness-independence','warning' if any(s.ip+':5403' in witnesses for _n,s in nodes) else 'unknown',
            'A separate address does not prove a separate hypervisor, power supply or network path.'))
        if readable: checks.append(fencing(readable[0]['_xml'],names))
        else: checks.append(check('fencing','unknown','No readable CIB; fencing cannot be assessed.'))
    else:
        vips=[v.vip.split('/')[0] for v in HaClusterVip.select().where(HaClusterVip.cluster_id==cluster.id)]
        ownership={vip:[str(v['id']) for v in readable if vip in v['addresses']] for vip in vips}
        checks.append(check('vip-ownership','observed' if ownership and len(readable)==len(nodes) and all(len(v)==1 for v in ownership.values()) else 'fail',
            'Each registered VIP must be present on exactly one reachable member.',dict(owners=ownership)))
        checks.append(check('service','observed' if len(readable)==len(nodes) and all(v['active'] for v in readable) else 'fail',
            'Current Keepalived process activity; this does not test partition handling.'))
        checks.extend([check('quorum','not-applicable','VRRP does not provide cluster quorum or a witness vote.'),
            check('fencing','warning','Keepalived does not provide Pacemaker-style fencing; a network partition can create competing owners.')])
        if any(v.get('includes') for v in readable): checks.append(check('includes','unknown','Included Keepalived files need separate review; the hash covers the main file.'))
    physical=[dict(id=s.server_id,name=n) for n,s in domain_nodes(provider,cluster,nodes)]
    checks.extend(domain_checks(physical,json.loads(current_profile.domains) if current_profile else {}))
    for node in observations: node.pop('_xml',None)
    fingerprint=hashlib.sha256(json.dumps(dict(provider=provider,registration_key=cluster.readiness_key,members=identities(nodes),digests=digests,
        corosync={str(v['id']):v.get('corosync_digest') for v in readable},
        domains=json.loads(current_profile.domains) if current_profile else {}),sort_keys=True).encode()).hexdigest()
    attestations=json.loads(current_profile.attestations) if current_profile else []
    matches=[dict(item,configuration_current=item['fingerprint']==fingerprint) for item in attestations]
    checks.append(check('verification','unknown','This read-only audit performs no switchover, fencing or partition test. Operator records are labelled separately.'))
    return dict(provider=provider,cluster_id=cluster.id,name=cluster.name,observed_at=utc_iso(utc_now()),
        fingerprint=fingerprint,nodes=observations,checks=checks,attestations=matches,last_verified_test=None)


def execute(task):
    task=InstallationTasks.get_by_id(task.id)
    if task.status in ('completed','failed'): return task.status
    payload=deserialize_operation_payload(task.operation_payload)
    row=None
    try:
        actor=User.get_or_none(User.user_id==task.user_id_id)
        if not actor or not actor.enabled or '5' not in user_sql.select_user_services(actor.user_id).split() or int(user_sql.get_user_role_in_group(actor.user_id,task.group_id_id))>3:
            raise ValueError('HA audit permissions were revoked')
        row=OperationalAssessment.get((OperationalAssessment.id==payload['assessment_id']) &
            (OperationalAssessment.group_id==task.group_id_id) & (OperationalAssessment.task_id==task.id))
        cluster,nodes=subject(payload['provider'],payload['cluster_id'],task.group_id_id)
        if payload.get('registration_key')!=cluster.readiness_key or row.subject!=subject_key(payload['provider'],cluster):
            raise ValueError('Cluster registration changed')
        if payload['identities']!=identities(nodes): raise ValueError('Cluster membership or SSH identity changed')
        result=collect(payload['provider'],cluster,nodes,profile(payload['provider'],cluster.id,task.group_id_id),
            heartbeat=lambda:InstallationTasks.update(updated_at=utc_now()).where(InstallationTasks.id==task.id).execute())
        _cluster,again=subject(payload['provider'],cluster.id,task.group_id_id)
        if _cluster.readiness_key!=payload['registration_key'] or identities(again)!=payload['identities']: raise ValueError('Cluster membership changed during audit')
        OperationalAssessment.update(result=serialize_operation_payload(result)).where(
            (OperationalAssessment.id==row.id) & (OperationalAssessment.result=='')).execute()
        state,error='completed',None
    except Exception:
        state,error='failed','HA assessment could not complete; refresh membership, permissions and SSH access before retrying'
    InstallationTasks.update(status=state,error=error,finish_date=utc_now(),updated_at=utc_now()).where(
        (InstallationTasks.id==task.id) & InstallationTasks.status.not_in(('completed','failed'))).execute()
    return InstallationTasks.get_by_id(task.id).status
