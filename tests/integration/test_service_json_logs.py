"""Run real services on loopback ports with temporary configs and log files.

Opt in with ROXYWI_TEST_SERVICE_LOGS=1. Can also run directly with Python and
Jinja2, without importing the application or installing pytest on the host.
"""
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest

from jinja2 import Environment, FileSystemLoader, StrictUndefined


ROLES = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles'
ENABLED = os.environ.get('ROXYWI_TEST_SERVICE_LOGS') == '1' and os.name == 'posix'


def render(name, **values):
    env = Environment(loader=FileSystemLoader(str(ROLES)), undefined=StrictUndefined)
    return env.get_template(name).render(**values)


def free_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_until(read, predicate, description):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(.05)
    raise AssertionError(f'Timed out waiting for {description}: {value!r}')


def records(path):
    if not path.exists():
        return []
    data = path.read_text(encoding='utf-8')
    # Ignore only a final, incomplete write. Every complete line must be JSON.
    return [json.loads(line) for line in data.splitlines(keepends=True) if line.endswith('\n')]


@contextlib.contextmanager
def running(command, directory):
    with tempfile.TemporaryFile(mode='w+') as output:
        process = subprocess.Popen(command, cwd=directory, stdout=output, stderr=output)
        try:
            yield process
        except Exception:
            output.seek(0)
            print(output.read())
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def request(port, uri='/probe', user_agent='json-test'):
    with socket.create_connection(('127.0.0.1', port), timeout=2) as connection:
        data = f'GET {uri} HTTP/1.1\r\nHost: localhost\r\nUser-Agent: {user_agent}\r\nConnection: close\r\n\r\n'
        connection.sendall(data.encode('utf-8'))
        response = b''
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                return response
            response += chunk


def port_ready(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.1):
            return True
    except OSError:
        return False


@unittest.skipUnless(ENABLED, 'Opt-in Linux service log test')
class ServiceJSONLogs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='roxywi-json-logs-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def check_config(self, command):
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @contextlib.contextmanager
    def syslog(self):
        if not shutil.which('rsyslogd'):
            self.skipTest('rsyslogd is required')
        port = free_port(socket.SOCK_DGRAM)
        config = render('haproxy/templates/haproxy_rsyslog.conf.j2')
        config = config.replace('$UDPServerRun 514', f'$UDPServerRun {port}')
        config = config.replace('/var/log/haproxy', str(self.root))
        path = self.root / 'rsyslog.conf'
        path.write_text(config, encoding='utf-8')
        self.check_config(['rsyslogd', '-N1', '-f', str(path)])
        with running(['rsyslogd', '-n', '-i', str(self.root / 'rsyslog.pid'), '-f', str(path)], self.root):
            # A UDP send can succeed before the receiver binds. Probe with an
            # informational record until it is actually written.
            def probe():
                self.send_syslog(port, 'ready')
                return records(self.root / 'access.log')
            wait_until(probe, bool, 'rsyslog receiver')
            yield port

    def send_syslog(self, port, message, severity=6):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            header = f'<{128 + severity}>Jan  1 00:00:00 localhost haproxy[123]: '
            sock.sendto((header + message).encode('utf-8'), ('127.0.0.1', port))

    def test_rsyslog_json_and_legacy_error_records(self):
        with self.syslog() as port:
            native = {'timestamp': '2026-09-23T12:34:56Z', 'level': 'INFO',
                      'process_role': 'haproxy', 'message': 'quotes " slash \\ Юникод', 'status': 200}
            self.send_syslog(port, json.dumps(native))
            plain = 'backend "quoted" failed \\ retry'
            self.send_syslog(port, plain, severity=3)
            self.send_syslog(port, '{truncated JSON', severity=4)
            self.send_syslog(port, json.dumps({**native, 'message': 'traffic error'}), severity=3)
            access = wait_until(lambda: records(self.root / 'access.log'),
                                lambda rows: any(row.get('status') == 200 for row in rows), 'JSON traffic record')
            self.assertIn(native, access)
            errors = wait_until(lambda: records(self.root / 'error.log'), bool, 'error record')
            self.assertEqual(errors[0]['message'].strip(), plain)
            self.assertEqual(errors[0]['level'], 'ERROR')
            errors = wait_until(lambda: records(self.root / 'error.log'), lambda rows: len(rows) >= 2, 'traffic error')
            self.assertEqual(errors[-1]['message'], 'traffic error')
            self.assertEqual(errors[-1]['level'], 'ERROR')
            status = wait_until(lambda: records(self.root / 'status.log'), lambda rows: len(rows) >= 2, 'status records')
            self.assertTrue(any(row['level'] == 'WARNING' and '{truncated JSON' in row['message'] for row in status))

    def test_haproxy_http_and_tcp_defaults(self):
        if not shutil.which('haproxy'):
            self.skipTest('haproxy is required')
        with self.syslog() as log_port:
            http_port, tcp_port, stats_port = free_port(), free_port(), free_port()
            config = render('haproxy/templates/haproxy.cfg.j2', SOCK_PORT=free_port(),
                            STAT_PORT=stats_port, STAT_FILE=str(self.root / 'state'),
                            STATS_USER='test', STATS_PASS='test-only')
            # Isolate process resources; retain the actual defaults and log format.
            config = re.sub(r'^\s+(?:chroot|pidfile|user|group|daemon|stats socket|server-state-file)\b.*\n', '', config, flags=re.M)
            config = config.replace('127.0.0.1 len 8192', f'127.0.0.1:{log_port} len 8192')
            config = config.replace(f'bind *:{stats_port}', f'bind 127.0.0.1:{stats_port}')
            config += f'\nfrontend json_http\n    bind 127.0.0.1:{http_port}\n    http-request return status 200 content-type text/plain string ok\n'

            class Echo(socketserver.BaseRequestHandler):
                def handle(self):
                    self.request.sendall(self.request.recv(1024))

            with socketserver.TCPServer(('127.0.0.1', 0), Echo) as backend:
                thread = threading.Thread(target=backend.serve_forever, daemon=True)
                thread.start()
                self.addCleanup(backend.shutdown)
                config += f'\nlisten json_tcp\n    bind 127.0.0.1:{tcp_port}\n    mode tcp\n    server echo 127.0.0.1:{backend.server_address[1]}\n'
                path = self.root / 'haproxy.cfg'
                path.write_text(config, encoding='utf-8')
                self.check_config(['haproxy', '-c', '-f', str(path)])
                with running(['haproxy', '-db', '-f', str(path)], self.root):
                    wait_until(lambda: port_ready(http_port), bool, 'HAProxy HTTP listener')
                    uri = '/probe?value="quoted"\\slash&long=' + 'x' * 1200
                    self.assertIn(b'200', request(http_port, uri).split(b'\r\n')[0])
                    with socket.create_connection(('127.0.0.1', tcp_port), timeout=2) as connection:
                        connection.sendall(b'tcp-json')
                        self.assertEqual(connection.recv(1024), b'tcp-json')
                    rows = wait_until(lambda: records(self.root / 'access.log'),
                                      lambda rows: any(row.get('frontend') == 'json_tcp' for row in rows), 'TCP record')
                    http = next(row for row in rows if row.get('frontend') == 'json_http' and row.get('status') == 200)
                    self.assertTrue(http['uri'].startswith('/probe?value="quoted"\\slash'))
                    self.assertEqual(http['method'], 'GET')
                    self.assertEqual(http['process_role'], 'haproxy')
                    self.assertTrue(http['timestamp'].endswith('Z'))
                    tcp = next(row for row in rows if row.get('frontend') == 'json_tcp')
                    self.assertEqual(tcp['server'], 'echo')
                    self.assertEqual(tcp['bytes'], '8')

    def test_nginx_access_log_templates(self):
        if not shutil.which('nginx'):
            self.skipTest('nginx is required')
        for role in ('service_common', 'service_docker'):
            with self.subTest(role=role):
                root = self.root / role
                root.mkdir()
                (root / 'conf.d').mkdir()
                (root / 'mime.types').write_text('types { text/plain txt; }\n')
                config = render(f'{role}/templates/nginx.conf.j2', ansible_facts={'os_family': 'Debian'})
                config = re.sub(r'^user\s+.*;\n', '', config)
                config = config.replace('/var/log/nginx/', str(root) + '/')
                config = config.replace('/etc/nginx/', str(root) + '/')
                config = config.replace('/var/run/nginx.pid', str(root / 'nginx.pid'))
                temp_paths = ''.join(f'\n    {kind}_temp_path {root}/{kind};'
                                     for kind in ('client_body', 'proxy', 'fastcgi', 'uwsgi', 'scgi'))
                config = config.replace('http {', 'http {' + temp_paths)
                port = free_port()
                (root / 'conf.d/test.conf').write_text(
                    f'server {{ listen 127.0.0.1:{port}; access_log {root}/vhost.log main; return 200 "ok"; }}\n')
                path = root / 'nginx.conf'
                path.write_text(config, encoding='utf-8')
                self.check_config(['nginx', '-t', '-p', str(root), '-c', str(path), '-e', str(root / 'startup.log')])
                with running(['nginx', '-p', str(root), '-c', str(path), '-e', str(root / 'startup.log'),
                              '-g', 'daemon off; master_process off;'], root):
                    wait_until(lambda: port_ready(port), bool, 'NGINX listener')
                    agent = 'quote " slash \\ tab\t Юникод'
                    self.assertIn(b'200', request(port, '/probe?value="quoted"\\slash', agent).split(b'\r\n')[0])
                    rows = wait_until(lambda: records(root / 'vhost.log'), bool, 'NGINX JSON record')
                    self.assertEqual(rows[0]['user_agent'], agent)
                    self.assertEqual(rows[0]['status'], 200)
                    self.assertIn(rows[0]['upstream_status'], ('', '-'))
                    self.assertEqual(rows[0]['process_role'], 'nginx')
                    self.assertIn('GET /probe?', rows[0]['message'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
