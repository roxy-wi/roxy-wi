"""Compare certificates actually served for a domain across discovered proxies."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import hashlib
import json
from pydantic import BaseModel, ConfigDict, Field, field_validator
from cryptography import x509
from app.modules.common.execution_context import group_settings
from app.modules.common.time import utc_now, utc_iso
from app.modules.db.db_model import ServedTlsMonitor, OperationalAssessment, InstallationTasks, CertificateSource
from app.modules.operations.queue import serialize_operation_payload as seal, deserialize_operation_payload as unseal
from app.modules.roxywi.exception import RoxywiResourceNotFound, RoxywiConflictError
from app.modules.service import proxy_assessments as assessments, service_map, network_probe as network, published_endpoints as inventory
from app.modules.service.le.le_store import transaction, locked


class Target(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    assessment_id: int = Field(gt=0)
    frontend_id: str = Field(min_length=1, max_length=255)


class MonitorRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=128)
    domain: str = Field(min_length=1, max_length=253)
    port: int = Field(default=443, ge=1, le=65535)
    targets: list[Target] = Field(min_length=1, max_length=32)
    source_id: int | None = Field(default=None, gt=0)
    ca_pem: str = Field(default='', max_length=131072)
    warning_days: int = Field(default=30, ge=1, le=365)
    interval_minutes: int = Field(default=60, ge=5, le=10080)
    enabled: bool = Field(default=False, strict=True)
    revision: int | None = Field(default=None, gt=0)

    @field_validator('domain')
    @classmethod
    def valid_domain(cls, value): return inventory.domain(value)

    @field_validator('ca_pem')
    @classmethod
    def public_ca(cls, value):
        if value:
            if 'PRIVATE KEY' in value or not x509.load_pem_x509_certificates(value.encode()):
                raise ValueError('Use a public PEM CA bundle without private keys')
        return value


def get(ident, group_id):
    row = ServedTlsMonitor.get_or_none((ServedTlsMonitor.id == ident) & (ServedTlsMonitor.group_id == group_id))
    if row is None: raise RoxywiResourceNotFound('TLS monitor not found')
    return row


def expected(source_id, group_id):
    if not source_id: return None
    row = CertificateSource.get_or_none((CertificateSource.id == source_id) & (CertificateSource.group_id == group_id))
    if row is None: raise RoxywiResourceNotFound('Certificate source not found')
    return dict(id=row.id, name=row.name, fingerprint=row.fingerprint, status=row.status, revision=row.revision,
        deployment_task_id=row.deployment_task_id,operation_active=bool(row.active_task_id))


def expected_token(source):
    if source is None:return ''
    # A chain-only replacement keeps its leaf fingerprint but creates a new
    # completed deployment. Do not miss that verification trigger.
    identity={key:source.get(key) for key in ('id','fingerprint','revision','deployment_task_id','operation_active')}
    return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()


def checked_targets(data, group_id, user_id, *, write=False, latest=False):
    result = []; seen = set()
    latest_ids = {row.id for row in service_map.latest(group_id)} if latest else None
    for target in data['targets']:
        snapshot = assessments.get(target['assessment_id'], group_id, user_id)
        if snapshot.kind != 'service-map' or not snapshot.result or (latest_ids is not None and snapshot.id not in latest_ids):
            raise RoxywiConflictError('Select targets from the latest completed service discovery')
        service, ident = snapshot.subject.split(':')
        server = assessments.authorize(int(ident), service, group_id, user_id, probe=write)
        report = unseal(snapshot.result); found = report['inventory']
        front = next((value for value in found['frontends'] if value['id'] == target['frontend_id']), None)
        if not front or not front['tls'] or not any(value['port'] == data['port'] for value in front['listeners']):
            raise ValueError('Select discovered TLS frontends for this port')
        confirmations = service_map.PublishedServiceConfirmation.select().where(
            (service_map.PublishedServiceConfirmation.group_id == group_id) &
            (service_map.PublishedServiceConfirmation.assessment_id == snapshot.id) &
            (service_map.PublishedServiceConfirmation.frontend_id == front['id']) &
            (service_map.PublishedServiceConfirmation.domain == data['domain']))
        if data['domain'] not in front['domains'] and not confirmations.exists():
            raise ValueError('Discover or confirm this domain on each selected frontend')
        if write and report['identity'] != assessments.identity(server, service):
            raise RoxywiConflictError('Proxy identity/runtime changed; rediscover and review the monitor')
        key = (server.server_id, service, front['id'])
        if key in seen: raise ValueError('Select each proxy frontend once')
        seen.add(key); result.append((server, service, front, found))
    return result


def authorize(row, user_id, *, write=False):
    data = unseal(row.configuration)
    return data, checked_targets(data, row.group_id, user_id, write=write)


def active(row):
    if not row.active_task_id:return False
    task=InstallationTasks.get_or_none((InstallationTasks.id==row.active_task_id)&(InstallationTasks.group_id==row.group_id))
    if task is None:raise RoxywiConflictError('TLS task identity could not be verified')
    return task.status not in ('completed','failed')


def public(row, user_id):
    # Read task state before the report snapshot. If the worker finishes during
    # serialization, retain polling; if it has already finished, reload the row
    # whose assessment pointer the worker updated before completing the task.
    is_active = active(row)
    if row.active_task_id and not is_active:
        row = get(row.id, row.group_id)
        is_active = active(row)
    data, _targets = authorize(row, user_id)
    report = OperationalAssessment.get_or_none((OperationalAssessment.id == row.last_assessment_id) &
        (OperationalAssessment.group_id == row.group_id) & (OperationalAssessment.kind == 'served-tls') &
        (OperationalAssessment.subject == str(row.id)))
    observed=unseal(report.result) if report and report.result else None
    try: source_current=expected_token(expected(data['source_id'],row.group_id))==expected_token((observed or {}).get('source'))
    except RoxywiResourceNotFound: source_current=False
    task_id=row.active_task_id or (report.task_id if report else None)
    task=InstallationTasks.get_or_none((InstallationTasks.id==task_id)&(InstallationTasks.group_id==row.group_id)) if task_id else None
    data.update(id=row.id, revision=row.revision, next_check=utc_iso(row.next_check), last_check=utc_iso(row.last_check),
        active_task_id=row.active_task_id if is_active else None, last_assessment_id=row.last_assessment_id,
        expectation_current=bool(observed and source_current),error=task.error if task else None,report=observed)
    return data


def save(body, group_id, user_id, ident=None):
    data = body.model_dump(); revision = data.pop('revision')
    checked_targets(data, group_id, user_id, write=True, latest=True); expected(data['source_id'], group_id)
    if ident:get(ident,group_id)
    with transaction():
        row = locked(ServedTlsMonitor, (ServedTlsMonitor.id == ident) & (ServedTlsMonitor.group_id == group_id)) if ident else None
        if ident and not row: raise RoxywiResourceNotFound()
        if row:
            if active(row): raise RoxywiConflictError('Wait for the active TLS assessment')
            if revision != row.revision: raise RoxywiConflictError('Monitor changed; reload before saving')
            row.revision += 1
        else:
            if ServedTlsMonitor.select().where(ServedTlsMonitor.group_id==group_id).count()>=256:
                raise ValueError('A group supports at most 256 TLS monitors')
            row = ServedTlsMonitor(group_id=group_id, revision=1)
        row.user_id=user_id; row.name=data['name']; row.configuration=seal(data); row.enabled=data['enabled']; row.last_assessment_id=None; row.active_task_id=None
        row.next_check=utc_now() if row.enabled else None; row.last_expected_fingerprint=''; row.save()
    return row


def enqueue(row, user_id):
    with transaction():
        row = locked(ServedTlsMonitor, (ServedTlsMonitor.id == row.id) & (ServedTlsMonitor.group_id == row.group_id))
        data, targets = authorize(row, user_id, write=True)
        source = expected(data['source_id'], row.group_id)
        if active(row): raise RoxywiConflictError('A TLS assessment is already queued')
        report = OperationalAssessment.create(group_id=row.group_id, user_id=user_id, kind='served-tls', subject=str(row.id))
        identities = [assessments.identity(server, service) for server, service, _front, _found in targets]
        task = InstallationTasks.create(service_name='Served TLS: '+row.name, group_id=row.group_id, user_id=user_id,
            server_ids=sorted({s.server_id for s, *_ in targets}), operation_type='served-tls', operation_id=str(uuid4()),
            status='created', updated_at=utc_now(), operation_payload=seal(dict(monitor_id=row.id, revision=row.revision,
                assessment_id=report.id, identities=identities, source=source)))
        report.task_id=task.id; report.save(); row.active_task_id=task.id; row.save()
    return report


def inspect(data, targets, source, heartbeat=lambda: None):
    endpoints = []; allowed = set(); stale = False
    request = dict(port=data['port'], domain=data['domain'], tls=True, http=False, ca_pem=data['ca_pem'])
    for server, service, original, snapshot in targets:
        with group_settings(server.group_id): found = inventory.discover(server, service)
        if found['fingerprint'] != snapshot['fingerprint']:
            stale = True; endpoints.append(dict(server_id=server.server_id, server=server.hostname, origin='proxy', state='configuration-changed')); continue
        front = next((f for f in found['frontends'] if f['id'] == original['id']), None)
        if front is None: raise ValueError('TLS frontend disappeared')
        try: allowed.update(assessments.interfaces(server))
        except Exception: pass
        listeners = [listener for listener in front['listeners'] if listener['port'] == data['port']]
        for listener in listeners[:4]:
            value = listener['host']; ip = '::1' if value == '::' else '127.0.0.1' if value in ('*','0.0.0.0') else value
            try:
                try: allowed.add(network.address(value, loopback=False))
                except ValueError: pass
                observed = assessments.rpc(server,'probe',dict(request,ip=network.address(ip)),binding=found['binding'])
            except Exception: observed = dict(tcp='unknown',tls='unknown')
            endpoints.append(dict(server_id=server.server_id,server=server.hostname,service=service,origin='proxy runtime namespace',**observed))
            heartbeat()
        if len(listeners) > 4: endpoints.append(dict(server_id=server.server_id,server=server.hostname,origin='proxy',state='listener-limit'))
        if inventory.discover(server, service)['fingerprint'] != found['fingerprint']: stale = True
    dns = []; unmatched = []
    try:
        dns = network.resolve(data['domain']); unmatched = sorted(set(dns)-allowed)
        for ip in sorted(set(dns)&allowed)[:8]:
            observed = assessments.certificate_result(network.probe(dict(request,ip=ip,allow_loopback=False)))
            endpoints.append(dict(origin='controller to discovered VIP/node',**observed)); heartbeat()
    except Exception: endpoints.append(dict(origin='controller',state='dns-or-probe-failed'))
    fingerprints = {item.get('fingerprint') for item in endpoints if item.get('fingerprint')}
    consistent = len(fingerprints) == 1
    expected_ready = source is None or bool(source['fingerprint'] and source['status'] in ('current','checked') and not source.get('operation_active'))
    expected_match = None if source is None or not expected_ready else fingerprints == {source['fingerprint']}
    now = datetime.now(timezone.utc)
    for item in endpoints:
        cert = item.get('certificate')
        if cert: item['days_remaining'] = (datetime.fromisoformat(cert['not_after'])-now).total_seconds()/86400
        item['expiring'] = bool(cert and item['days_remaining'] < data['warning_days'])
    all_verified = bool(endpoints) and all(item.get('tls')=='verified' for item in endpoints)
    state = 'stale' if stale else 'mismatch' if len(fingerprints)>1 or expected_match is False else 'verified' if all_verified and consistent and expected_ready and not unmatched else 'partial'
    if state=='verified' and any(item['expiring'] for item in endpoints): state='expiring'
    return dict(domain=data['domain'],port=data['port'],observed_at=utc_iso(utc_now()),state=state,endpoints=endpoints,
        peer_consistent=consistent,expected_match=expected_match,source=source,dns=dns,unmatched_dns=unmatched,
        summary={'verified':'Every selected listener verified trust/name and presented the same leaf certificate; the selected source, if any, also matches.',
            'mismatch':'Served certificates differ between endpoints or from the selected certificate source.',
            'partial':'Some endpoints, DNS targets or expected source state could not be verified.',
            'stale':'Configuration changed; rediscover targets and review the monitor.',
            'expiring':'Certificates agree and validate, but their remaining validity is below the warning threshold.'}[state],
        trust_scope='System CA store of each probe host plus the optional public CA bundle. No HTTP requests, private keys or credentials are sent.')


def execute(task):
    task=InstallationTasks.get_by_id(task.id)
    if task.status in ('completed','failed'): return task.status
    payload=unseal(task.operation_payload); row=None; report=None; fingerprint=''
    try:
        row=get(payload['monitor_id'],task.group_id_id)
        if row.active_task_id!=task.id or row.revision!=payload['revision']: raise ValueError('Monitor changed')
        data,targets=authorize(row,task.user_id_id,write=True)
        if [assessments.identity(s,service) for s,service,*_ in targets]!=payload['identities']: raise ValueError('Proxy identity changed')
        report=OperationalAssessment.get((OperationalAssessment.id==payload['assessment_id']) &
            (OperationalAssessment.task_id==task.id) & (OperationalAssessment.group_id==row.group_id) &
            (OperationalAssessment.kind=='served-tls') & (OperationalAssessment.subject==str(row.id)))
        source=expected(data['source_id'],row.group_id)
        if source!=payload['source']: raise ValueError('Expected source changed after queuing')
        fingerprint=expected_token(source)
        result=inspect(data,targets,source,lambda:InstallationTasks.update(updated_at=utc_now()).where(InstallationTasks.id==task.id).execute())
        result['monitor_revision']=row.revision
        _data,current=authorize(row,task.user_id_id,write=True)
        if [assessments.identity(s,service) for s,service,*_ in current]!=payload['identities'] or expected(data['source_id'],row.group_id)!=source:
            raise ValueError('Proxy identity or certificate source changed during TLS assessment')
        OperationalAssessment.update(result=seal(result)).where((OperationalAssessment.id==report.id)&(OperationalAssessment.result=='')).execute()
        state,error='completed',None
    except Exception: state,error='failed','TLS assessment failed; review discovery, permission, source state and host access'
    if row:
        ServedTlsMonitor.update(active_task_id=None,last_assessment_id=report.id if report else row.last_assessment_id,
            last_check=utc_now(),last_expected_fingerprint=fingerprint,
            next_check=utc_now()+timedelta(minutes=unseal(row.configuration)['interval_minutes']) if row.enabled else None).where(
                (ServedTlsMonitor.id==row.id)&(ServedTlsMonitor.active_task_id==task.id)&(ServedTlsMonitor.revision==payload['revision'])).execute()
    InstallationTasks.update(status=state,error=error,finish_date=utc_now(),updated_at=utc_now()).where(
        (InstallationTasks.id==task.id)&InstallationTasks.status.not_in(('completed','failed'))).execute()
    return InstallationTasks.get_by_id(task.id).status


def dispatch_due(limit=25):
    now=utc_now(); count=0
    # Source-change checks also run before the normal interval, after a completed
    # provider deployment. They never turn provider delivery into TLS success.
    for row in ServedTlsMonitor.select().where(ServedTlsMonitor.enabled).order_by(ServedTlsMonitor.next_check).limit(1000):
        if count>=limit: break
        source=None
        try:
            if active(row):continue
            data=unseal(row.configuration); source=expected(data['source_id'],row.group_id)
            changed=bool(source and source['status']=='current' and not source.get('operation_active') and expected_token(source)!=row.last_expected_fingerprint)
            if (row.next_check and row.next_check<=now) or changed:
                enqueue(row,row.user_id); count+=1
        except Exception:
            ServedTlsMonitor.update(next_check=now+timedelta(minutes=15),
                last_expected_fingerprint=expected_token(source) if source else row.last_expected_fingerprint).where(ServedTlsMonitor.id==row.id).execute()
    return count
