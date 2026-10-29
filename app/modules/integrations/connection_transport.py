"""Bounded connection checks without engine access, shell commands or redirects."""
from contextlib import contextmanager
import base64
import http.client
import ipaddress
import os
from pathlib import Path
import socket
import ssl
import tempfile
from threading import Event, Timer
from time import monotonic
from urllib.parse import urlsplit


def tls_context(credentials):
    context = ssl.create_default_context(cadata=credentials.get('ca_pem') or None)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if credentials.get('client_cert_pem'):
        with tempfile.TemporaryDirectory(prefix='roxywi-client-tls-') as folder:
            paths = []
            for name, key in [('certificate.pem', 'client_cert_pem'), ('key.pem', 'client_key_pem')]:
                path = Path(folder) / name
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    stream.write(credentials[key])
                paths.append(str(path))
            context.load_cert_chain(*paths)
    return context


def destination_addresses(host, port):
    addresses = []
    for family, _, _, _, address in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(address[0])
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            raise ValueError('Destination is not permitted')
        if str(ip) == 'fd00:ec2::254' or (ip.ipv4_mapped and ip.ipv4_mapped.is_link_local
                                        if isinstance(ip, ipaddress.IPv6Address) else False):
            raise ValueError('Destination is not permitted')
        if (family, address) not in addresses:
            addresses.append((family, address))
    if not addresses:
        raise ValueError('Destination did not resolve')
    return addresses


def open_socket(settings, credentials):
    # Resolve once and connect to that exact address; the TLS name stays the
    # configured host. Check all answers before sending any credentials.
    deadline = monotonic() + settings['timeout']
    addresses = destination_addresses(settings['host'], settings['port'])
    last_error = None
    for family, address in addresses:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError('Connection timeout')
        stream = socket.socket(family, socket.SOCK_STREAM)
        try:
            stream.settimeout(remaining)
            stream.connect(address)
        except OSError as error:
            last_error = error
            stream.close()
            continue
        try:
            if settings['transport'] in {'tcp_tls', 'https'}:
                stream = tls_context(credentials).wrap_socket(stream, server_hostname=settings['host'])
            return stream
        except BaseException:
            stream.close()
            raise
    raise last_error


@contextmanager
def bounded_stream(settings, credentials, deadline):
    stream = open_socket(settings, credentials)
    remaining = deadline-monotonic()
    if remaining <= 0:
        stream.close()
        raise TimeoutError('Connection deadline reached')
    expired = Event()
    def expire():
        expired.set()
        # HTTPResponse owns a socket file object. shutdown interrupts its reads;
        # closing only the original socket may leave that file object blocked.
        try:
            stream.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            stream.close()
        except OSError:
            pass
    timer = Timer(remaining, expire)
    timer.name = 'roxywi-connection-io-deadline'
    timer.daemon = True
    timer.start()
    try:
        yield stream
        if expired.is_set() or monotonic() >= deadline:
            raise TimeoutError('Connection deadline reached')
    finally:
        timer.cancel()
        timer.join()
        stream.close()


def http_headers(settings, credentials):
    headers = {'User-Agent': 'Roxy-WI connection check', 'Connection': 'close'}
    auth = settings['auth']
    if auth == 'basic':
        value = settings['username'] + ':' + credentials['password']
        headers['Authorization'] = 'Basic ' + base64.b64encode(value.encode()).decode('ascii')
    elif auth == 'bearer':
        headers['Authorization'] = 'Bearer ' + credentials['token']
    elif auth == 'api_key':
        headers[settings['header_name']] = credentials['token']
    return headers


def check_connection(connection):
    settings, credentials = connection.settings, connection.credentials
    if settings['transport'] == 'udp':
        return {'status': 'unverified', 'detail': 'UDP has no connection or delivery acknowledgement'}
    deadline = monotonic()+settings['timeout']
    with bounded_stream(settings, credentials, deadline) as stream:
        if settings['transport'] != 'https':
            return {'status': 'connected', 'detail': 'Transport connection established; no audit event was sent'}
        client = http.client.HTTPConnection(settings['host'], settings['port'], timeout=settings['timeout'])
        client.sock = stream
        try:
            parts = urlsplit(settings['url'])
            client.request('HEAD', parts.path or '/', headers=http_headers(settings, credentials))
            response = client.getresponse()
            status = response.status
            # Redirects are not followed and response content is not published.
            return {'status': 'accepted' if 200 <= status < 300 else 'rejected',
                    'http_status': status, 'detail': 'Receiver response to a HEAD connection check'}
        finally:
            client.close()
