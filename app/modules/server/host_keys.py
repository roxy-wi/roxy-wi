"""Explicit, short-lived approval of SSH host keys before authentication."""
import base64
import hashlib
import json
import os
import socket
import tempfile

import paramiko
from flask import current_app, g
from itsdangerous import BadData, URLSafeTimedSerializer

from app.modules.db.db_model import Cred, Groups, Server
from app.modules.roxywi.exception import RoxywiPermissionError, RoxywiPublicError
from app.modules.service.ha_mutation import guarded_server


CONFIRMATION_TTL = 600


class HostKeyError(RoxywiPublicError):
    """A host-key failure that can be shown without exposing credentials."""

    def __init__(self, message, status=400, **details):
        super().__init__(message)
        self.status = status
        self.response = dict(status='failed', error=message, **details)


def parse_key(value):
    """Read the public key format supported by the installed Paramiko version."""
    entry = paramiko.hostkeys.HostKeyEntry.from_line('server ' + value)
    if entry is None or entry.key is None:
        raise ValueError('Unsupported SSH host key')
    return entry.key


def fingerprint(value):
    """Return an OpenSSH-style SHA-256 fingerprint."""
    digest = hashlib.sha256(parse_key(value).asbytes()).digest()
    return 'SHA256:' + base64.b64encode(digest).decode('ascii').rstrip('=')


def write_known_hosts(pins, directory):
    """Give an Ansible job the same approved identities as SSHClient."""
    lines = []
    for pin in pins:
        host, port = pin['host'], int(pin['port'])
        if not host or any(char.isspace() for char in host):
            raise HostKeyError('Invalid SSH server address.')
        key = parse_key(pin['key'])
        name = host if port == 22 else f'[{host}]:{port}'
        lines.append(f'{name} {key.get_name()} {key.get_base64()}\n')
    descriptor, path = tempfile.mkstemp(
        dir=directory, prefix='roxywi-host-keys-', suffix='.pub')
    try:
        with os.fdopen(descriptor, 'w', encoding='ascii') as stream:
            stream.writelines(lines)
        return path
    except BaseException:
        os.unlink(path)
        raise


def probe(host, port, preferred_key=None):
    """Negotiate SSH and read its public host key without authenticating."""
    try:
        with socket.create_connection((host, port), timeout=11) as connection:
            with paramiko.Transport(connection) as transport:
                transport.banner_timeout = 11
                if preferred_key:
                    algorithm = parse_key(preferred_key).get_name()
                    options = transport.get_security_options()
                    preferred = tuple(
                        name for name in options.key_types
                        if name == algorithm
                        or (algorithm == 'ssh-rsa' and name.startswith('rsa-sha2-')))
                    options.key_types = preferred + tuple(
                        name for name in options.key_types if name not in preferred)
                transport.start_client(timeout=11)
                key = transport.get_remote_server_key()
                return key.get_name() + ' ' + key.get_base64()
    except (OSError, EOFError, paramiko.SSHException) as error:
        raise HostKeyError(
            'Cannot read the SSH host key. Check the server address, port and SSH availability.'
        ) from error


def _signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='ssh-host-key-confirmation-v1')


def _binding(host, port, group, **context):
    return dict(host=host, port=int(port), group=int(group),
                user=int(g.user_params['user_id']), **context)


def verify(host, port, binding, token=None, known_key=None, always_confirm=False):
    """Require approval of this exact key, actor, target and operation."""
    expected = None
    if token:
        try:
            approved = _signer().loads(token, max_age=CONFIRMATION_TTL)
        except BadData as error:
            raise HostKeyError(
                'SSH key confirmation expired or is invalid. Retry and review the fingerprint.', 409
            ) from error
        if approved.get('binding') != binding:
            raise HostKeyError('Server details changed. Retry and review the SSH fingerprint.', 409)
        expected = approved['key']

    observed = probe(host, port, expected or known_key)
    if expected == observed or (not always_confirm and known_key == observed and not token):
        return observed

    previous = expected or known_key
    details = dict(host=host, port=port, algorithm=parse_key(observed).get_name(),
                   fingerprint=fingerprint(observed), changed=bool(previous and previous != observed))
    if previous:
        details['previous_fingerprint'] = fingerprint(previous)
    raise HostKeyError(
        'Review and confirm the SSH host key before continuing.', 409,
        code='ssh_host_key_confirmation_required', host_key=details,
        confirmation=_signer().dumps(dict(binding=binding, key=observed)),
    )


def prepare_server(body, group, existing=None):
    """Validate references before probing a new or changed physical server."""
    if not Groups.select().where(Groups.group_id == group).exists():
        raise HostKeyError('Select an existing server group.')
    if not Cred.select().where(
        (Cred.id == body.cred_id) & ((Cred.group_id == group) | (Cred.shared == 1))
    ).exists():
        raise RoxywiPermissionError('SSH credentials are not available to this group')
    duplicate = Server.select().where(Server.ip == str(body.ip))
    if existing:
        duplicate = duplicate.where(Server.server_id != existing.server_id)
    if duplicate.exists():
        raise HostKeyError('A server with this address already exists.', 409)
    if body.type_ip:
        return None
    if (existing and not existing.type_ip
            and existing.ip == str(body.ip) and existing.port == body.port):
        return existing.ssh_host_key
    # Bind all form values: editing the target or selected credentials requires a
    # new review. A deleted/recreated registration cannot reuse an old approval.
    form = body.model_dump(mode='json', exclude={'ssh_host_key_confirmation'})
    form_hash = hashlib.sha256(json.dumps(form, sort_keys=True).encode()).hexdigest()
    binding = _binding(str(body.ip), body.port, group, operation='save-server',
                       registration=existing.registration_key if existing else None,
                       form=form_hash)
    return verify(str(body.ip), body.port, binding,
                  body.ssh_host_key_confirmation, always_confirm=True)


@guarded_server
def confirm_existing(server_id, token=None):
    """Approve a legacy or replaced key without overwriting a concurrent edit."""
    from app.modules.roxywi import common

    server = Server.get_by_id(server_id)
    common.require_active_group_access(server.group_id)
    if server.type_ip:
        raise HostKeyError('Virtual IPs do not have an SSH host key.')
    binding = _binding(server.ip, server.port, server.group_id, operation='confirm-server',
                       registration=server.registration_key, credential=server.cred_id,
                       previous_key=server.ssh_host_key)
    key = verify(server.ip, server.port, binding, token, server.ssh_host_key)
    if key != server.ssh_host_key:
        previous = (Server.ssh_host_key.is_null() if server.ssh_host_key is None
                    else Server.ssh_host_key == server.ssh_host_key)
        changed = Server.update(ssh_host_key=key).where(
            (Server.server_id == server_id) & (Server.registration_key == server.registration_key)
            & (Server.ip == server.ip) & (Server.port == server.port)
            & (Server.group_id == server.group_id) & (Server.cred_id == server.cred_id)
            & (Server.type_ip == 0) & previous).execute()
        if changed != 1:
            raise HostKeyError('Server details changed. Retry and review the SSH fingerprint.', 409)
        common.logging(server.ip, f'SSH host key confirmed: {fingerprint(key)}',
                       login=1, keep_history=1, service='server')
    return dict(status='ok', fingerprint=fingerprint(key))
