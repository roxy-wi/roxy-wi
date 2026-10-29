"""Group-scoped external certificate bindings on the durable Operations queue."""
import json
import hashlib
from contextlib import nullcontext
from datetime import timedelta
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.common.time import utc_iso, utc_now
from app.modules.connectors.certificates import provider, validate_settings
from app.modules.db.db_model import CertificateSource, InstallationTasks
from app.modules.db import user as user_sql
from app.modules.operations.queue import serialize_operation_payload, deserialize_operation_payload, renew_operation_lease
from app.modules.roxywi.class_models import LetsEncryptRequest
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiResourceNotFound, RoxywiValidationError
from app.modules.service import certificates, certificate_operations as operations
from app.modules.service.certificate_ownership import check as check_ownership
from app.modules.service.le.le_store import transaction, locked


class SourceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(default='certwarden', pattern=r'^[a-z][a-z0-9_-]{0,31}$')
    settings: dict
    server_id: int = Field(gt=0)
    cluster_id: int | None = Field(default=None, gt=0)
    pem_name: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.pem$')
    domains: list[str] = Field(min_length=1, max_length=100)
    directory: str | None = Field(default=None, min_length=1, max_length=4096)
    destination: dict | None = None
    interval_minutes: int = Field(default=360, ge=5, le=10080)
    enabled: bool = Field(default=False, strict=True)
    revision: int | None = Field(default=None, gt=0)

    @field_validator('domains')
    @classmethod
    def domains_valid(cls, value):
        return LetsEncryptRequest.normalize_domains(value)

    @field_validator('destination')
    @classmethod
    def destination_valid(cls, value):
        if value is not None and (set(value) != {'kind', 'path'} or value['kind'] not in ('directory', 'crt_list')
                                  or not isinstance(value['path'], str) or not 1 <= len(value['path']) <= 4096):
            raise ValueError('Select a loaded certificate directory or crt-list')
        return value


def get(source_id, group_id):
    row = CertificateSource.get_or_none((CertificateSource.id == source_id) & (CertificateSource.group_id == group_id))
    if row is None:
        raise RoxywiResourceNotFound('Certificate source not found')
    return row


def configuration(row):
    return deserialize_operation_payload(row.configuration)


def targets(data, group_id, user_id, *, write=True):
    if data.get('cluster_id'):
        if '5' not in user_sql.select_user_services(user_id).split():
            raise certificates.CertificateError('Cluster permission is required for cluster certificate targets', 'permission_denied')
        rows = certificates.targets_for(data['server_id'], group_id, cluster_id=data['cluster_id'])
    else:
        rows = certificates.targets_for(data['server_id'], group_id)
    for row in rows:
        operations.authorize(row.server_id, group_id, user_id, write=write)
    return rows


def public(row):
    data = configuration(row)
    data['settings'] = {key: value for key, value in data['settings'].items()
                        if key not in provider(row.provider).secret_fields}
    child = InstallationTasks.get_or_none(InstallationTasks.id == row.deployment_task_id) if row.deployment_task_id else None
    parent = InstallationTasks.get_or_none(InstallationTasks.id == row.active_task_id) if row.active_task_id else None
    active = parent is not None and parent.status == 'running'
    recovery = bool(child and deserialize_operation_payload(child.operation_payload).get('phase') in ('apply', 'rollback', 'commit') and
        (child.status in ('failed', 'created', 'published') or (child.status == 'running' and not active)))
    data.update(id=row.id, revision=row.revision, status=row.status, fingerprint=row.fingerprint, recovery_required=recovery,
                active_task_id=row.active_task_id, deployment_task_id=row.deployment_task_id,
                next_check=utc_iso(row.next_check) if row.next_check else None,
                last_check=utc_iso(row.last_check) if row.last_check else None,
                error=row.last_error)
    return data


def editable(row):
    if row.active_task_id:
        job = InstallationTasks.get_or_none(InstallationTasks.id == row.active_task_id)
        if job and job.status not in ('completed', 'failed'):
            raise RoxywiConflictError('Wait for the certificate source operation')
    if row.deployment_task_id:
        job = InstallationTasks.get_or_none(InstallationTasks.id == row.deployment_task_id)
        if job:
            payload = deserialize_operation_payload(job.operation_payload)
            if job.status not in ('completed', 'failed') or payload.get('phase') in ('apply', 'rollback', 'commit'):
                raise RoxywiConflictError('Complete certificate deployment or recovery before changing this source')


def save(body, group_id, user_id, source_id=None):
    data = body.model_dump()
    expected_revision = data.pop('revision')
    with transaction():
        row = locked(CertificateSource, (CertificateSource.id == source_id) &
                     (CertificateSource.group_id == group_id)) if source_id is not None else None
        if row:
            editable(row)
            if expected_revision != row.revision:
                raise RoxywiConflictError('Certificate source changed; reload it before saving')
            previous = configuration(row)
            if previous['provider'] == data['provider']:
                data['settings'] = {**previous['settings'], **data['settings']}
        data['settings'] = validate_settings(data['provider'], data['settings'])
        checked = targets(data, group_id, user_id)
        ids = {s.server_id for s in checked}
        check_ownership(ids, data['pem_name'], group_id, source_id=row.id if row else None)
        fields = dict(group_id=group_id, user_id=user_id, name=data['name'], provider=data['provider'],
                      configuration=serialize_operation_payload(data), enabled=data['enabled'],
                      next_check=utc_now() if data['enabled'] else None, status='draft', last_error=None)
        if row:
            for key, value in fields.items():
                setattr(row, key, value)
            row.revision += 1
            row.fingerprint = ''
            row.save()
        else:
            row = CertificateSource.create(**fields)
        return row


def enqueue(row, user_id, *, check=False, recover=False):
    with transaction():
        row = locked(CertificateSource, CertificateSource.id == row.id)
        if recover:
            if row.active_task_id:
                parent = InstallationTasks.get_or_none(InstallationTasks.id == row.active_task_id)
                if parent and parent.status not in ('completed', 'failed'):
                    raise RoxywiConflictError('Wait for the certificate source operation')
            if not row.deployment_task_id:
                raise RoxywiConflictError('No certificate deployment needs recovery')
        else:
            editable(row)
        data = configuration(row)
        checked = targets(data, row.group_id, user_id, write=not check)
        job = InstallationTasks.create(operation_id=str(uuid4()), operation_type='certificate-source',
            service_name='Certificate source: ' + row.name, user_id=user_id, group_id=row.group_id,
            server_ids=[s.server_id for s in checked], status='created', updated_at=utc_now(),
            operation_payload=serialize_operation_payload(dict(source_id=row.id, revision=row.revision, check=check, recover=recover)))
        changed = CertificateSource.update(active_task_id=job.id, status='queued', last_error=None).where(
            (CertificateSource.id == row.id) & ((CertificateSource.active_task_id.is_null()) |
                                               (CertificateSource.active_task_id == row.active_task_id))).execute()
        if changed != 1:
            raise RoxywiConflictError('Another certificate source operation was queued')
        return job


def recover_deployment(row, task, renew):
    child = operations.owned_task(row.deployment_task_id, row.group_id)
    with operations.operation_lock(child.operation_id):
        child = InstallationTasks.get_by_id(child.id)
        payload = deserialize_operation_payload(child.operation_payload)
        if payload.get('source_id') != row.id:
            raise RoxywiConflictError('The deployment is not owned by this certificate source')
        if set(child.server_ids) != set(task.server_ids):
            raise RoxywiConflictError('Recovery membership changed; inspect the original certificate history')
        # Only source-owned children can be orphaned here. A recorded apply is
        # rolled back after interruption, never silently resumed as a new write.
        payload['source_task_id'] = task.id
        if child.status in ('running', 'created', 'published'):
            if payload['phase'] == 'apply':
                payload['phase'] = 'rollback'
                payload['failure_code'] = 'interrupted'
            operations.save(child, payload, status='failed')
        else:
            operations.save(child, payload)
    child = InstallationTasks.get_by_id(child.id)
    with transaction():
        operations.retry(child, task.user_id_id, source_id=row.id)
        InstallationTasks.update(status='running').where(InstallationTasks.id == child.id).execute()
    result = operations.execute(InstallationTasks.get_by_id(child.id), renew=renew, source_task_id=task.id)
    if result != 'completed':
        raise RoxywiValidationError('Certificate recovery did not commit; inspect per-target history before a fresh synchronization')
    row.fingerprint = payload['metadata']['fingerprint']
    row.deployed_targets = json.dumps(task.server_ids)
    row.status = 'current'


def already_current(row, data, checked, fingerprint, bundle,plans=None):
    if fingerprint != row.fingerprint or json.loads(row.deployed_targets) != [s.server_id for s in checked]:
        return False
    expected_revision=hashlib.sha256((bundle['fullchain']+bundle['key']).encode('ascii')).hexdigest()
    for server in checked:
        if plans and plans[server.server_id]['mode']=='passive':
            _settings,item=certificates.passive_inspection(server,data['pem_name'],plans[server.server_id],directory=data.get('directory'),
                destination=data.get('destination'),expected_digest=expected_revision)
            if item.get('revision')!=expected_revision or item.get('certificate',{}).get('fingerprint')!=fingerprint:return False
            continue
        items = certificates.catalog(server)['certificates']
        matches = [item for item in items if item['name'] == data['pem_name'] and
                   (not data.get('directory') or item.get('directory') == data['directory'])]
        if len(matches) != 1:
            return False
        # HAProxy exposes SHA-1 in Runtime API metadata; the provider's identity
        # is SHA-256. The catalog independently proves disk/runtime agreement.
        item=matches[0]
        if (item.get('disk',{}).get('fingerprint')!=fingerprint or item.get('revision')!=expected_revision or item.get('disk_status')!='matches'
                or item.get('runtime_status') not in ('used','loaded') or not item.get('can_update')):
            return False
    return True


def execute(task):
    with operations.operation_lock(task.operation_id):
        task = InstallationTasks.get_by_id(task.id)
        if task.status in ('completed', 'failed'):
            return task.status
        return execute_source(task)


def owns_child(child, parent_id):
    """Prove the source/parent/child binding before any child phase can run."""
    if parent_id is None:
        return False
    payload = deserialize_operation_payload(child.operation_payload)
    row = CertificateSource.get_or_none((CertificateSource.id == payload.get('source_id')) &
        (CertificateSource.group_id == child.group_id_id) & (CertificateSource.deployment_task_id == child.id) &
        (CertificateSource.active_task_id == parent_id))
    parent = InstallationTasks.get_or_none((InstallationTasks.id == parent_id) &
        (InstallationTasks.operation_type == 'certificate-source') & (InstallationTasks.status == 'running') &
        (InstallationTasks.group_id == child.group_id_id))
    if row is None or parent is None or payload.get('source_task_id', parent_id) != parent_id:
        return False
    owner = deserialize_operation_payload(parent.operation_payload)
    return owner.get('source_id') == row.id and owner.get('revision') == row.revision and owner.get('started') is True


def execute_source(task):
    row = None
    message = None
    try:
        payload = deserialize_operation_payload(task.operation_payload)
        row = get(payload['source_id'], task.group_id_id)
        if row.revision != payload['revision'] or row.active_task_id != task.id or payload.get('started'):
            raise RoxywiConflictError('Source changed or its operation was interrupted; inspect state before retrying')
        payload['started'] = True
        InstallationTasks.update(operation_payload=serialize_operation_payload(payload), status='running', updated_at=utc_now()).where(
            InstallationTasks.id == task.id).execute()
        data = configuration(row)
        from app.modules.pacemaker import service as cluster_service
        cluster = cluster_service.get_cluster(data['cluster_id'], row.group_id) if data.get('cluster_id') else None
        with cluster_service.locked(cluster) if cluster else nullcontext() as lease:
            def renew():
                if not CertificateSource.select().where((CertificateSource.id == row.id) &
                        (CertificateSource.active_task_id == task.id) & (CertificateSource.revision == row.revision)).exists():
                    raise RoxywiConflictError('Certificate source ownership changed')
                if renew_operation_lease(task.operation_id, task.id) != 1:
                    raise RoxywiConflictError('Certificate source worker lease was lost')
                if cluster:
                    cluster_service.renew_lock(cluster, lease)
            checked = targets(data, row.group_id, task.user_id_id, write=not payload['check'])
            if [s.server_id for s in checked] != task.server_ids:
                raise RoxywiConflictError('Certificate targets changed after queuing')
            plans={}
            if cluster and not payload['check'] and not payload.get('recover'):
                from app.modules.service.certificate_cluster import plan
                plans=plan(cluster,{s.server_id:certificates.deployment_settings(s,data['pem_name'],verify_startup=False) for s in checked})
            primary=next((server for server in checked if not plans or plans[server.server_id]['mode']=='active'),checked[0])
            if payload.get('recover'):
                recover_deployment(row, task, renew)
            else:
                pem = provider(data['provider']).fetch(data['settings'])
                bundle, metadata = certificates.inspect_pem(pem)
                certificates.inspect_bundle(bundle, data['domains'])
                if payload['check']:
                    row.status = 'checked'
                elif already_current(row, data, checked, metadata['fingerprint'],bundle,plans):
                    row.status = 'current'
                else:
                    catalog = certificates.catalog(primary)
                    matches = [item for item in catalog['certificates'] if item['name'] == data['pem_name']
                               and (not data.get('directory') or item.get('directory') == data['directory'])]
                    if len(matches) > 1:
                        raise RoxywiValidationError('Select the directory containing the certificate to update')
                    current = matches[0] if matches else None
                    if current and not current.get('can_update'):
                        raise RoxywiValidationError('The selected certificate cannot be updated through Runtime API')
                    destination = None if current else data.get('destination')
                    if not current and destination not in catalog.get('destinations', []):
                        raise RoxywiValidationError('Select a currently loaded certificate directory or crt-list for first deployment')
                    with transaction():
                        check_ownership(task.server_ids, data['pem_name'], row.group_id, source_id=row.id)
                        child = operations.enqueue(primary.server_id, row.group_id, task.user_id_id, data['pem_name'], pem,
                            current['revision'] if current else '0' * 64, str(uuid4()), destination=destination,
                            directory=current.get('directory') if current else None, cluster_id=data.get('cluster_id'),
                            source_id=row.id, source_task_id=task.id)
                        recorded = InstallationTasks.get_by_id(child['id'])
                        child_payload = deserialize_operation_payload(recorded.operation_payload)
                        child_payload['source_id'] = row.id
                        if plans:child_payload['cluster_cib']=next(iter(plans.values()))['cib']
                        # The parent executes its child while holding the cluster
                        # lease; the queue publisher must not dispatch it again.
                        operations.save(recorded, child_payload, status='running')
                        row.deployment_task_id = child['id']
                        row.save()
                    result = operations.execute(InstallationTasks.get_by_id(child['id']), renew=renew, source_task_id=task.id)
                    if result != 'completed':
                        raise RoxywiValidationError('Certificate deployment failed; inspect its per-target history and recovery')
                    row.fingerprint = metadata['fingerprint']
                    row.deployed_targets = json.dumps(task.server_ids)
                    row.status = 'current'
        state = 'completed'
    except Exception:
        message = 'Certificate source operation failed; inspect provider settings and certificate deployment history'
        state = 'failed'
    if row is not None:
        # A late delivery of an old task cannot erase a newer operation or edit.
        fields = dict(status=row.status if state == 'completed' else 'failed', last_error=message,
                      active_task_id=None, fingerprint=row.fingerprint, deployed_targets=row.deployed_targets,
                      last_check=utc_now(), next_check=utc_now() + timedelta(minutes=configuration(row)['interval_minutes']) if row.enabled else None)
        CertificateSource.update(**fields).where((CertificateSource.id == row.id) &
            (CertificateSource.active_task_id == task.id) & (CertificateSource.revision == row.revision)).execute()
    InstallationTasks.update(status=state, error=message, finish_date=utc_now(), updated_at=utc_now()).where(
        InstallationTasks.id == task.id).execute()
    return state


def dispatch_due(limit=25):
    now = utc_now()
    count = 0
    # Materialize before enqueue can roll back and invalidate SQLite cursors.
    due=list(CertificateSource.select().where(CertificateSource.enabled & (CertificateSource.next_check <= now)).limit(limit))
    for row in due:
        try:
            enqueue(row, row.user_id)
            count += 1
        except Exception:
            CertificateSource.update(next_check=now + timedelta(minutes=15)).where(CertificateSource.id == row.id).execute()
    return count
