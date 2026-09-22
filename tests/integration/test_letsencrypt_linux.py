"""Opt-in checks on a disposable Linux host with Docker and passwordless sudo.

The real SSH transport and HAProxy Runtime API are used. Certificates are
generated locally; public ACME validation still requires a staging domain.
"""

import hashlib
import getpass
import os
import socket
import ssl
import subprocess
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.service.le import le_certbot
from app.scripts import letsencrypt_remote


pytestmark = pytest.mark.skipif(
    os.name != 'posix' or os.environ.get('ROXYWI_TEST_DOCKER_LE') != '1',
    reason='Requires an opt-in disposable Linux host with Docker, sshd and sudo',
)


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=120).stdout.strip()


def wait_until(check):
    deadline = time.monotonic() + 30
    while True:
        try:
            return check()
        except (OSError, RuntimeError, le_certbot.CertificateError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)


@pytest.fixture
def ssh_target(tmp_path, monkeypatch):
    host_key, user_key = tmp_path / 'host-key', tmp_path / 'client-key'
    for key in (host_key, user_key):
        command('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    pidfile = tmp_path / 'sshd.pid'
    config = tmp_path / 'sshd_config'
    config.write_text(f'ListenAddress 127.0.0.1\nPort {port}\nHostKey {host_key}\n'
                      f'PidFile {pidfile}\nAuthorizedKeysFile {user_key}.pub\n'
                      f'AllowUsers {getpass.getuser()}\nPermitRootLogin no\nPasswordAuthentication no\n'
                      'KbdInteractiveAuthentication no\nUsePAM yes\nStrictModes no\n')
    command('sudo', '-n', 'mkdir', '-p', '/run/sshd')
    with (tmp_path / 'sshd.log').open('w') as log:
        process = subprocess.Popen(['sudo', '-n', '/usr/sbin/sshd', '-D', '-e', '-f', str(config)],
                                   stdout=log, stderr=log)
        try:
            def reachable():
                with socket.create_connection(('127.0.0.1', port), timeout=1):
                    return True
            wait_until(reachable)
            settings = dict(user=getpass.getuser(), port=port, password=None, enabled=1, key=str(user_key), passphrase=None)
            monkeypatch.setattr(le_certbot, 'return_ssh_keys_path', lambda _ip: settings)
            yield SimpleNamespace(ip='127.0.0.1')
        finally:
            if pidfile.exists():
                command('sudo', '-n', 'kill', '--', pidfile.read_text().strip())
            process.wait(timeout=10)


def make_pem(directory, serial):
    certificate, key = directory / f'{serial}.crt', directory / f'{serial}.key'
    command('openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
            '-nodes', '-days', '2', '-subj', '/CN=example.test', '-addext', 'subjectAltName=DNS:example.test',
            '-set_serial', str(serial), '-keyout', str(key), '-out', str(certificate))
    return certificate.read_text() + key.read_text()


def test_ssh_docker_reload_rollback_and_interrupted_finalize(tmp_path, ssh_target):
    certificates = tmp_path / 'certificates'
    certificates.mkdir()
    old, new = make_pem(tmp_path, 1), make_pem(tmp_path, 2)
    target = certificates / 'example.pem'
    target.write_text(old)
    target.chmod(0o600)
    config = tmp_path / 'haproxy.cfg'
    config.write_text('global\n  stats socket ipv4@0.0.0.0:1999 level admin\n'
                      'defaults\n  mode http\n  timeout connect 5s\n  timeout client 5s\n  timeout server 5s\n'
                      'frontend tls\n  bind :8443 ssl crt /tls/example.pem\n'
                      '  http-request return status 200 content-type text/plain string healthy\n')
    name = 'roxywi-le-test-' + uuid4().hex[:12]
    image = os.environ.get('ROXYWI_TEST_HAPROXY_IMAGE', 'haproxy:3.0-alpine')
    data = dict(cert_dir=str(certificates), config_path=str(config), docker=True, container=name,
                runtime_port=1999, pem_name='example.pem', pem=new, transaction=uuid4().hex)
    command('docker', 'run', '-d', '--name', name, '--user', '0:0',
            '-v', f'{certificates}:/tls', '-v', f'{config}:/usr/local/etc/haproxy/haproxy.cfg:ro',
            '--entrypoint', 'haproxy', image, '-W', '-db', '-f', '/usr/local/etc/haproxy/haproxy.cfg')
    try:
        wait_until(lambda: letsencrypt_remote.runtime_pid(data))

        def peer_fingerprint():
            host, _ = letsencrypt_remote.runtime_endpoint(data)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
            with socket.create_connection((host, 8443), timeout=5) as stream:
                with context.wrap_socket(stream, server_hostname='example.test') as connection:
                    return hashlib.sha256(connection.getpeercert(binary_form=True)).hexdigest()

        original = peer_fingerprint()
        assert le_certbot.remote(ssh_target, dict(data, operation='preflight'))['checked']
        assert le_certbot.remote(ssh_target, dict(data, operation='deploy'))['verification'] == 'loaded'
        replacement = peer_fingerprint()
        assert original != replacement
        # Recovery after the worker disappears following successful deployment.
        assert le_certbot.remote(ssh_target, dict(data, operation='deploy'))['deployed']
        assert le_certbot.remote(ssh_target, dict(data, operation='rollback'))['finished']
        assert peer_fingerprint() == original
        assert le_certbot.remote(ssh_target, dict(data, operation='rollback'))['finished']
        data['transaction'] = uuid4().hex
        assert le_certbot.remote(ssh_target, dict(data, operation='deploy'))['deployed']
        assert le_certbot.remote(ssh_target, dict(data, operation='commit'))['finished']
        assert le_certbot.remote(ssh_target, dict(data, operation='commit'))['finished']
        assert peer_fingerprint() == replacement
        # Invalid replacement must leave the last accepted certificate serving.
        with pytest.raises(le_certbot.CertificateError, match='configuration validation'):
            le_certbot.remote(ssh_target, dict(data, operation='deploy', transaction=uuid4().hex, pem='invalid PEM'))
        assert peer_fingerprint() == replacement
    finally:
        command('docker', 'rm', '-f', name)
