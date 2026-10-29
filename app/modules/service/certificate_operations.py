"""Manual certificate updates on the existing durable Operations queue."""
import hashlib
from pathlib import Path
from uuid import UUID

from peewee import Select, SQL, SqliteDatabase, fn

from app.modules.common.file_lock import file_lock
from app.modules.common.time import utc_iso, utc_now
from app.modules.config import deployment_policy
from app.modules.db import user as user_sql, service as service_sql, server as server_sql
from app.modules.db.db_model import InstallationTasks, Server
from app.modules.operations.queue import serialize_operation_payload, deserialize_operation_payload
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi.exception import RoxywiResourceNotFound
from app.modules.service import certificates, certificate_deployment


def operation_lock(operation_id):
    root = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'certificates'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return file_lock(root / (str(UUID(operation_id)) + '.lock'))


def authorize(server_id, group_id, user_id, write=False, *, service='haproxy'):
    server = Server.get_or_none((Server.server_id == server_id) & (Server.group_id == str(group_id)))
    if server is None:
        raise RoxywiResourceNotFound('Server not found')
    role = int(user_sql.get_user_role_in_group(user_id, group_id) or 4)
    if str(service_sql.select_service_id_by_slug(service)) not in user_sql.select_user_services(user_id) or (write and role > 3):
        raise certificates.CertificateError('Certificate permission denied', 'permission_denied')
    if write:
        if server_sql.is_serv_protected(server.ip) and role > 2:
            raise certificates.CertificateError('Server is protected', 'permission_denied')
        if not deployment_policy.direct_deployment_allowed(group_id, service):
            raise certificates.CertificateError('Direct deployment is disabled', 'direct_disabled')
    return server


def owned_task(task_id, group_id):
    task = InstallationTasks.get_or_none((InstallationTasks.id == task_id) &
        (InstallationTasks.group_id == group_id) & (InstallationTasks.operation_type == 'certificate'))
    if task is None:
        raise RoxywiResourceNotFound('Certificate operation not found')
    return task


def public_task(task):
    payload = deserialize_operation_payload(task.operation_payload)
    # InstallationTasks.start_date defaults to datetime.now (server-local time),
    # while the Operations worker writes finish_date using utc_now.
    started_at = task.start_date.astimezone() if task.start_date else None
    return {'id': task.id, 'status': task.status, 'error_code': payload.get('error_code'),
            'name': payload['name'], 'action': 'upload_apply' if payload.get('destination') else 'update',
            'started_at': utc_iso(started_at),
            'finished_at': utc_iso(task.finish_date) if task.status in ('completed', 'failed') else None,
            'targets': [{'server_id': int(key), 'address': value['address'], 'status': value['status'],
                         'verification':value.get('verification'),
                         'error_code': value.get('error_code')}
                        for key, value in payload['targets'].items()],
            'retryable': task.status == 'failed' and payload['phase'] in ('rollback', 'commit')}


def server_tasks(server_id, group_id):
    """Filter targets in SQL before counting/paging, on both supported databases."""
    if isinstance(InstallationTasks._meta.database, SqliteDatabase):
        targets = fn.json_each(InstallationTasks.server_ids).alias('certificate_server')
        matches = fn.EXISTS(Select(columns=[SQL('1')]).from_(targets).where(targets.c.value == server_id))
    else:
        matches = fn.JSON_CONTAINS(InstallationTasks.server_ids, str(server_id))
    return InstallationTasks.select().where(
        (InstallationTasks.group_id == group_id) &
        (InstallationTasks.operation_type == 'certificate') & matches).order_by(InstallationTasks.id.desc())


def history(server_id, group_id, page=1, per_page=10):
    tasks = server_tasks(server_id, group_id)
    total = tasks.count()
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    return {'operations': [public_task(task) for task in tasks.paginate(page, per_page)],
            'page': page, 'per_page': per_page, 'pages': pages, 'total': total}


def enqueue(server_id, group_id, user_id, name, pem, revision, operation_id, *, destination=None, directory=None, cluster_id=None,
            source_id=None, source_task_id=None):
    operation_id = str(UUID(str(operation_id)))
    if not name.endswith('.pem') or any(char in name for char in '/\\\r\n\x00;') or name in ('.', '..'):
        raise certificates.CertificateError('Invalid certificate name', 'invalid_path')
    bundle, metadata = certificates.inspect_pem(pem)
    normalized = bundle['fullchain'] + bundle['key']
    digest = hashlib.sha256(normalized.encode('ascii')).hexdigest()
    targets = (certificates.targets_for(server_id, group_id, cluster_id=cluster_id) if cluster_id is not None
               else certificates.targets_for(server_id, group_id))
    for server in targets:
        authorize(server.server_id, group_id, user_id, write=True)
    with operation_lock(operation_id):
        existing = InstallationTasks.get_or_none(InstallationTasks.operation_id == operation_id)
        if existing:
            if existing.operation_type != 'certificate' or str(existing.group_id_id) != str(group_id):
                raise certificates.CertificateError('Operation conflict', 'concurrent_change')
            payload = deserialize_operation_payload(existing.operation_payload)
            if ((payload['digest'], payload['name'], payload['server_id'], payload['revision']) != (digest, name, server_id, revision)
                    or payload.get('destination') != destination or payload.get('directory') != directory
                    or payload.get('cluster_id') != cluster_id
                    or (payload.get('source_id'), payload.get('source_task_id')) != (source_id, source_task_id)):
                raise certificates.CertificateError('Operation conflict', 'concurrent_change')
            return public_task(existing)
        payload = dict(server_id=server_id, name=name, bundle=bundle, digest=digest, revision=revision,
                       phase='apply', targets={}, metadata=metadata, destination=destination, directory=directory)
        if source_id is not None:
            if source_task_id is None:
                raise certificates.CertificateError('A source deployment requires its parent operation', 'concurrent_change')
            payload.update(source_id=source_id, source_task_id=source_task_id)
        if cluster_id is not None:
            payload['cluster_id'] = cluster_id
        for server in targets:
            settings = certificates.deployment_settings(server, name, verify_startup=False)
            settings['apply_mode'] = 'runtime'
            if destination:
                settings['destination'] = destination
            if directory:
                settings['update_directory'] = directory
            if server.server_id == server_id:
                settings['expected_revision'] = revision
            payload['targets'][str(server.server_id)] = dict(address=server.ip, status='pending', settings=settings,
                identity=dict(ip=server.ip,port=server.port,cred_id=server.cred_id))
        task = InstallationTasks.create(service_name='HAProxy certificates', operation_type='certificate',
            operation_id=operation_id, operation_payload=serialize_operation_payload(payload),
            server_ids=[server.server_id for server in targets], group_id=group_id, user_id=user_id,
            status='created', updated_at=utc_now())
        return public_task(task)


def save(task, payload, **updates):
    InstallationTasks.update(operation_payload=serialize_operation_payload(payload), updated_at=utc_now(),
                             **updates).where(InstallationTasks.id == task.id).execute()


def retry(task, user_id, *, source_id=None):
    with operation_lock(task.operation_id):
        task = InstallationTasks.get_by_id(task.id)
        payload = deserialize_operation_payload(task.operation_payload)
        if payload.get('source_id') is not None and payload['source_id'] != source_id:
            raise certificates.CertificateError('Recover this deployment through its certificate source', 'concurrent_change')
        for key in payload['targets']:
            authorize(int(key), task.group_id_id, user_id, write=True)
        if task.status != 'failed' or payload['phase'] not in ('commit', 'rollback'):
            raise certificates.CertificateError('Refresh and submit a new update', 'concurrent_change')
        save(task, payload, status='created', error=None, published_at=None, user_id=user_id)
        return public_task(InstallationTasks.get_by_id(task.id))


def finish(task, payload, *, renew=None):
    phase = payload['phase']
    failures = []
    if not any(target.get('started') and target.get('finished')!=phase for target in payload['targets'].values()):return
    plans={}
    if payload.get('cluster_id'):
        from app.modules.service.certificate_cluster import plan
        from app.modules.pacemaker import service as clusters
        plans=plan(clusters.get_cluster(payload['cluster_id'],task.group_id_id),
            {int(key):dict(value['settings']) for key,value in payload['targets'].items()})
        if payload.get('cluster_cib') and any(proof['cib']!=payload['cluster_cib'] for proof in plans.values()):
            raise certificates.CertificateError('Cluster changed before certificate recovery','concurrent_change')
    prepared={}
    def resolve(key,target):
        server=Server.get_or_none((Server.server_id==int(key)) & (Server.group_id==str(task.group_id_id)))
        if server is None or server.ip!=target['address'] or (target.get('identity') and target['identity']!=dict(ip=server.ip,port=server.port,cred_id=server.cred_id)):
            raise certificates.CertificateError('Recovery target changed','recovery_failed')
        settings=dict(target['settings'])
        if plans:
            current=certificates.cluster_deployment_settings(server,payload['name'],plans[int(key)])
            if any(current.get(field)!=settings.get(field) for field in ('cert_dir','config_path','docker','container','container_runtime','root','service_unit')):
                raise certificates.CertificateError('Recovery runtime binding changed','recovery_failed')
            settings.update(validation=current['validation'],cluster_proof=plans[int(key)])
        prepared[server.server_id]=settings
        return server
    def finalize(server,data):
        return certificates.remote(server,dict(prepared[server.server_id],operation=phase,transaction=task.operation_id,
            expected_digest=payload['digest'],expected_certificate=payload.get('bundle',{}).get('fullchain','')))
    certificate_deployment.finish(payload['targets'],phase,task.operation_id,resolve=resolve,remote=finalize,
        persist=lambda:save(task,payload),renew=renew)


def execute(task, *, renew=None, source_task_id=None):
    with operation_lock(task.operation_id):
        task = InstallationTasks.get_by_id(task.id)
        if task.status in ('completed', 'failed'):
            return task.status
        payload = deserialize_operation_payload(task.operation_payload)
        if payload.get('source_id') is not None:
            from app.modules.service.certificate_sources import owns_child
            if renew is None or not owns_child(task, source_task_id):
                # Even a delayed direct dispatch cannot advance an owned child.
                # Recovery must reacquire the source's cluster lease first.
                return 'owned'
        try:
            if payload['phase'] == 'apply':
                current_targets = (certificates.targets_for(payload['server_id'], task.group_id_id, cluster_id=payload['cluster_id'])
                                   if payload.get('cluster_id') is not None else
                                   certificates.targets_for(payload['server_id'], task.group_id_id))
                if {str(server.server_id) for server in current_targets} != set(payload['targets']):
                    raise certificates.CertificateError('Targets changed', 'concurrent_change')
                # Discover startup sources in the worker, without tying up the HTTP
                # request, and refresh them before a recovered operation resumes.
                plans={}
                if payload.get('cluster_id'):
                    from app.modules.service.certificate_cluster import plan
                    from app.modules.pacemaker import service as clusters
                    plans=plan(clusters.get_cluster(payload['cluster_id'],task.group_id_id),
                        {int(key):dict(target['settings']) for key,target in payload['targets'].items()})
                    fingerprint=next(iter(plans.values()))['cib']
                    if payload.get('cluster_cib') and payload['cluster_cib']!=fingerprint:
                        raise certificates.CertificateError('Cluster configuration changed','concurrent_change')
                    payload['cluster_cib']=fingerprint
                for key, target in payload['targets'].items():
                    if renew:
                        renew()
                    server = authorize(int(key), task.group_id_id, task.user_id_id, write=True)
                    if server.ip != target['address'] or (target.get('identity') and target['identity']!=dict(ip=server.ip,port=server.port,cred_id=server.cred_id)):
                        raise certificates.CertificateError('Target changed', 'concurrent_change')
                    settings = (certificates.cluster_deployment_settings(server,payload['name'],plans[int(key)]) if plans else
                                certificates.deployment_settings(server,payload['name']))
                    identity = ('cert_dir', 'config_path', 'docker', 'container', 'runtime_port', 'container_runtime','root','service_unit')
                    if any(settings.get(field) != target['settings'].get(field) for field in identity):
                        raise certificates.CertificateError('Service settings changed', 'concurrent_change')
                    settings['apply_mode'] = 'runtime'
                    if payload.get('destination'):
                        settings['destination'] = payload['destination']
                    if payload.get('directory'):
                        settings['update_directory'] = payload['directory']
                    if server.server_id == payload['server_id']:
                        settings['expected_revision'] = payload['revision']
                    if plans:
                        proof=plans[int(key)];settings['cluster_proof']=proof
                        if proof['mode']=='passive':
                            settings,observed=certificates.passive_inspection(server,payload['name'],proof,directory=payload.get('directory'),destination=payload.get('destination'))
                            settings.update(passive_binding=observed['binding'],expected_revision=observed['revision'])
                    target['settings'] = settings
                save(task, payload)
                if payload.get('destination'):
                    # Fail before touching the Master if a Slave cannot accept this destination/name.
                    for key, target in payload['targets'].items():
                        if target['settings'].get('cluster_proof',{}).get('mode')=='passive':continue
                        try:
                            if renew:
                                renew()
                            certificates.remote(Server.get_by_id(int(key)), dict(target['settings'],
                                operation='check-new', transaction=task.operation_id))
                        except Exception as error:
                            target['error_code'] = getattr(error, 'code', 'operation_failed')
                            raise
                def resolve(key,target):
                    server=authorize(int(key),task.group_id_id,task.user_id_id,write=True)
                    if server.ip!=target['address'] or (target.get('identity') and target['identity']!=dict(ip=server.ip,port=server.port,cred_id=server.cred_id)):
                        raise certificates.CertificateError('Target changed','concurrent_change')
                    return server
                certificate_deployment.apply(payload['targets'],payload['bundle'],payload['name'],task.operation_id,
                    resolve=resolve,deploy=certificates.deploy,persist=lambda:save(task,payload),renew=renew)
                if plans:
                    current=plan(clusters.get_cluster(payload['cluster_id'],task.group_id_id),
                        {int(key):dict(target['settings']) for key,target in payload['targets'].items()})
                    if current!=plans:raise certificates.CertificateError('Resource placement changed during certificate deployment','concurrent_change')
                payload['phase'] = 'commit'
                save(task, payload)
            finish(task, payload, renew=renew)
            success = payload['phase'] == 'commit'
            completed = dict(payload, phase='done', error_code=None if success else payload.get('failure_code'))
            completed.pop('bundle', None)
            save(task, completed, status='completed' if success else 'failed', finish_date=utc_now(),
                 error=None if success else 'Certificate update rolled back')
            return 'completed' if success else 'failed'
        except Exception as error:
            payload['error_code'] = getattr(error, 'code', 'operation_failed')
            if payload['phase'] == 'apply':
                payload['failure_code'] = payload['error_code']
                for target in payload['targets'].values():
                    if not target.get('started'):
                        target['status'] = 'not_applied'
                payload['phase'] = 'rollback'
                save(task, payload)
                try:
                    finish(task, payload, renew=renew)
                    payload['phase'] = 'done'
                    payload.pop('bundle', None)
                except Exception:
                    payload['error_code'] = 'recovery_failed'
            save(task, payload, status='failed', error='Certificate operation failed: ' + payload['error_code'],
                 finish_date=utc_now())
            return 'failed'
