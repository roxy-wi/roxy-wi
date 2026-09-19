import errno
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import stat
import threading
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from app.modules.service import backup_transfer as transfer
from app.modules.service.backup_migration import remove_legacy_entries
from app.modules.service.backup_scheduler import next_run
from datetime import datetime


@pytest.mark.parametrize('period, after, expected', [
    ('hourly', datetime(2026, 9, 16, 10), datetime(2026, 9, 16, 11)),
    ('daily', datetime(2026, 9, 16, 10), datetime(2026, 9, 17)),
    ('weekly', datetime(2026, 9, 19, 10), datetime(2026, 9, 20)),
    ('monthly', datetime(2026, 12, 31, 23), datetime(2027, 1, 1)),
])
def test_calendar_boundaries(period, after, expected):
    assert next_run(period, 'UTC', after) == expected


def test_schedule_stores_utc_while_preserving_local_midnight():
    assert next_run('daily', 'Europe/Moscow', datetime(2026, 9, 16, 18)) == datetime(2026, 9, 16, 21)
    assert next_run('daily', 'America/New_York', datetime(2026, 3, 8, 6)) == datetime(2026, 3, 9, 4)
    assert next_run('hourly', 'America/New_York', datetime(2026, 3, 8, 6, 30)) == datetime(2026, 3, 8, 7)
    assert next_run('hourly', 'America/New_York', datetime(2026, 11, 1, 5, 30)) == datetime(2026, 11, 1, 6)


@pytest.mark.parametrize('value', ['https://user:secret@s3.test', 'file:///tmp/x', 'https://s3.test/path',
                                  'https://s3.test?token=secret', 'ftp://s3.test', 'https:///'])
def test_s3_rejects_credential_bearing_and_non_origin_endpoints(value):
    with pytest.raises(ValueError):
        transfer.endpoint_url(value)


def test_s3_defaults_to_tls_and_accepts_explicit_local_endpoint():
    assert transfer.endpoint_url('192.0.2.1') == 'https://192.0.2.1'
    assert transfer.endpoint_url('http://localhost:9000/') == 'http://localhost:9000'


def test_filename_selection_does_not_cross_server_boundaries():
    assert transfer.owns_file('192.0.2.1-2026-09-16.100000.cfg', '192.0.2.1')
    assert not transfer.owns_file('192.0.2.10-2026-09-16.cfg', '192.0.2.1')
    assert not transfer.owns_file('web-other-2026.cfg', 'web', ['web', 'web-other'])
    assert not transfer.owns_file('192.0.2.1-key.pem', '192.0.2.1')
    assert transfer.owns_file('2001db81-2026.conf', '2001:db8::1')
    assert not transfer.owns_file('2001db81-2026.conf', '2001:db8::1', ['2001:db8:1::'])


def test_cutover_only_removes_ansible_backup_entries():
    untouched = ('MAILTO=ops@example.test\n# user backup\n@daily user-backup\n'
                 '#Ansible: Git backup haproxy configs\n@daily git push\n'
                 '#Ansible: Renew certificates\n@daily certbot renew\n')
    old = ('#Ansible: Roxy-WI Backup configs for server 192.0.2.1 hap_config\n@daily rsync\n'
           '#Ansible: Roxy-WI S3 Backup configs for server source bucket nginx_config\n@weekly s3cmd\n')
    assert remove_legacy_entries(untouched + old) == (untouched, 2)
    assert remove_legacy_entries(untouched) == (untouched, 0)
    with pytest.raises(ValueError):
        remove_legacy_entries('#Ansible: Roxy-WI Backup configs for server x hap_config\n# user job\n')


def test_real_boto_upload_retry_and_unchanged_object_skip(tmp_path, monkeypatch):
    """Exercise SDK signing and transfer code against an isolated S3 HTTP fixture."""
    objects, uploads = {}, []
    bucket_exists = [False]
    failures = [1]
    class S3Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_HEAD(self):
            if self.path == '/configs':
                self.send_response(200 if bucket_exists[0] else 404)
            elif self.path in objects:
                data, digest = objects[self.path]
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('x-amz-meta-sha256', digest)
            else:
                self.send_response(404)
            self.end_headers()
        def do_PUT(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            if self.path == '/configs':
                bucket_exists[0] = True
            elif failures[0]:
                failures[0] -= 1
                self.send_response(503)
                self.end_headers()
                return
            else:
                uploads.append(self.path)
                objects[self.path] = (body, self.headers['x-amz-meta-sha256'])
            self.send_response(200)
            self.send_header('ETag', '"test-etag"')
            self.end_headers()
    server = ThreadingHTTPServer(('127.0.0.1', 0), S3Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv('NO_PROXY', '127.0.0.1')
    config = SimpleNamespace(s3_server=f'http://127.0.0.1:{server.server_port}', bucket='configs',
                             access_key='test-access', secret_key='test-secret')
    source = SimpleNamespace(hostname='display-name')
    path = tmp_path / '192.0.2.1-2026.cfg'
    path.write_bytes(b'global\n  maxconn 1000\n')
    try:
        transfer.upload_s3(config, source, {'hap_config': [path]})
        transfer.upload_s3(config, source, {'hap_config': [path]})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
    assert failures[0] == 0
    assert uploads == ['/configs/display-name/hap_config/' + path.name]
    assert objects[uploads[0]] == (path.read_bytes(), hashlib.sha256(path.read_bytes()).hexdigest())


class SftpFixture:
    def __init__(self, root, fail_upload=False):
        self.root = root
        self.fail_upload = fail_upload
        self.renamed = []
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return None
    def get_channel(self):
        return SimpleNamespace(settimeout=lambda _seconds: None)
    def path(self, name):
        return self.root / name.lstrip('/')
    def lstat(self, name):
        return self.path(name).lstat()
    def mkdir(self, name, mode):
        self.path(name).mkdir(mode=mode)
    def put(self, source, destination):
        if self.fail_upload:
            raise OSError('Upload interrupted')
        self.path(destination).write_bytes(Path(source).read_bytes())
    def chmod(self, name, mode):
        self.path(name).chmod(mode)
    def posix_rename(self, source, destination):
        self.renamed.append((source, destination))
        self.path(source).replace(self.path(destination))
    def listdir_attr(self, name):
        return [SimpleNamespace(filename=path.name, st_mode=path.lstat().st_mode)
                for path in self.path(name).iterdir()]
    def remove(self, name):
        self.path(name).unlink()


@pytest.mark.parametrize('mode', ['backup', 'synchronization'])
@pytest.mark.parametrize('fail_upload', [False, True])
def test_sftp_atomic_upload_retention_and_failure_cleanup(tmp_path, monkeypatch, mode, fail_upload):
    remote = tmp_path / 'remote'
    target = remote / 'backups/roxy-wi-configs-backup/configs/hap_config'
    target.mkdir(parents=True)
    (target / '192.0.2.1-old.cfg').write_text('old')
    (target / '192.0.2.10-other.cfg').write_text('another server')
    (target / 'notes.txt').write_text('user file')
    source = tmp_path / '192.0.2.1-new.cfg'
    source.write_text('new')
    sftp = SftpFixture(remote, fail_upload)
    class Connection:
        def __init__(self, *_args, **_kwargs):
            self.ssh = SimpleNamespace(open_sftp=lambda: sftp)
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
    monkeypatch.setattr(transfer, 'SshConnection', Connection)
    monkeypatch.setattr(transfer, 'return_ssh_keys_path', lambda *_args: {})
    config = SimpleNamespace(rpath='/backups', rserver='backup.test', cred_id=1, type=mode)
    server = SimpleNamespace(ip='192.0.2.1')
    args = (config, server, {'hap_config': [source]}, ['192.0.2.1', '192.0.2.10'], 'run-id')
    if fail_upload:
        with pytest.raises(OSError):
            transfer.upload_filesystem(*args)
        assert (target / '192.0.2.1-old.cfg').exists()
        assert not (target / source.name).exists()
    else:
        transfer.upload_filesystem(*args)
        transfer.upload_filesystem(*args)
        assert (target / source.name).read_text() == 'new'
        assert (target / '192.0.2.1-old.cfg').exists() == (mode == 'backup')
        assert sftp.renamed
    assert (target / '192.0.2.10-other.cfg').read_text() == 'another server'
    assert (target / 'notes.txt').read_text() == 'user file'
    assert not list(target.glob('.roxywi-*'))


def test_sftp_does_not_follow_remote_symlink():
    sftp = SimpleNamespace(lstat=lambda _name: SimpleNamespace(st_mode=stat.S_IFLNK))
    with pytest.raises(ValueError, match='symlink'):
        transfer._mkdirs(sftp, '/backups/configs')


def test_s3_access_denied_is_not_treated_as_a_missing_bucket(monkeypatch):
    config = SimpleNamespace(s3_server='https://s3.test', bucket='configs',
                             access_key='test-key', secret_key='test-secret')
    client = transfer.s3_client(config)
    with Stubber(client) as stubber:
        stubber.add_client_error('head_bucket', service_error_code='AccessDenied',
                                 http_status_code=403, expected_params={'Bucket': 'configs'})
        monkeypatch.setattr(transfer, 's3_client', lambda _config: client)
        with pytest.raises(ClientError):
            transfer.upload_s3(config, SimpleNamespace(hostname='source'), {})
        stubber.assert_no_pending_responses()
