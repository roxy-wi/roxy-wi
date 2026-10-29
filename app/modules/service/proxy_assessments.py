"""Durable, group-scoped request-path diagnostics over discovered proxy targets."""
import base64
import ipaddress
import json
import ssl
from typing import Literal
from urllib.parse import urlsplit,urlunsplit,unquote
from uuid import uuid4
from pydantic import BaseModel,ConfigDict,Field,field_validator
from peewee import SqliteDatabase
from app.modules.common.execution_context import group_settings
from app.modules.common.time import utc_now,utc_iso
from app.modules.db.db_model import Server,User,InstallationTasks,OperationalAssessment
from app.modules.db import user as user_sql,service as service_sql
from app.modules.operations.queue import serialize_operation_payload as seal,deserialize_operation_payload as unseal
from app.modules.pacemaker.remote import Remote
from app.modules.roxywi.exception import RoxywiPermissionError,RoxywiResourceNotFound,RoxywiConflictError
from app.modules.service import published_endpoints as inventory,network_probe as network,certificates
from app.modules.connectors import containers
from app.modules.roxywi import logger


class ProxyRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    service: Literal['haproxy','nginx','apache']
    server_id: int=Field(gt=0)


class DiagnosticRequest(ProxyRequest):
    url: str=Field(min_length=1,max_length=2048)
    frontend_id: str|None=Field(default=None,max_length=255)

    @field_validator('url')
    @classmethod
    def validate_url(cls,value):
        if '://' not in value:value='https://'+value
        parsed=urlsplit(value)
        if parsed.scheme not in ('http','https') or parsed.username or parsed.password or parsed.fragment or not parsed.hostname:
            raise ValueError('Use an HTTP(S) domain/URL without credentials or fragments')
        host=inventory.domain(parsed.hostname)
        port=parsed.port
        if port is not None and not 1<=port<=65535:raise ValueError('Invalid port')
        path=parsed.path or '/'
        if any(ord(c)<33 or ord(c)>126 for c in path+parsed.query) or any(ord(c)<32 for c in unquote(path+'?'+parsed.query)):
            raise ValueError('Encode the URL path and remove control characters')
        return urlunsplit((parsed.scheme,host+(':'+str(port) if port else ''),path,parsed.query,''))


def authorize(server_id,service,group_id,user_id,*,probe=False,for_update=False):
    if service not in ('haproxy','nginx','apache'):raise ValueError('Unsupported proxy service')
    query=Server.select().where((Server.server_id==server_id)&(Server.group_id==str(group_id)))
    if for_update:query=query.for_update()
    row=query.get_or_none()
    if row is None:raise RoxywiResourceNotFound('Proxy server not found')
    actor=User.get_or_none(User.user_id==user_id)
    if not actor or not actor.enabled or str(service_sql.select_service_id_by_slug(service)) not in user_sql.select_user_services(user_id).split() or (probe and int(user_sql.get_user_role_in_group(user_id,group_id))>3):
        raise RoxywiPermissionError('Proxy inspection permissions are required')
    if not row.enabled or row.type_ip or not getattr(row,service):raise ValueError('Select an enabled physical server with this proxy service')
    return row


def identity(server,service):
    with group_settings(server.group_id):
        return dict(registration_key=registration_key(server),ip=server.ip,port=server.port,cred_id=server.cred_id,binding=inventory.binding(server,service))


def registration_key(server):
    if not server.registration_key:
        raise RoxywiConflictError('Server registration identity is unavailable; finish the database migration')
    return server.registration_key


def bound_server(row):
    """Check provenance before exposing even an already loaded report row."""
    if not row.server_registration_key:raise RoxywiResourceNotFound('Unbound proxy assessment')
    try:service,server_id=row.subject.split(':');server_id=int(server_id)
    except (ValueError,AttributeError):raise RoxywiResourceNotFound('Proxy assessment not found')
    if service not in ('haproxy','nginx','apache'):raise RoxywiResourceNotFound('Proxy assessment not found')
    server=Server.get_or_none((Server.server_id==server_id)&(Server.group_id==str(row.group_id))&
        (Server.registration_key==row.server_registration_key))
    if server is None:raise RoxywiResourceNotFound('Previous server registration')
    return server


def history(service,server_id,group_id,user_id):
    server=authorize(server_id,service,group_id,user_id)
    # Exhaust this bounded cursor before checking/decrypting any rows. An active
    # SQLite WAL cursor otherwise keeps an older server-registration snapshot.
    return list(OperationalAssessment.select().where((OperationalAssessment.group_id==group_id)&
        (OperationalAssessment.kind=='proxy-diagnostics')&(OperationalAssessment.subject==f'{service}:{server_id}')&
        (OperationalAssessment.server_registration_key==registration_key(server))).order_by(OperationalAssessment.id.desc()).limit(20))


def enqueue(body,group_id,user_id,*,kind='diagnostics'):
    if kind not in ('diagnostics','service-map'):raise ValueError('Unsupported proxy assessment')
    assessment_kind='proxy-diagnostics' if kind=='diagnostics' else 'service-map'
    label='Request path' if kind=='diagnostics' else 'Service discovery'
    database=OperationalAssessment._meta.database;subject=f'{body.service}:{body.server_id}'
    with database.atomic('IMMEDIATE') if isinstance(database,SqliteDatabase) else database.atomic():
        # Authorize and bind the registration while holding the database lock.
        server=authorize(body.server_id,body.service,group_id,user_id,probe=True,for_update=not isinstance(database,SqliteDatabase))
        key=registration_key(server)
        if (OperationalAssessment.select().join(InstallationTasks,on=(OperationalAssessment.task_id==InstallationTasks.id)).where(
            (OperationalAssessment.group_id==group_id)&(OperationalAssessment.kind==assessment_kind)&(OperationalAssessment.subject==subject)&
            (OperationalAssessment.server_registration_key==key)&
            InstallationTasks.status.in_(('created','published','running'))).exists()):
            raise RoxywiConflictError('An assessment of this kind is already queued on this proxy')
        row=OperationalAssessment.create(group_id=group_id,user_id=user_id,kind=assessment_kind,subject=subject,server_registration_key=key)
        task=InstallationTasks.create(service_name=f'{label}: {server.hostname}',group_id=group_id,user_id=user_id,
            server_ids=[server.server_id],operation_id=str(uuid4()),operation_type='proxy-assessment',status='created',updated_at=utc_now(),
            operation_payload=seal(dict(assessment_id=row.id,kind=kind,request=body.model_dump(),identity=identity(server,body.service))))
        row.task_id=task.id;row.save()
    return row


def get(row_id,group_id,user_id):
    row=OperationalAssessment.get_or_none((OperationalAssessment.id==row_id)&(OperationalAssessment.group_id==group_id)&
        OperationalAssessment.kind.in_(('proxy-diagnostics','service-map')))
    if row is None:raise RoxywiResourceNotFound('Proxy assessment not found')
    server=bound_server(row)
    service,_server_id=row.subject.split(':');authorize(server.server_id,service,group_id,user_id)
    return row


def public(row):
    if row.kind in ('proxy-diagnostics','service-map'):bound_server(row)
    task=InstallationTasks.get_or_none(InstallationTasks.id==row.task_id)
    if task and task.group_id_id!=row.group_id:task=None
    if task and task.status in ('completed','failed') and not row.result:
        # The list query may precede worker completion. The worker persists the
        # report before its terminal task state; reload that report so a stale
        # empty row cannot stop browser polling without displaying the result.
        row=OperationalAssessment.get((OperationalAssessment.id==row.id)&
            (OperationalAssessment.group_id==row.group_id)&(OperationalAssessment.task_id==row.task_id))
        if row.kind in ('proxy-diagnostics','service-map'):bound_server(row)
    return dict(id=row.id,created_at=utc_iso(row.created_at),kind=row.kind,subject=row.subject,
        status=task.status if task else 'missing',error=task.error if task else None,
        report=unseal(row.result) if row.result else None)


def rpc(server,operation,data,*,binding=None):
    source=network.source(operation)
    if operation=='probe' and binding:
        script=containers.embedded()+('import json,sys\nd=json.load(sys.stdin)\n'
            'print(module.in_network(d["binding"]["runtime"],d["binding"]["name"],d["source"],d["request"]),end="")\n')
        response=Remote(server).run(['python3','-c',script],data=json.dumps(dict(binding=binding,source=source,request=data)),timeout=45)
    else:response=Remote(server).run(['python3','-c',source],data=json.dumps(data),timeout=30)
    result=json.loads(response)
    if operation=='resolve':
        if not isinstance(result,list) or not 1<=len(result)<=16:raise ValueError('Invalid DNS response')
        return [network.address(value) for value in result]
    if not isinstance(result,dict) or result.get('ip')!=network.address(data['ip']) or result.get('port')!=data['port']:
        raise ValueError('Invalid network probe response')
    return certificate_result(result)


def certificate_result(value):
    value=dict(value);encoded=value.pop('certificate_der',None)
    if encoded:
        if not isinstance(encoded,str) or len(encoded)>131072:raise ValueError('Certificate observation exceeds its size limit')
        der=base64.b64decode(encoded,validate=True)
        metadata=certificates.certificate_metadata(ssl.DER_cert_to_PEM_cert(der))
        if value.get('fingerprint')!=metadata['fingerprint']:raise ValueError('Certificate fingerprint differs from observed bytes')
        value['certificate']=metadata
    return value


INTERFACES=r'''
import json,subprocess
raw=subprocess.run(['ip','-j','address','show'],check=True,capture_output=True,text=True,timeout=10).stdout
if len(raw)>1048576:raise ValueError('Interface data exceeds its size limit')
print(json.dumps(sorted({v['local'] for i in json.loads(raw) for v in i.get('addr_info',[])})))
'''


def interfaces(server):
    values=json.loads(Remote(server).run(['python3','-c',INTERFACES]))
    if not isinstance(values,list) or len(values)>256:raise ValueError('Invalid interface data')
    result=[]
    for value in values:
        try:result.append(network.address(value,loopback=False))
        except ValueError:continue
    try:result.append(network.address(server.ip,loopback=False))
    except ValueError:pass
    return sorted(set(result))


def listener_destinations(front, port, host_addresses):
    """Match this frontend's binds, never every listener on the same machine."""
    local = set()
    for value in host_addresses:
        try:local.add(network.address(value, loopback=False))
        except ValueError:continue
    allowed = set()
    for listener in front['listeners']:
        if listener['port'] != port:continue
        host = listener['host']
        if host in ('*', '0.0.0.0', '::'):
            versions = {4} if host == '0.0.0.0' else {6} if host == '::' else {4, 6}
            if host == '::' and listener.get('address_family') == 'v4v6':versions = {4, 6}
            allowed.update(value for value in local if ipaddress.ip_address(value).version in versions)
        else:
            try:allowed.add(network.address(host, loopback=False))
            except ValueError:continue
    return allowed


def stage(key,state,message,details=None):
    return dict(key=key,state=state,message=message,details=details or {})


def diagnostics(server,body,heartbeat=lambda:None):
    found=inventory.discover(server,body.service);heartbeat()
    parsed=urlsplit(body.url);host=parsed.hostname;port=parsed.port or (443 if parsed.scheme=='https' else 80)
    path=parsed.path+('?'+parsed.query if parsed.query else '')
    stages=[stage('configuration','observed' if found['running_sources_verified'] else 'configured',
        'Routing candidates were parsed; conditional rules are not fully evaluated.',dict(partial=found['partial'],fingerprint=found['fingerprint']))]
    candidates=[front for front in found['frontends'] if any(listener['port']==port for listener in front['listeners'])]
    if body.frontend_id:candidates=[front for front in candidates if front['id']==body.frontend_id]
    else:
        named=[front for front in candidates if host in front['domains']]
        if named:candidates=named
    result=dict(service=body.service,server_id=server.server_id,url=body.url,observed_at=utc_iso(utc_now()),
        origin='controller and registered proxy host',trust_scope='Each probe uses its host system CA store; container filesystem trust is not inferred.',
        stages=stages,frontends=found['frontends'],fingerprint=found['fingerprint'])
    if len(candidates)!=1:
        stages.append(stage('frontend','unknown','Select one discovered frontend for this port; ambiguous routing is not guessed.'))
        result['summary']='A unique frontend could not be established.';return result
    front=candidates[0];result['selected_frontend']=front['id']
    stages.append(stage('frontend','discovered','Selected a configuration-derived frontend.',dict(id=front['id'],name=front['name'])))
    answers=[]
    try:
        answers=network.resolve(host)
        stages.append(stage('dns-controller','observed','Controller DNS answers were resolved once and pinned.',dict(answers=answers)))
    except Exception:stages.append(stage('dns-controller','fail','Controller DNS resolution failed or returned blocked addresses.'))
    try:
        host_answers=rpc(server,'resolve',dict(host=host))
        stages.append(stage('dns-proxy-host','observed' if set(host_answers)==set(answers) else 'warning',
            'DNS from the registered host; custom container DNS/search semantics are not inferred.',dict(answers=host_answers)))
    except Exception:stages.append(stage('dns-proxy-host','unknown','Proxy-host DNS could not be verified.'))
    try:host_addresses=interfaces(server)
    except Exception:host_addresses=[];stages.append(stage('vip-addresses','unknown','Could not read managed-host interface addresses.'))
    allowed=listener_destinations(front,port,host_addresses)
    selected=sorted(set(answers)&allowed)
    vip_probes=[]
    for ip in selected[:8]:
        value=certificate_result(network.probe(dict(ip=ip,port=port,domain=host,path=path,tls=parsed.scheme=='https',http=True,allow_loopback=False)))
        vip_probes.append(value);heartbeat()
    stages.append(stage('vip','observed' if selected else 'unknown',
        'Only DNS destinations matching the selected frontend bindings are probed. Wildcards are limited to host interface addresses; unmatched answers stay separate.',
        dict(probes=vip_probes,unmatched=sorted(set(answers)-allowed))))
    node_probes=[]
    for listener in front['listeners']:
        if listener['port']!=port:continue
        value=listener['host']
        ip='::1' if value=='::' else '127.0.0.1' if value in ('*','0.0.0.0') else value
        try:
            ip=network.address(ip)
            probe=rpc(server,'probe',dict(ip=ip,port=port,domain=host,path=path,tls=parsed.scheme=='https',http=True),binding=found['binding'])
            node_probes.append(probe)
        except Exception:node_probes.append(dict(tcp='unknown',port=port,error='Proxy listener could not be inspected in its runtime context'))
        heartbeat()
    stages.append(stage('proxy-listener','observed' if any(p['tcp']=='connected' for p in node_probes) else 'fail',
        'Listener checks originate in the saved proxy runtime network namespace.',dict(probes=node_probes)))
    listeners=vip_probes+node_probes
    stages.append(stage('tcp','observed' if listeners and all(p.get('tcp')=='connected' for p in listeners) else 'warning',
        'TCP connectivity is independent of TLS trust and application response.',dict(connected=sum(p.get('tcp')=='connected' for p in listeners),attempted=len(listeners))))
    tls_bad=any(p.get('tls') in ('untrusted','handshake-failed') for p in listeners)
    stages.append(stage('tls-sni','not-applicable' if parsed.scheme=='http' else 'fail' if tls_bad else 'observed' if listeners and all(p.get('tls')=='verified' for p in listeners) else 'unknown',
        'TLS validates the requested name and system trust. Rejected certificates are only inspected; no HTTP data is sent over an unverified connection.',
        dict(endpoints=[dict(ip=p.get('ip'),port=p.get('port'),tls=p.get('tls'),certificate=p.get('certificate')) for p in listeners])))
    statuses=[p.get('http') for p in listeners]
    stages.append(stage('http','observed' if any(isinstance(code,int) and code<400 for code in statuses) else 'warning',
        'HEAD responses are recorded without cookies, authentication, response bodies or redirects.',dict(statuses=statuses)))
    backend_probes = []
    resolved_backends = {}
    inspected_backends = {}
    for backend in front['backends'][:16]:
        probes = []
        try:
            if backend['host'] not in resolved_backends:
                resolved_backends[backend['host']] = rpc(server, 'resolve', dict(host=backend['host']))
            addresses = resolved_backends[backend['host']]
            for ip in addresses[:4]:
                target = (ip, backend['port'])
                if target not in inspected_backends:
                    inspected_backends[target] = rpc(
                        server, 'probe', dict(ip=ip, port=backend['port'], http=False, tls=False),
                        binding=found['binding'],
                    )
                probes.append(inspected_backends[target])
                heartbeat()
        except Exception:
            probes = [dict(tcp='unknown', error='Configured backend could not be resolved/probed from the host/runtime context')]
        backend_probes.append(dict(id=backend['id'], host=backend['host'], port=backend['port'], probes=probes))
        heartbeat()
    unresolved_routes=front.get('unresolved_routes',0)
    not_probed=max(0,len(front['backends'])-16)+front['unsupported_backends']+front.get('not_inventoried',0)+unresolved_routes
    backend_state = 'warning'
    backend_message = 'TCP checks of discovered candidate backends; they do not prove application health or conditional route selection.'
    if not backend_probes and not not_probed and not found['partial']:
        backend_state = 'not-applicable'
        backend_message = 'No candidate backend targets were found in the discovered configuration for this frontend.'
    elif not not_probed and backend_probes and all(any(p['tcp'] == 'connected' for p in b['probes']) for b in backend_probes):
        backend_state = 'observed'
    stages.append(stage('backends', backend_state, backend_message,
        dict(targets=backend_probes,not_probed=not_probed,unresolved_routes=unresolved_routes,
             unresolved_route_evidence=front.get('unresolved_route_evidence',[]))))
    refused=any(p.get('tcp')=='refused' for b in backend_probes for p in b['probes'])
    if tls_bad:result['summary']='At least one inspected endpoint failed TLS trust/name validation.'
    elif any(isinstance(p.get('http'),int) for p in node_probes) and refused:result['summary']='The selected proxy listener responds, but at least one discovered backend refuses TCP connections.'
    elif any(isinstance(code,int) and code>=500 for code in statuses):result['summary']='The proxy returned a server error; inspect routing and application health.'
    elif any(isinstance(code,int) and code<500 for code in statuses):result['summary']='An HTTP response was observed. Review DNS, candidate backend and route evidence for its scope.'
    else:result['summary']='The request path could not be verified; inspect the stage results.'
    if inventory.discover(server,body.service)['fingerprint']!=found['fingerprint']:
        result['stale']=True;result['summary']='Configuration changed during diagnostics; run a fresh assessment.'
    return result


def execute(task):
    task=InstallationTasks.get_by_id(task.id)
    if task.status in ('completed','failed'):return task.status
    try:
        payload = unseal(task.operation_payload)
        kind=payload['kind']
        if kind=='diagnostics':
            request_model=DiagnosticRequest
            inspect=diagnostics
        elif kind=='service-map':
            from app.modules.service.service_map import discover
            request_model=ProxyRequest
            inspect=lambda server,body,heartbeat:discover(server,body.service,heartbeat)
        else:raise ValueError('Unsupported proxy assessment')
        body=request_model.model_validate(payload['request'])
        server=authorize(body.server_id,body.service,task.group_id_id,task.user_id_id,probe=True)
        if identity(server,body.service)!=payload['identity']:raise ValueError('Proxy identity/runtime changed after queuing')
        row=get(payload['assessment_id'],task.group_id_id,task.user_id_id)
        expected_kind='proxy-diagnostics' if kind=='diagnostics' else 'service-map'
        if row.task_id!=task.id or row.kind!=expected_kind:raise ValueError('Assessment does not belong to this task')
        with group_settings(task.group_id_id):
            heartbeat=lambda:InstallationTasks.update(updated_at=utc_now()).where(InstallationTasks.id==task.id).execute()
            result=inspect(server,body,heartbeat)
        database=OperationalAssessment._meta.database
        with database.atomic('IMMEDIATE') if isinstance(database,SqliteDatabase) else database.atomic():
            server=authorize(body.server_id,body.service,task.group_id_id,task.user_id_id,probe=True,
                             for_update=not isinstance(database,SqliteDatabase))
            if identity(server,body.service)!=payload['identity']:raise ValueError('Proxy identity changed during inspection')
            OperationalAssessment.update(result=seal(result)).where((OperationalAssessment.id==row.id)&
                (OperationalAssessment.task_id==task.id)&(OperationalAssessment.server_registration_key==registration_key(server))&
                (OperationalAssessment.result=='')).execute()
        state,error='completed',None
    except Exception as exception:
        logger.error('Proxy assessment failed', task_id=task.id, error_type=type(exception).__name__)
        state = 'failed'
        error = 'Proxy assessment could not complete; refresh permissions, configuration discovery and host access'
    InstallationTasks.update(status=state,error=error,finish_date=utc_now(),updated_at=utc_now()).where(
        (InstallationTasks.id==task.id)&InstallationTasks.status.not_in(('completed','failed'))).execute()
    return InstallationTasks.get_by_id(task.id).status
