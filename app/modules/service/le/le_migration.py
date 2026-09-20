"""Resumable import and explicit legacy cron cutover on the original host."""

import json
import os
from collections import defaultdict

from app.modules.common.time import utc_now
from app.modules.db.db_model import LetsEncrypt, LetsEncryptState, InstallationTasks, Server
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.service.le import le_store, le_certbot
from app.scripts import letsencrypt_remote as legacy


def _require_original_host(config):
    if (os.name != 'posix' or os.geteuid() != 0 or
            config.get_config_var('main', 'deployment_mode', 'package') != 'package'):
        raise RuntimeError('Run migrate-le-cron as root on the original package host before moving its database')


def migrate_legacy():
    config = GetConfigVar()
    _require_original_host(config)
    for task in InstallationTasks.select().where(
        (InstallationTasks.operation_type == 'ansible') & InstallationTasks.status.in_(le_store.ACTIVE)
    ):
        payload = deserialize_operation_payload(task.operation_payload)
        if any(step.get('ansible_role') in ('letsencrypt', 'letsencrypt_standalone')
               for step in payload.get('steps') or [payload]):
            raise RuntimeError('Legacy LE setup operations must finish before migration')
    states = list(LetsEncryptState.select().where(LetsEncryptState.legacy_pending == True))
    if not states:
        return 0
    local_names, remote_names = [], defaultdict(list)
    # Export and validate before disabling any renewal job. No new ACME orders.
    for state in states:
        row = LetsEncrypt.get_by_id(state.le_id)
        server = Server.get_by_id(row.server_id_id)
        data = le_store.validate_config(le_store.config_for(row, state), server.group_id)
        with le_store.transaction():
            le_store.check_destination(data, state.pem_name, server.group_id, state.le_id)
        request = {'operation': 'legacy-export', 'domain': data['domains'][0]}
        exported = (le_certbot.remote(server, request) if data['type'] == 'standalone'
                    else legacy.legacy_export(request))
        matched = []
        for bundle in exported['bundles']:
            # Expired certificates can still migrate; the first scheduled run
            # replaces them. Domain/key validation must still succeed.
            try:
                expires, fingerprint = le_certbot.inspect_bundle(bundle, data['domains'], allow_expired=True)
            except le_certbot.CertificateError:
                continue
            matched.append((expires, fingerprint, bundle))
        if exported['bundles'] and not matched:
            raise RuntimeError(f'Legacy certificate #{state.le_id} has different domains or key; inspect before cutover')
        if matched:
            expires, fingerprint, bundle = max(matched, key=lambda item: item[0])
            root = le_certbot.revision_root(state.le_id, state.revision)
            le_certbot.private_write(root / 'bundle.json', json.dumps(bundle))
            state.not_after, state.fingerprint = expires, fingerprint
            names = [entry[2]['name'] for entry in matched]
            if data['type'] == 'standalone':
                remote_names[server.server_id].extend(names)
            else:
                local_names.extend(names)
        elif data['type'] == 'standalone':
            remote_names[server.server_id]  # Still remove the stale standalone cron.
        state.save()
    # Imported private material must be readable by the configured runtime user.
    root = le_certbot.storage_root()
    owner = root.parent.stat()
    for directory, _, files in os.walk(root):
        os.chown(directory, owner.st_uid, owner.st_gid)
        os.chmod(directory, 0o700)
        for filename in files:
            path = os.path.join(directory, filename)
            os.chown(path, owner.st_uid, owner.st_gid)
            os.chmod(path, 0o600)
    legacy.legacy_disable({'names': local_names})
    for server_id, names in remote_names.items():
        le_certbot.remote(Server.get_by_id(server_id), {'operation': 'legacy-disable', 'names': names})
    with le_store.transaction():
        for candidate in states:
            state = le_store.locked(LetsEncryptState, LetsEncryptState.id == candidate.id)
            state.legacy_pending = False
            state.status = 'pending'
            state.next_run_at = utc_now()
            state.save()
    return len(states)
