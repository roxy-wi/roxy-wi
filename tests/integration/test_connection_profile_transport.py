"""Real loopback TLS/HTTP checks, including credential isolation on redirects."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import ssl
from threading import Event, Thread, enumerate as enumerate_threads
from time import monotonic

import pytest

from app.modules.integrations.connection_options import ResolvedConnection
from app.modules.integrations.connection_transport import check_connection
from tests.fixtures.certificate_runtime import make_pem


@contextmanager
def receiver(tmp_path, status=200, *, pem=None, client_ca=None, slow_headers=False):
    pem = pem or make_pem(domains=('localhost',))
    path = tmp_path / 'receiver.pem'
    path.write_text(pem)
    calls = []
    stopped = Event()

    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            calls.append((self.path, self.headers.get('Authorization'), self.headers.get('X-Audit-Key')))
            if slow_headers:
                try:
                    self.wfile.write(b'HTTP/1.1 200 OK\r\nX-Slow: ')
                    until = monotonic()+3
                    while monotonic() < until and not stopped.wait(0.15):
                        self.wfile.write(b'x')
                    self.wfile.write(b'\r\n\r\n')
                except OSError:
                    pass
                return
            self.send_response(status)
            if status == 302:
                self.send_header('Location', 'https://other.example.test/must-not-follow')
            self.end_headers()

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(path)
    if client_ca:
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cadata=client_ca)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, pem.split('-----BEGIN PRIVATE KEY-----')[0], calls
    finally:
        stopped.set()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive()


@pytest.mark.parametrize(('auth', 'expected'), [
    ('basic', 'Basic dXNlcjpwYXNzd29yZA=='), ('bearer', 'Bearer token-value'), ('api_key', None),
])
def test_actual_tls_receiver_gets_only_configured_authentication(tmp_path, auth, expected):
    with receiver(tmp_path) as (port, ca, calls):
        settings = dict(transport='https', host='localhost', port=port, timeout=2,
                        url=f'https://localhost:{port}/events', auth=auth, username='user',
                        header_name='X-Audit-Key')
        result = check_connection(ResolvedConnection(1, 1, settings, dict(
            ca_pem=ca, password='password', token='token-value')))
        assert result['status'] == 'accepted'
        assert result['http_status'] == 200
        assert calls == [('/events', expected, 'token-value' if auth == 'api_key' else None)]


def test_actual_tls_redirect_does_not_forward_credentials(tmp_path):
    with receiver(tmp_path, status=302) as (port, ca, calls):
        settings = dict(transport='https', host='localhost', port=port, timeout=2,
                        url=f'https://localhost:{port}/events', auth='bearer')
        result = check_connection(ResolvedConnection(1, 1, settings, dict(ca_pem=ca, token='token-value')))
        assert result['status'] == 'rejected'
        assert len(calls) == 1


def test_untrusted_actual_receiver_is_rejected_before_credentials(tmp_path):
    with receiver(tmp_path) as (port, _, calls):
        settings = dict(transport='https', host='localhost', port=port, timeout=2,
                        url=f'https://localhost:{port}/events', auth='bearer')
        with pytest.raises(ssl.SSLCertVerificationError):
            check_connection(ResolvedConnection(1, 1, settings, dict(token='token-value')))
        assert calls == []


def test_slow_head_headers_cannot_keep_connection_check_alive(tmp_path):
    with receiver(tmp_path, slow_headers=True) as (port, ca, calls):
        settings = dict(transport='https', host='localhost', port=port, timeout=1,
                        url=f'https://localhost:{port}/events', auth='bearer')
        started = monotonic()
        with pytest.raises((OSError, http.client.HTTPException)):
            check_connection(ResolvedConnection(1, 1, settings, dict(ca_pem=ca, token='SyntheticToken')))
        assert 0.7 <= monotonic()-started < 2
        assert calls == [('/events', 'Bearer SyntheticToken', None)]
        assert not any(thread.name == 'roxywi-connection-io-deadline' for thread in enumerate_threads())


def test_mutual_tls_receiver_requires_and_accepts_client_identity(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Test connection CA')])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(100)
          .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(ca_key, hashes.SHA256()))
    ca_pem = ca.public_bytes(serialization.Encoding.PEM).decode()

    def identity(name, serial, usage):
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (x509.CertificateBuilder().subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, name)])).issuer_name(ca_name)
            .public_key(key.public_key()).serial_number(serial)
            .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .sign(ca_key, hashes.SHA256()))
        return (cert.public_bytes(serialization.Encoding.PEM).decode(), key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode())

    server_cert, server_key = identity('localhost', 101, ExtendedKeyUsageOID.SERVER_AUTH)
    client_cert, client_key = identity('audit-client', 102, ExtendedKeyUsageOID.CLIENT_AUTH)
    with receiver(tmp_path, pem=server_cert+server_key, client_ca=ca_pem) as (port, _, calls):
        settings = dict(transport='https', host='localhost', port=port, timeout=2,
                        url=f'https://localhost:{port}/events', auth='none')
        with pytest.raises(OSError):
            check_connection(ResolvedConnection(1, 1, settings, dict(ca_pem=ca_pem)))
        assert calls == []
        result = check_connection(ResolvedConnection(1, 1, settings, dict(
            ca_pem=ca_pem, client_cert_pem=client_cert, client_key_pem=client_key)))
        assert result['status'] == 'accepted'
        assert len(calls) == 1
