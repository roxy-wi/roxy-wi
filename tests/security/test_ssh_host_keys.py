"""Real SSH handshakes must verify identity before transmitting credentials."""
from contextlib import contextmanager
from io import StringIO
import socket
import threading

import paramiko
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.modules.server import host_keys
from app.modules.server.ssh_connection import SshConnection


pytestmark = pytest.mark.security


@pytest.fixture(scope='module')
def keys():
    private = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, serialization.NoEncryption())
    return (paramiko.RSAKey.generate(2048), paramiko.RSAKey.generate(2048),
            paramiko.ECDSAKey.generate(), paramiko.Ed25519Key.from_private_key(StringIO(private.decode())))


def public(key):
    return key.get_name() + ' ' + key.get_base64()


@contextmanager
def ssh_server(key):
    authentications = []
    failures = []
    stopped = threading.Event()

    class Server(paramiko.ServerInterface):
        def check_auth_password(self, username, password):
            authentications.append((username, password))
            return paramiko.AUTH_SUCCESSFUL

    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(4)
    listener.settimeout(0.1)

    def serve():
        while not stopped.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            try:
                with connection, paramiko.Transport(connection) as transport:
                    transport.add_server_key(key)
                    transport.start_server(server=Server())
                    while transport.is_active() and not stopped.wait(0.01):
                        pass
            except (EOFError, ConnectionResetError):
                # A client that rejects the host key closes before authentication.
                continue
            except Exception as error:
                failures.append(error)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1], authentications
    finally:
        stopped.set()
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive()
        assert not failures


def settings(port, key=None, host='127.0.0.1'):
    result = dict(port=port, user='test-user', password='synthetic-password', enabled=0,
                  key=None, passphrase=None)
    if key:
        result['host_key'] = dict(host=host, port=port, key=public(key))
    return result


@pytest.mark.parametrize('key_index', [0, 2, 3])
def test_fingerprint_probe_never_authenticates(keys, key_index):
    with ssh_server(keys[key_index]) as (port, authentications):
        value = host_keys.probe('127.0.0.1', port)
        assert value == public(keys[key_index])
        assert host_keys.fingerprint(value).startswith('SHA256:')
        assert len(host_keys.fingerprint(value)) == 50
        assert authentications == []


@pytest.mark.parametrize('key_index', [2, 3])
def test_approved_ecdsa_and_ed25519_keys_authenticate(keys, key_index):
    with ssh_server(keys[key_index]) as (port, authentications):
        with SshConnection('127.0.0.1', settings(port, keys[key_index])):
            assert len(authentications) == 1


def test_approval_is_bound_to_the_user(app, monkeypatch, keys):
    from flask import g
    monkeypatch.setattr(host_keys, 'probe', lambda *args: public(keys[0]))
    with app.test_request_context('/'):
        g.user_params = {'user_id': 1}
        binding = host_keys._binding('192.0.2.1', 22, 1)
        with pytest.raises(host_keys.HostKeyError) as review:
            host_keys.verify('192.0.2.1', 22, binding, always_confirm=True)
        g.user_params = {'user_id': 2}
        binding = host_keys._binding('192.0.2.1', 22, 1)
        with pytest.raises(host_keys.HostKeyError, match='Server details changed'):
            host_keys.verify('192.0.2.1', 22, binding, review.value.response['confirmation'])


@pytest.mark.parametrize('trust', ['unknown', 'changed', 'approved', 'other-host', 'other-port'])
def test_ssh_authenticates_only_the_approved_peer(keys, monkeypatch, trust):
    monkeypatch.setattr(paramiko.SSHClient, 'load_system_host_keys', lambda *_: None)
    with ssh_server(keys[0]) as (port, authentications):
        key = None if trust == 'unknown' else keys[1] if trust == 'changed' else keys[0]
        host = '192.0.2.99' if trust == 'other-host' else '127.0.0.1'
        options = settings(port, key, host)
        if trust == 'other-port':
            options['host_key']['port'] = port + 1
        connection = SshConnection('127.0.0.1', options, banner_timeout=2)
        assert isinstance(connection.ssh._policy, paramiko.RejectPolicy)
        if trust == 'approved':
            with connection:
                assert authentications == [('test-user', 'synthetic-password')]
        else:
            with pytest.raises(paramiko.SSHException):
                with connection:
                    pytest.fail('Unapproved connection succeeded')
            assert authentications == []
            assert connection.ssh.get_transport() is None


def test_previously_trusted_known_hosts_remains_supported(keys, monkeypatch):
    with ssh_server(keys[0]) as (port, authentications):
        def trusted(client):
            client.get_host_keys().add(f'[127.0.0.1]:{port}', 'ssh-rsa', keys[0])
        monkeypatch.setattr(paramiko.SSHClient, 'load_system_host_keys', trusted)
        with SshConnection('127.0.0.1', settings(port)):
            assert len(authentications) == 1


def test_probe_failure_is_actionable_and_does_not_expose_raw_errors(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('internal transport details')
    monkeypatch.setattr(host_keys.socket, 'create_connection', fail)
    with pytest.raises(host_keys.HostKeyError, match='Check the server address') as failure:
        host_keys.probe('192.0.2.1', 22)
    assert 'internal transport details' not in str(failure.value)
