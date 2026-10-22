"""Real TLS handshakes against an isolated HAProxy, without touching system services."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import shutil
import shlex
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest

try:
    import roxywi_certificate_remote as remote
except ModuleNotFoundError:
    from app.scripts import certificate_remote as remote


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=20).stdout


def make_pem(root, name):
    key, cert = root / (name + '.key'), root / (name + '.crt')
    command('openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
            '-nodes', '-days', '2', '-subj', '/CN=' + name, '-addext', 'subjectAltName=DNS:' + name,
            '-keyout', str(key), '-out', str(cert))
    return cert.read_text() + key.read_text()


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def served_fingerprint(port, domain):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection(('127.0.0.1', port), timeout=3) as client:
        with context.wrap_socket(client, server_hostname=domain) as tls:
            return hashlib.sha1(tls.getpeercert(binary_form=True)).hexdigest().upper()


@contextmanager
def instance(kind):
    with tempfile.TemporaryDirectory(prefix='roxywi-runtime-create-') as temporary:
        root = Path(temporary)
        directory = root / ('certificates with spaces' if kind == 'directory' else 'certificates')
        directory.mkdir()
        old, new = make_pem(root, 'old.example.test'), make_pem(root, 'new.example.test')
        (directory / 'old.pem').write_text(old)
        listing = root / 'certificates list'
        listing.write_text(str(directory / 'old.pem') + '\n')
        destination = directory if kind == 'directory' else listing
        runtime_port, tls_port = free_port(), free_port()
        main = root / 'haproxy.cfg'
        main.write_text(
            f'global\n stats socket ipv4@127.0.0.1:{runtime_port} level admin\n'
            'defaults\n mode http\n timeout connect 2s\n timeout client 2s\n timeout server 2s\n'
            f'frontend tls\n bind 127.0.0.1:{tls_port} ssl {"crt" if kind == "directory" else "crt-list"} {shlex.quote(str(destination))}\n'
            ' http-request return status 200 content-type text/plain string healthy\n')
        data = dict(cert_dir=str(directory), pem_name='new.pem', config_path=str(main), runtime_port=runtime_port,
                    docker=False, apply_mode='runtime', destination=dict(path=str(destination), kind=kind),
                    pem=new, transaction='integration', validation=dict(service='haproxy', target=str(main),
                    candidate='', action='check', container='', root=str(root), main=str(main), sources=[str(main)]))
        original_root = remote.ROOT
        remote.ROOT = root / 'journals'
        with (root / 'process.log').open('w+') as log:
            process = subprocess.Popen(['haproxy', '-db', '-f', str(main)], stdout=log, stderr=log)
            def ready():
                deadline = time.monotonic() + 10
                while True:
                    try:
                        remote.runtime_pid(data)
                        break
                    except (OSError, RuntimeError):
                        if process.poll() is not None or time.monotonic() > deadline:
                            log.seek(0)
                            raise AssertionError('Isolated HAProxy did not start: ' + log.read())
                        time.sleep(.1)
            def restart():
                nonlocal process
                process.terminate()
                process.wait(timeout=5)
                process = subprocess.Popen(['haproxy', '-db', '-f', str(main)], stdout=log, stderr=log)
                ready()

            try:
                ready()
                yield data, tls_port, old, new, restart
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                remote.ROOT = original_root


@unittest.skipUnless(sys.platform == 'linux' and shutil.which('haproxy'), 'Linux and HAProxy required')
class RuntimeCertificateCreation(unittest.TestCase):
    def test_new_sni_certificate_is_served_without_reload_and_persisted(self):
        for kind in ('directory', 'crt_list'):
            with self.subTest(kind=kind), instance(kind) as (data, port, old, new, restart):
                original = served_fingerprint(port, 'new.example.test')
                self.assertEqual(original, remote.pem_fingerprint(old))
                pid = remote.runtime_pid(data)
                self.assertIn(data['destination'], remote.catalog(data)['destinations'])
                remote.deploy(data)
                self.assertEqual(served_fingerprint(port, 'new.example.test'), remote.pem_fingerprint(new))
                self.assertEqual(served_fingerprint(port, 'old.example.test'), original)
                self.assertEqual(remote.runtime_pid(data), pid)
                remote.deploy(data)  # Resume after a lost worker acknowledgement.
                remote.finish_deployment(dict(data, operation='commit'))
                remote.validate_configuration(data)
                self.assertEqual(Path(data['cert_dir'], 'new.pem').read_text(), new)
                self.assertFalse(list(remote.ROOT.rglob('pending.json')))
                restart()
                self.assertEqual(served_fingerprint(port, 'new.example.test'), remote.pem_fingerprint(new))

    def test_rollback_removes_new_sni_and_keeps_existing_certificate(self):
        for kind in ('directory', 'crt_list'):
            with self.subTest(kind=kind), instance(kind) as (data, port, old, new, _restart):
                pid = remote.runtime_pid(data)
                source = Path(data['destination']['path'])
                previous = source.read_bytes() if source.is_file() else None
                remote.deploy(data)
                self.assertEqual(served_fingerprint(port, 'new.example.test'), remote.pem_fingerprint(new))
                remote.finish_deployment(dict(data, operation='rollback'))
                self.assertEqual(served_fingerprint(port, 'new.example.test'), remote.pem_fingerprint(old))
                self.assertEqual(remote.runtime_pid(data), pid)
                self.assertFalse(Path(data['cert_dir'], 'new.pem').exists())
                if previous is not None:
                    self.assertEqual(source.read_bytes(), previous)
                self.assertFalse(list(remote.ROOT.rglob('pending.json')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
