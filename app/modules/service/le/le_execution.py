"""Serialized, recoverable Operations execution for certificate lifecycles."""

import json
import os
import shutil
import time
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace

from app.modules.common.time import utc_now
from app.modules.db.db_model import LetsEncrypt, LetsEncryptState, InstallationTasks, Server
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.service.le import le_store, le_certbot
from app.modules.roxywi.exception import RoxywiPublicError


@contextmanager
def certificate_lock(le_id):
    path = le_certbot.storage_root() / f'{int(le_id)}.lock'
    # Do not unlink: recovered workers must wait on the same inode.
    with path.open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            if stream.tell() == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in (13, 36):
                        raise
                    time.sleep(0.1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def delete_material(state, data, group_id):
    issuers = set(json.loads(state.issuer_servers))
    if data['type'] == 'standalone':
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
            targets = le_store.targets_for(data['server_id'], task.group_id)
            if operation not in ('delete', 'test'):
                with le_store.transaction():
                    le_store.check_destination(data, state.pem_name, task.group_id, state.le_id)
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
            else:
                runtime = SimpleNamespace(le_id=state.le_id, revision=(state.applied_revision
                    if operation in ('renew', 'test') and state.applied_revision else state.revision))
                if operation == 'issue' and state.applied_revision and data['type'] != 'standalone':
                    previous = le_store.config_for(row, state)
                    if any(data.get(key) != previous.get(key) for key in ('api_key', 'api_token')):
                        le_certbot.obtain(data, runtime, targets[0], test=True)
                bundle = le_certbot.obtain(data, runtime, targets[0], test=operation == 'test')
                if operation != 'test':
                    expires, fingerprint = le_certbot.inspect_bundle(bundle, data['domains'])
                    progress = json.loads(state.targets)
                    for server in targets:
                        key = str(server.server_id)
                        # A completed target is safe to skip after another target fails.
                        deployed = {'fingerprint': fingerprint, 'status': 'deployed', 'address': server.ip}
                        if progress.get(key) == deployed:
                            continue
                        progress[key] = {'status': 'deploying'}
                        state.targets = json.dumps(progress)
                        state.save()
                        try:
                            le_certbot.deploy(server, bundle, state.pem_name)
                        except Exception:
                            progress[key] = {'status': 'failed'}
                            state.targets = json.dumps(progress)
                            state.save()
                            raise
                        progress[key] = deployed
                        state.targets = json.dumps(progress)
                        state.save()
                    state.not_after, state.fingerprint = expires, fingerprint
                    state.applied_revision = runtime.revision
                state.status = 'active' if state.applied_revision else 'pending'
                state.next_run_at = utc_now() + timedelta(hours=12)
            with le_store.transaction():
                if operation not in ('delete', 'test'):
                    le_store.write_config(row, state, data)
                state.pending_config = None
                state.pending_action = 'renew'
                state.active_task_id = state.retry_at = None
                state.last_error = None
                state.failures = 0
                state.save()
                InstallationTasks.update(status='completed', error=None, finish_date=utc_now(),
                                         updated_at=utc_now()).where(InstallationTasks.id == task.id).execute()
            return 'completed'
        except Exception as error:
            detail = (error.public_message if isinstance(error, RoxywiPublicError) else
                      f'Certificate operation failed ({type(error).__name__}); check ACME, SSH and server configuration')
            with le_store.transaction():
                # A failed commit rolled back the configuration too. Do not
                # persist the mutated in-memory applied revision/credentials.
                state = le_store.locked(LetsEncryptState, LetsEncryptState.id == state.id)
                detail = le_store.record_failure(state, detail)
                state.save()
                InstallationTasks.update(status='failed', error=detail, finish_date=utc_now(),
                                         updated_at=utc_now()).where(InstallationTasks.id == task.id).execute()
            return 'failed'
