"""Reviewed IP-feed versions on the durable Operations and Change Center queues."""
from contextlib import ExitStack
from datetime import timedelta
import difflib
import json
from pathlib import Path
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field
from peewee import SqliteDatabase
from app.modules.common.execution_context import group_settings
from app.modules.common.file_lock import file_lock
from app.modules.common.time import utc_now, utc_iso
from app.modules.connectors import ip_feeds, containers
from app.modules.db import user as user_sql, sql
from app.modules.db.db_model import ManagedAclFeed,ManagedAclVersion,InstallationTasks,ConfigChange,User,Server,PacemakerCluster
from app.modules.operations.queue import serialize_operation_payload as seal,deserialize_operation_payload as unseal
from app.modules.pacemaker.remote import Remote
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi.exception import RoxywiResourceNotFound,RoxywiConflictError,RoxywiPermissionError
from app.modules.service import proxy_assessments as assessments,certificates,haproxy_runtime
from app.modules.config import candidate,haproxy_discovery
from app.modules.service.le.le_store import transaction,locked
from app.modules.subscription.access import CHANGE_CENTER,require_feature


class Target(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    server_id: int=Field(gt=0)
    path: str=Field(pattern=r'^/[A-Za-z0-9_./-]{1,4095}$')


class FeedRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    name: str=Field(min_length=1,max_length=128)
    provider: str=Field(default='https-ip-list',max_length=64)
    settings: dict
    targets: list[Target]=Field(min_length=1,max_length=32)
    interval_minutes: int=Field(default=360,ge=5,le=10080)
    stale_hours: int=Field(default=24,ge=1,le=8760)
    enabled: bool=Field(default=False,strict=True)
    revision: int|None=Field(default=None,gt=0)


def get(ident,group_id):
    row=ManagedAclFeed.get_or_none((ManagedAclFeed.id==ident)&(ManagedAclFeed.group_id==group_id))
    if row is None:raise RoxywiResourceNotFound('ACL feed not found')
    return row


def version(ident,row):
    value=ManagedAclVersion.get_or_none((ManagedAclVersion.id==ident)&(ManagedAclVersion.feed_id==row.id)&(ManagedAclVersion.group_id==row.group_id))
    if value is None:raise RoxywiResourceNotFound('ACL version not found')
    return value


def authorize(row,user_id,*,write=False):
    data=unseal(row.configuration);result=[];seen=set()
    for target in data['targets']:
        server=assessments.authorize(target['server_id'],'haproxy',row.group_id,user_id,probe=write)
        if server.server_id in seen:raise ValueError('Select one ACL per proxy node in a feed')
        if write and server.protected and int(user_sql.get_user_role_in_group(user_id,row.group_id))>2:
            raise RoxywiPermissionError('An administrator must update a protected proxy')
        seen.add(server.server_id);result.append(server)
    return data,result


def source_approved(row):
    actor=User.get_or_none(User.user_id==row.approved_by)
    if row.approved_revision!=row.revision or not actor or not actor.enabled or '1' not in user_sql.select_user_services(actor.user_id).split():
        raise RoxywiConflictError('An administrator must approve the current source and targets')
    role=int(user_sql.get_user_role_in_group(actor.user_id,row.group_id) or 4)
    if role>(1 if elevated_source(unseal(row.configuration)['settings']) else 2):
        raise RoxywiPermissionError('The source approver no longer has sufficient permissions')


def elevated_source(settings):
    return settings['allow_private'] or settings['min_ipv4_prefix']<8 or settings['min_ipv6_prefix']<16


def busy(row):
    if not row.active_task_id:return False
    task=InstallationTasks.get_or_none((InstallationTasks.id==row.active_task_id)&(InstallationTasks.group_id==row.group_id))
    return task is None or task.status not in ('completed','failed')


def editable(row):
    if busy(row) or ManagedAclVersion.select().where((ManagedAclVersion.feed_id==row.id)&ManagedAclVersion.status.in_(('deploying','recovery-required'))).exists():
        raise RoxywiConflictError('Finish the active ACL operation or recovery first')


def save(body,group_id,user_id,ident=None):
    data=body.model_dump();revision=data.pop('revision');data['settings']=ip_feeds.provider(data['provider']).settings_model.model_validate(data['settings']).model_dump()
    temporary=ManagedAclFeed(group_id=group_id,configuration=seal(data));_data,servers=authorize(temporary,user_id,write=True)
    # Every target must be discovered; a submitted path cannot choose arbitrary files.
    for target,server in zip(data['targets'],servers):
        found=remote(server,'discover')
        if target['path'] not in {item['path'] for item in found['lists']}:raise ValueError('Select a discovered persistent src IP ACL')
    if ident:get(ident,group_id)
    with transaction():
        if not isinstance(Server._meta.database,SqliteDatabase):list(Server.select().where(Server.server_id.in_([s.server_id for s in servers])).order_by(Server.server_id).for_update())
        row=locked(ManagedAclFeed,(ManagedAclFeed.id==ident)&(ManagedAclFeed.group_id==group_id)) if ident else None
        if row:
            editable(row)
            if row.revision!=revision:raise RoxywiConflictError('Feed changed; reload it')
        elif ident:raise RoxywiResourceNotFound()
        elif ManagedAclFeed.select().where(ManagedAclFeed.group_id==group_id).count()>=256:raise ValueError('A group supports at most 256 ACL feeds')
        for other in ManagedAclFeed.select().where(ManagedAclFeed.group_id==group_id):
            if row and other.id==row.id:continue
            occupied={(t['server_id'],t['path']) for t in unseal(other.configuration)['targets']}
            if occupied&{(t['server_id'],t['path']) for t in data['targets']}:raise RoxywiConflictError('Another feed owns this ACL target')
        if row:row.revision+=1
        else:row=ManagedAclFeed(group_id=group_id,revision=1)
        row.name=data['name'];row.user_id=user_id;row.provider=data['provider'];row.configuration=seal(data);row.enabled=data['enabled']
        row.approved_revision=None;row.approved_by=None;row.approved_at=None;row.next_check=None;row.active_task_id=None;row.save()
    return row


def approve(row,user_id,revision):
    data,_servers=authorize(row,user_id,write=True)
    role=int(user_sql.get_user_role_in_group(user_id,row.group_id) or 4)
    if role>(1 if elevated_source(data['settings']) else 2):raise RoxywiPermissionError('Administrator approval is required for this source scope')
    with transaction():
        row=locked(ManagedAclFeed,(ManagedAclFeed.id==row.id)&(ManagedAclFeed.group_id==row.group_id));editable(row)
        if revision!=row.revision:raise RoxywiConflictError('Source changed before approval')
        row.approved_revision=row.revision;row.approved_by=user_id;row.approved_at=utc_now();row.next_check=utc_now() if row.enabled else None;row.save()
    return row


def remote_source():
    from app.scripts import certificate_remote,certificate_cluster_remote,certificate_passive
    source=containers.embedded()
    for name,module in (('roxywi_config_candidate',candidate),('roxywi_haproxy_runtime',haproxy_runtime),('roxywi_haproxy_discovery',haproxy_discovery),
                        ('roxywi_certificate_cluster',certificate_cluster_remote),('roxywi_certificate_passive',certificate_passive),('roxywi_certificate_remote',certificate_remote)):
        text=Path(module.__file__).read_text()
        source+='\nimport types,sys\nmodule=types.ModuleType('+repr(name)+')\nsys.modules[module.__name__]=module\n'
        source+='module.__source__='+repr(text)+'\nexec(compile('+repr(text)+','+repr(name)+',"exec"),module.__dict__)\n'
    return source+Path(__file__).resolve().parents[2].joinpath('scripts/acl_feed_remote.py').read_text()


def remote_spec(server):
    with group_settings(server.group_id):
        transport=certificates.deployment_settings(server,'',verify_startup=True)
        return dict(root=sql.get_setting('haproxy_dir'),validation=transport['validation'],transport=transport)


def remote(server,operation,*,spec=None,**data):
    source=remote_source();encoded=source.encode()
    if len(encoded)>512*1024:raise ValueError('ACL helper exceeds its frame limit')
    result=json.loads(Remote(server).run(['python3','-c',certificates.REMOTE_BOOTSTRAP],
        data=format(len(encoded),'x')+'\n'+source+json.dumps(dict(spec or remote_spec(server),operation=operation,**data)),timeout=240))
    if result.get('error'):raise RoxywiConflictError('Remote ACL transaction could not be verified; inspect its recovery state')
    return result


def public(row,user_id):
    data,_servers=authorize(row,user_id)
    task=InstallationTasks.get_or_none((InstallationTasks.id==row.active_task_id)&(InstallationTasks.group_id==row.group_id)) if row.active_task_id else None
    data.update(id=row.id,revision=row.revision,approved_revision=row.approved_revision,approved_by=row.approved_by,
        approved_at=utc_iso(row.approved_at),last_check=utc_iso(row.last_check),next_check=utc_iso(row.next_check),
        stale=not row.last_check or row.last_check<utc_now()-timedelta(hours=data['stale_hours']),error=row.last_error,
        deployed_version_id=row.deployed_version_id,operation=dict(id=task.id,status=task.status,error=task.error) if task else None)
    return data


def public_version(value):
    details=unseal(value.details) if value.details else {};change=ConfigChange.get_or_none((ConfigChange.id==value.change_id)&(ConfigChange.group_id==value.group_id)) if value.change_id else None
    return dict(id=value.id,created_at=utc_iso(value.created_at),revision=value.feed_revision,status=value.status,fingerprint=value.fingerprint,
        entries=value.entries,change_id=value.change_id,change_status=change.status if change else None,
        diff=details.get('diff'),diff_truncated=details.get('diff_truncated',False),targets=[dict(server_id=t['server_id'],path=t['path'],added=t['added'],removed=t['removed']) for t in details.get('targets',[])],
        events=details.get('events',[]))


def enqueue(row,user_id,action,version_id=None):
    if action not in ('fetch','review','apply','recover','rollback-version'):raise ValueError('Unsupported ACL action')
    if action!='fetch':require_feature(CHANGE_CENTER)
    with transaction():
        row=locked(ManagedAclFeed,(ManagedAclFeed.id==row.id)&(ManagedAclFeed.group_id==row.group_id))
        data,servers=authorize(row,user_id,write=True)
        if action!='recover':source_approved(row)
        if busy(row):raise RoxywiConflictError('An ACL operation is already queued')
        if action!='recover':editable(row)
        selected=version(version_id,row) if version_id else None
        if action!='fetch' and (selected is None or (action!='rollback-version' and selected.feed_revision!=row.revision)):raise RoxywiConflictError('Select a version of the current approved feed revision')
        if action=='review' and selected.status not in ('downloaded','reviewed','rolled-back','deployed'):raise RoxywiConflictError('This version cannot be reviewed')
        if action=='apply':approval(selected,row)
        if action=='recover' and selected.status not in ('deploying','recovery-required'):raise RoxywiConflictError('No ACL recovery is pending')
        if action=='rollback-version' and selected.status not in ('deployed','reviewed','rolled-back'):raise RoxywiConflictError('Select a previously reviewed version for rollback')
        payload=dict(feed_id=row.id,revision=row.revision,action=action,version_id=selected.id if selected else None,
            identities=[assessments.identity(s,'haproxy') for s in servers])
        task=InstallationTasks.create(service_name='ACL feed: '+row.name+' · '+action,group_id=row.group_id,user_id=user_id,
            server_ids=[s.server_id for s in servers],operation_type='managed-acl',operation_id=str(uuid4()),
            status='created',updated_at=utc_now(),operation_payload=seal(payload))
        row.active_task_id=task.id;row.save()
    return task


def approval(value,row):
    change=ConfigChange.get_or_none((ConfigChange.id==value.change_id)&(ConfigChange.group_id==row.group_id)&(ConfigChange.action=='acl-feed'))
    if value.status!='reviewed' or not change or change.status!='approved' or not change.approved_by:raise RoxywiConflictError('Approve this ACL review in Change Center')
    valid_approver(change,row)
    return change


def valid_approver(change,row):
    actor=User.get_or_none(User.user_id==change.approved_by)
    if not actor or not actor.enabled or actor.user_id==change.user_id or int(user_sql.get_user_role_in_group(actor.user_id,row.group_id) or 4)>2 or '1' not in user_sql.select_user_services(actor.user_id).split():
        raise RoxywiPermissionError('The independent ACL approver no longer has permission')


def update_details(value,details):
    if len(json.dumps(details).encode())>2*1024*1024:raise ValueError('ACL review exceeds 2 MiB; reduce targets/feed size')
    ManagedAclVersion.update(details=seal(details),status=value.status,change_id=value.change_id).where(ManagedAclVersion.id==value.id).execute()


def review(value,row,servers,user_id,heartbeat):
    from app.modules.config.deployment_policy import require_change_center_creation
    require_change_center_creation(row.group_id,'haproxy')
    content=unseal(value.content)['text'];data=unseal(row.configuration);targets=[]
    for target,server in zip(data['targets'],servers):
        spec=remote_spec(server);before=remote(server,'preview',spec=spec,path=target['path']);heartbeat()
        old=set(before['content'].splitlines());new=set(content.splitlines())
        targets.append(dict(server_id=server.server_id,path=target['path'],spec=spec,expected=before,identity=assessments.identity(server,'haproxy'),
            added=len(new-old),removed=len(old-new)))
    previous=version(row.deployed_version_id,row) if row.deployed_version_id else None
    baseline=unseal(previous.content)['text'] if previous else ''
    diff=''.join(difflib.unified_diff(baseline.splitlines(True),content.splitlines(True),fromfile='last deployed version',tofile='downloaded candidate'))
    # A full oversized diff remains available through immutable version content;
    # Change Center receives bounded evidence and the exact candidate fingerprint.
    details=dict(targets=targets,diff=diff[:60000],diff_truncated=len(diff)>60000,phase='reviewed',events=[])
    if len(json.dumps(details).encode())>2*1024*1024:raise ValueError('ACL review exceeds its size limit')
    with transaction():
        if value.change_id:
            old=ConfigChange.get_by_id(value.change_id)
            if old.active_task_id:raise RoxywiConflictError('An old ACL review is active')
            ConfigChange.update(status='cancelled').where(ConfigChange.id==old.id).execute()
        change=ConfigChange.create(server_id=servers[0].server_id,group_id=row.group_id,user_id=user_id,service='haproxy',action='acl-feed',
            title='ACL feed: '+row.name+' · version #'+str(value.id),description='IP/CIDR feed deployment; exact fingerprint '+value.fingerprint,
            remote_path=f'feed://{row.id}/{value.id}',draft_path='',rollback_path='',requires_approval=1,status='pending_approval',
            diff=diff[:60000],validation_output=json.dumps([dict(server_id=t['server_id'],path=t['path'],added=t['added'],removed=t['removed']) for t in targets])[:60000])
        value.change_id=change.id;value.status='reviewed';update_details(value,details)


def apply(value,row,servers,task,heartbeat,*,recover=False):
    details=unseal(value.details);content=unseal(value.content)['text'];change=ConfigChange.get_by_id(value.change_id)
    if details.get('phase')=='done' and value.status in ('deployed','rolled-back'):return
    if not recover:
        approval(value,row)
        details.update(phase='prepare',transaction=str(uuid4()));value.status='deploying';update_details(value,details)
    if details.get('phase') not in ('prepare','apply','rollback','commit'):raise ValueError('No recoverable transaction phase')
    if details['phase'] in ('prepare','apply'):
        try:
            if change.status not in ('approved','deploying'):raise RoxywiConflictError('ACL approval was withdrawn')
            valid_approver(change,row)
        except Exception:
            details['phase']='rollback';value.status='recovery-required';update_details(value,details)
    ConfigChange.update(active_task_id=task.id,last_task_id=task.id,status='deploying').where(ConfigChange.id==change.id).execute()
    def invoke(target,operation):
        server=Server.get_by_id(target['server_id'])
        if str(server.group_id)!=str(row.group_id) or assessments.identity(server,'haproxy')!=target['identity']:
            raise RoxywiConflictError('Reviewed proxy identity changed; inspect the original host before recovery')
        def event(state):
            details.setdefault('events',[]).append(dict(at=utc_iso(utc_now()),server_id=server.server_id,operation=operation,state=state))
            details['events']=details['events'][-512:];update_details(value,details)
        event('requested')
        result=remote(server,operation,spec=target['spec'],path=target['path'],expected=target['expected'],content=content,transaction=details['transaction'])
        event('verified')
        heartbeat();return result
    try:
        if details['phase']=='prepare':
            for target in details['targets']:invoke(target,'prepare')
            details['phase']='apply';update_details(value,details)
        if details['phase']=='apply':
            for target in details['targets']:
                source_approved(row)
                # Revalidate the independent approval before every live commit.
                current=ConfigChange.get_by_id(change.id)
                if current.approved_by!=change.approved_by or current.status not in ('approved','deploying'):raise RoxywiConflictError('ACL approval was revoked')
                valid_approver(current,row)
                authorize(row,task.user_id_id,write=True)
                invoke(target,'apply')
            details['phase']='commit';update_details(value,details)
        if details['phase']=='commit':
            for target in details['targets']:invoke(target,'commit')
            value.status='deployed';details['phase']='done';update_details(value,details)
            ManagedAclFeed.update(deployed_version_id=value.id).where(ManagedAclFeed.id==row.id).execute()
            ConfigChange.update(status='deployed',deployed_at=utc_now()).where(ConfigChange.id==change.id).execute()
            return
    except Exception:
        if details['phase']=='commit':
            value.status='recovery-required';update_details(value,details)
            ConfigChange.update(status='deployment_interrupted').where(ConfigChange.id==change.id).execute()
            raise
        details['phase']='rollback';value.status='recovery-required';update_details(value,details)
    if details['phase']=='rollback':
        for target in details['targets']:invoke(target,'rollback')
        details['phase']='done';value.status='rolled-back';update_details(value,details)
        ConfigChange.update(status='auto_rolled_back').where(ConfigChange.id==change.id).execute()
        if not recover:raise RoxywiConflictError('ACL deployment was rolled back; inspect and review again')


def execute(task):
    task=InstallationTasks.get_by_id(task.id)
    if task.status in ('completed','failed'):return task.status
    payload=unseal(task.operation_payload);root=Path(GetConfigVar().get_config_var('main','lib_path'))/'acl-feed-locks';root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with file_lock(root/(str(int(payload['feed_id']))+'.lock')):
        row=None;selected=None;error=None;state='failed'
        try:
            row=get(payload['feed_id'],task.group_id_id)
            if row.revision!=payload['revision'] or row.active_task_id!=task.id:raise RoxywiConflictError('Feed changed after queuing')
            data,servers=authorize(row,task.user_id_id,write=True)
            if payload['action']!='recover':source_approved(row)
            if [assessments.identity(s,'haproxy') for s in servers]!=payload['identities']:raise RoxywiConflictError('Proxy identity changed after queuing')
            def heartbeat():InstallationTasks.update(updated_at=utc_now()).where(InstallationTasks.id==task.id).execute()
            action=payload['action'];selected=version(payload['version_id'],row) if payload.get('version_id') else None
            if action=='fetch':
                content=ip_feeds.normalize(ip_feeds.provider(row.provider).fetch(data['settings']),data['settings']);heartbeat()
                # Recheck approval and permission after an untrusted download.
                fresh=get(row.id,row.group_id);source_approved(fresh);authorize(fresh,task.user_id_id,write=True)
                if fresh.revision!=row.revision:raise RoxywiConflictError('Source changed during download')
                latest=ManagedAclVersion.select().where((ManagedAclVersion.feed_id==row.id)&(ManagedAclVersion.feed_revision==row.revision)).order_by(ManagedAclVersion.id.desc()).first()
                if not latest or latest.fingerprint!=ip_feeds.fingerprint(content):
                    ManagedAclVersion.create(feed_id=row.id,group_id=row.group_id,user_id=task.user_id_id,feed_revision=row.revision,
                        content=seal(dict(text=content)),fingerprint=ip_feeds.fingerprint(content),entries=len(content.splitlines()))
            elif action in ('review','rollback-version'):
                require_feature(CHANGE_CENTER)
                if action=='rollback-version':
                    normalized=ip_feeds.normalize(unseal(selected.content)['text'],data['settings'])
                    selected=ManagedAclVersion.create(feed_id=row.id,group_id=row.group_id,user_id=task.user_id_id,feed_revision=row.revision,
                        content=seal(dict(text=normalized)),fingerprint=ip_feeds.fingerprint(normalized),entries=len(normalized.splitlines()))
                review(selected,row,servers,task.user_id_id,heartbeat)
            elif action in ('apply','recover'):
                require_feature(CHANGE_CENTER)
                from app.modules.service.ha_maintenance import assert_server_idle
                from app.modules.pacemaker import service as cluster_service
                with ExitStack() as locks:
                    ids={s.server_id for s in servers}
                    for server in servers:assert_server_idle(server.server_id)
                    for cluster in PacemakerCluster.select().where(PacemakerCluster.group_id==row.group_id).order_by(PacemakerCluster.id):
                        if ids & {int(m['server_id']) for m in json.loads(cluster.servers)}:
                            if '5' not in user_sql.select_user_services(task.user_id_id).split():raise RoxywiPermissionError('Cluster permission is required for these ACL targets')
                            locks.enter_context(cluster_service.locked(cluster))
                    apply(selected,row,servers,task,heartbeat,recover=action=='recover' or selected.status in ('deploying','recovery-required'))
            else:raise ValueError('Unsupported ACL operation')
            state='completed'
        except Exception:error='ACL operation failed; inspect source approval, target discovery, Change Center review and recovery status'
        finally:
            if row:
                fields=dict(active_task_id=None,last_error=error)
                if payload['action']=='fetch':fields.update(last_check=utc_now() if state=='completed' else row.last_check,
                    next_check=utc_now()+timedelta(minutes=unseal(row.configuration)['interval_minutes']) if row.enabled else None)
                ManagedAclFeed.update(**fields).where((ManagedAclFeed.id==row.id)&(ManagedAclFeed.active_task_id==task.id)).execute()
            if selected and selected.change_id:
                ConfigChange.update(active_task_id=None,updated_at=utc_now()).where((ConfigChange.id==selected.change_id)&(ConfigChange.active_task_id==task.id)).execute()
            InstallationTasks.update(status=state,error=error,finish_date=utc_now(),updated_at=utc_now()).where(InstallationTasks.id==task.id).execute()
        return state


def dispatch_due(limit=25):
    now=utc_now();count=0
    for row in ManagedAclFeed.select().where(ManagedAclFeed.enabled&(ManagedAclFeed.next_check<=now)).limit(limit):
        try:enqueue(row,row.user_id,'fetch');count+=1
        except Exception:ManagedAclFeed.update(next_check=now+timedelta(minutes=15)).where(ManagedAclFeed.id==row.id).execute()
    return count
