"""Actual loopback receivers verify wire framing, TLS and HTTPS authentication."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import socket
import ssl
from threading import Event, Thread, enumerate as enumerate_threads
from time import monotonic

import pytest

from app.modules.audit.delivery import send, ReceiverRejected
from app.modules.integrations.connection_options import ResolvedConnection
from tests.fixtures.certificate_runtime import make_pem


PAYLOAD = dict(id='72ed858e-66e3-4d3b-8f64-511776e784c8', timestamp='2026-10-29T12:00:00Z',
               schema=1, type='change.applied', outcome='succeeded', actor_id=1,
               actor_name='Synthetic User', group_id=1, source_ip='192.0.2.11',
               details=dict(status='applied', change_id=42))


@contextmanager
def stream_receiver(tmp_path, tls=False):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(4)
    calls, failures = [], []
    pem = make_pem(domains=('localhost',))
    path = tmp_path/'audit-server.pem'
    path.write_text(pem)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(path)
    def run():
        try:
            conn, _ = listener.accept()
            with conn:
                stream = context.wrap_socket(conn, server_side=True) if tls else conn
                with stream:
                    stream.settimeout(4)
                    chunks = []
                    while True:
                        chunk = stream.recv(4096)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    calls.append(b''.join(chunks))
        except Exception as error:
            failures.append(error)
    thread = Thread(target=run, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1], pem.split('-----BEGIN PRIVATE KEY-----')[0], calls
    finally:
        thread.join(5)
        listener.close()
        assert not thread.is_alive()
        assert not failures, failures


@pytest.mark.parametrize('tls', [False, True])
@pytest.mark.parametrize('framing', ['octet_counting', 'newline'])
def test_syslog_wire_format_and_transport_handoff(tmp_path, tls, framing):
    with stream_receiver(tmp_path, tls) as (port, ca, calls):
        connection = ResolvedConnection(1, 1, dict(transport='tcp_tls' if tls else 'tcp', host='localhost',
                                                  port=port, timeout=2, framing=framing), dict(ca_pem=ca) if tls else {})
        assert send(connection, PAYLOAD) == 'transport_handoff'
    data = calls[0]
    if framing == 'octet_counting':
        length, message = data.split(b' ', 1)
        assert int(length) == len(message)
    else:
        assert data.endswith(b'\n') and data.count(b'\n') == 1
        message = data[:-1]
    assert message.startswith(b'<86>1 2026-10-29T12:00:00Z ')
    assert b' roxy-wi ' in message and b' audit - ' in message
    assert json.loads(message.split(b' audit - ', 1)[1]) == PAYLOAD


def test_udp_is_a_single_datagram_and_never_claims_receipt():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(('127.0.0.1', 0))
        receiver.settimeout(2)
        settings = dict(transport='udp', host='127.0.0.1', port=receiver.getsockname()[1], timeout=2)
        assert send(ResolvedConnection(1, 1, settings, {}), PAYLOAD) == 'datagram_sent'
        data, _ = receiver.recvfrom(10000)
    assert data.startswith(b'<86>1 ') and not data.endswith(b'\n')
    assert json.loads(data.split(b' audit - ', 1)[1]) == PAYLOAD


@contextmanager
def https_receiver(tmp_path, status, slow_headers=False):
    pem = make_pem(domains=('localhost',))
    path = tmp_path/'audit-https.pem'
    path.write_text(pem)
    calls = []
    stopped = Event()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(dict(path=self.path, auth=self.headers.get('Authorization'),
                              key=self.headers.get('X-Audit-Key'),
                              body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
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
                self.send_header('Location', 'https://other.example.test/private')
            self.end_headers()
            self.wfile.write(b'PRIVATE_RECEIVER_RESPONSE')
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, pem.split('-----BEGIN PRIVATE KEY-----')[0], calls
    finally:
        stopped.set()
        server.shutdown()
        thread.join(5)
        server.server_close()
        assert not thread.is_alive()


@pytest.mark.parametrize(('auth', 'expected'), [('none', None), ('basic', 'Basic dXNlcjpwYXNz'),
                                               ('bearer', 'Bearer SyntheticToken'), ('api_key', None)])
def test_https_posts_json_and_authenticates_only_as_configured(tmp_path, auth, expected):
    with https_receiver(tmp_path, 202) as (port, ca, calls):
        settings = dict(transport='https', host='localhost', port=port, timeout=2,
                        url=f'https://localhost:{port}/audit', auth=auth, username='user', header_name='X-Audit-Key')
        result = send(ResolvedConnection(1, 1, settings, dict(ca_pem=ca, token='SyntheticToken', password='pass')), PAYLOAD)
        assert result == 'receiver_accepted'
        assert calls == [dict(path='/audit', auth=expected, key='SyntheticToken' if auth == 'api_key' else None, body=PAYLOAD)]


@pytest.mark.parametrize(('status', 'permanent'), [(302, False), (401, True), (429, False), (503, False)])
def test_https_rejections_do_not_follow_redirects_or_disclose_response_body(tmp_path, status, permanent):
    with https_receiver(tmp_path, status) as (port, ca, calls):
        settings = dict(transport='https', host='localhost', port=port, timeout=2,
                        url=f'https://localhost:{port}/audit', auth='bearer')
        with pytest.raises(ReceiverRejected) as failure:
            send(ResolvedConnection(1, 1, settings, dict(ca_pem=ca, token='SyntheticToken')), PAYLOAD)
        assert failure.value.code == f'HTTP {status}' and failure.value.permanent is permanent
        assert len(calls) == 1
        assert 'PRIVATE' not in str(failure.value) and 'SyntheticToken' not in str(failure.value)


def test_https_header_trickle_cannot_extend_absolute_delivery_deadline(tmp_path):
    with https_receiver(tmp_path, 200, slow_headers=True) as (port, ca, calls):
        settings = dict(transport='https', host='localhost', port=port, timeout=1,
                        url=f'https://localhost:{port}/audit', auth='bearer')
        started = monotonic()
        with pytest.raises((OSError, http.client.HTTPException)):
            send(ResolvedConnection(1, 1, settings, dict(ca_pem=ca, token='SyntheticToken')), PAYLOAD)
        assert 0.7 <= monotonic()-started < 2
        assert len(calls) == 1
        assert not any(thread.name == 'roxywi-connection-io-deadline' for thread in enumerate_threads())
