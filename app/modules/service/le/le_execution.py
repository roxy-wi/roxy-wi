"""Serialized, recoverable Operations execution for certificate lifecycles."""

import json
import shutil
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.modules.common.time import utc_now
from app.modules.db.db_model import LetsEncrypt, LetsEncryptState, InstallationTasks, Server
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.service.le import le_store, le_certbot, le_profiles
from app.modules.service.le.le_lock import file_lock
from app.modules.roxywi.exception import RoxywiPublicError


def certificate_lock(le_id):
    # Do not unlink: recovered workers must wait on the same inode.
    return file_lock(le_certbot.storage_root() / f'{int(le_id)}.lock')


def delete_material(state, data, group_id):
    issuers = set(json.loads(state.issuer_servers))
    if data['type'] == 'standalone' and state.applied_revision:
        issuers.add(data['server_id'])
    for server_id in sorted(issuers):
        server = Server.get_by_id(server_id)
        if str(server.group_id) != str(group_id):
            raise le_certbot.CertificateError('A former certificate issuer belongs to another group; administrator cleanup is required')
        le_certbot.remote(server, {'operation': 'delete', 'le_id': state.le_id})
    root = le_certbot.storage_root()
    target = root / str(int(state.le_id))
    if target.parent != root or target.is_symlink() or state.le_id <= 0:
        raise le_certbot.CertificateError('Invalid certificate storage directory')
    if target.exists():
        shutil.rmtree(target)


def finish_deployment(state, group_id, phase):
    deployment = json.loads(state.deployment)
    deployment['phase'] = phase
    state.deployment = json.dumps(deployment)
    state.save()
    progress = json.loads(state.targets)
    failed = []
    for key, target in deployment['targets'].items():
        if target.get(phase):
            continue
        try:
            server = Server.get_by_id(int(key))
            if str(server.group_id) != str(group_id) or server.ip != target['address']:
                raise le_certbot.CertificateError('Recovery target ownership or address changed; administrator action required')
            le_certbot.remote(server, dict(target['settings'], operation=phase, transaction=deployment['id']))
            target[phase] = True
            if phase == 'rollback':
                progress[key] = {'status': 'rolled_back', 'address': server.ip}
        except Exception:
            failed.append(key)
            if phase == 'rollback':
                progress[key] = {'status': 'rollback_failed', 'address': target['address']}
        state.deployment, state.targets = json.dumps(deployment), json.dumps(progress)
        state.save()
    if failed:
        raise le_certbot.CertificateError('Certificate ' + phase + ' incomplete on servers ' + ', '.join(failed))
    state.deployment = '{}'
    state.save()


def execute(task):
    payload = deserialize_operation_payload(task.operation_payload)
    with certificate_lock(payload['le_id']):
        current = InstallationTasks.get_or_none(
            (InstallationTasks.id == task.id) & (InstallationTasks.operation_id == task.operation_id))
        if current is None:
            return 'missing'
        if current.status in ('completed', 'failed'):
            return current.status
        state = LetsEncryptState.get(LetsEncryptState.le_id == payload['le_id'])
        if state.active_task_id != task.id or state.revision != payload['revision']:
            InstallationTasks.update(status='failed', error='Superseded certificate operation',
                                     finish_date=utc_now(), updated_at=utc_now()).where(InstallationTasks.id == task.id).execute()
            return 'failed'
        operation = payload['action']
        try:
            data = deserialize_operation_payload(state.pending_config)
            row = LetsEncrypt.get_by_id(state.le_id)
            deployment = json.loads(state.deployment)
            if deployment.get('phase') == 'rollback':
                finish_deployment(state, task.group_id, 'rollback')
                raise le_certbot.CertificateError('Previous partial deployment was rolled back; issuance can be retried')
            committing = deployment.get('phase') == 'commit'
            if not committing and operation != 'delete':
                data = le_profiles.resolve(data, task.group_id)
                if state.draft and operation == 'issue' and not deployment:
                    le_store.require_preflight(state, data)
            targets = le_store.targets_for(data['server_id'], task.group_id) if not committing else []
            if not committing and operation not in ('delete', 'test', 'preflight'):
                with le_store.transaction():
                    le_store.check_destination(data, state.pem_name, task.group_id, state.le_id)
                addresses = {str(server.server_id): server.ip for server in targets}
                if any(addresses.get(key) != target['address'] for key, target in deployment.get('targets', {}).items()):
                    raise le_certbot.CertificateError('Deployment targets changed; recovery is required')
            state.status = 'deleting' if operation == 'delete' else 'running'
            state.save()
            if operation == 'delete':
                delete_material(state, data, task.group_id)
                state.status = 'deleted'
                state.credentials = ''
                state.issuer_servers = '[]'
                row.api_key = row.api_token = ''
                row.save()
                state.next_run_at = None
            elif not committing:
                runtime = SimpleNamespace(le_id=state.le_id, revision=(state.applied_revision
                    if operation in ('renew', 'test') and state.applied_revision else state.revision))
                if operation == 'preflight':
                    from app.modules.service.le.le_preflight import run
                    run(state, data, runtime, targets)
                    bundle = None
                elif operation == 'issue' and state.applied_revision and data['type'] != 'standalone':
                    previous = le_store.config_for(row, state)
                    if any(data.get(key) != previous.get(key) for key in ('api_key', 'api_token')):
                        le_certbot.obtain(data, runtime, targets[0], test=True)
                if operation != 'preflight':
                    bundle = le_certbot.obtain(data, runtime, targets[0], test=operation == 'test')
                if operation not in ('test', 'preflight'):
                    expires, fingerprint = le_certbot.inspect_bundle(bundle, data['domains'])
                    deployment = json.loads(state.deployment) or {'id': str(uuid4()), 'phase': 'apply', 'targets': {}}
                    progress = json.loads(state.targets)
                    for server in targets:
                        key = str(server.server_id)
                        # A completed target is safe to skip after another target fails.
                        deployed = {'fingerprint': fingerprint, 'status': 'deployed', 'address': server.ip}
                        if all(progress.get(key, {}).get(field) == value for field, value in deployed.items()):
                            continue
                        target = deployment['targets'].setdefault(key, {
                            'address': server.ip, 'settings': le_certbot.deployment_settings(server, state.pem_name)})
                        if target['address'] != server.ip:
                            raise le_certbot.CertificateError('Deployment target address changed; recovery is required')
                        state.deployment = json.dumps(deployment)
                        progress[key] = {'status': 'deploying'}
                        state.targets = json.dumps(progress)
                        state.save()
                        try:
                            result = le_certbot.deploy(server, bundle, state.pem_name,
                                                      settings=target['settings'], transaction=deployment['id'])
                        except Exception:
                            progress[key] = {'status': 'failed'}
                            state.targets = json.dumps(progress)
                            state.save()
                            raise
                        progress[key] = deployed
                        if result and result.get('verification'):
                            progress[key]['verification'] = result['verification']
                        state.targets = json.dumps(progress)
                        state.save()
                    state.not_after, state.fingerprint = expires, fingerprint
                    state.applied_revision = runtime.revision
                state.status = 'ready' if operation == 'preflight' else ('active' if state.applied_revision else 'pending')
                state.next_run_at = None if state.draft else utc_now() + timedelta(hours=12)
            if operation not in ('delete', 'test', 'preflight') and not committing:
                # Persist the applied configuration before discarding remote backups.
                # A lost DB commit leaves phase=apply, which is safe to roll back.
                with le_store.transaction():
                    data['draft'] = False
                    le_store.write_config(row, state, data)
                    state.next_run_at = utc_now() + timedelta(hours=12)
                    deployment['phase'] = 'commit'
                    state.deployment = json.dumps(deployment)
                    state.save()
            if operation not in ('delete', 'test', 'preflight'):
                finish_deployment(state, task.group_id, 'commit')
                state.status = 'active'
            with le_store.transaction():
                state.pending_config = None
                state.pending_action = 'renew'
                state.active_task_id = state.retry_at = None
                state.last_error = None
                state.last_error_code = None
                state.failures = 0
                state.save()
                InstallationTasks.update(status='completed', error=None, finish_date=utc_now(),
                                         updated_at=utc_now()).where(InstallationTasks.id == task.id).execute()
            return 'completed'
        except Exception as error:
            detail = (error.public_message if isinstance(error, RoxywiPublicError) else
                      f'Certificate operation failed ({type(error).__name__}); check ACME, SSH and server configuration')
            state = LetsEncryptState.get_by_id(state.id)
            deployment = json.loads(state.deployment)
            if deployment.get('phase') == 'apply':
                try:
                    finish_deployment(state, task.group_id, 'rollback')
                except le_certbot.CertificateError as recovery_error:
                    detail += '; ' + recovery_error.public_message
            with le_store.transaction():
                # A failed commit rolled back the configuration too. Do not
                # persist the mutated in-memory applied revision/credentials.
                state = le_store.locked(LetsEncryptState, LetsEncryptState.id == state.id)
                detail = le_store.record_failure(state, detail, code=getattr(error, 'code', 'certificate_failed'),
                                                 retry_at=getattr(error, 'retry_at', None))
                state.save()
                InstallationTasks.update(status='failed', error=detail, finish_date=utc_now(),
                                         updated_at=utc_now()).where(InstallationTasks.id == task.id).execute()
            return 'failed'
