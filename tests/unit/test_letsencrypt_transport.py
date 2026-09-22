import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.service.le import le_certbot as certbot
from app.scripts import letsencrypt_remote as remote


def test_ssh_transport_loads_remote_helper(monkeypatch):
    settings = {'user': 'root'}
    monkeypatch.setattr(certbot, 'return_ssh_keys_path', lambda ip: settings)
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(certbot, 'SshConnection', lambda *args, **kwargs: connection)
    stdin, stdout, stderr = MagicMock(), MagicMock(), MagicMock()
    stdout.read.return_value = b'{"tested": true}'
    stdout.channel.recv_exit_status.return_value = 0
    connection.ssh.exec_command.return_value = stdin, stdout, stderr
    payload = {'operation': 'issue', 'le_id': 1, 'test': True}

    assert certbot.remote(SimpleNamespace(ip='192.0.2.1'), payload) == {'tested': True}

    command = connection.ssh.exec_command.call_args.args[0]
    assert shlex.split(command) == ['python3', '-c', Path(remote.__file__).read_text(encoding='utf-8')]
    stdin.write.assert_called_once_with(json.dumps(payload))
    stdin.channel.shutdown_write.assert_called_once_with()


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    root = tmp_path / 'runtime'
    root.mkdir()
    monkeypatch.setattr(remote, 'ROOT', root)
    monkeypatch.setattr(remote.os, 'chown', lambda *args: None, raising=False)
    monkeypatch.setattr(remote, 'runtime_pid', lambda data: '123')
    monkeypatch.setattr(remote, 'runtime_request', lambda *args: 'Status: Used')
    monkeypatch.setattr(remote, 'verify_runtime', lambda *args, **kwargs: 'loaded')
    target = tmp_path / 'certificates'
    target.mkdir()
    (target / 'example.pem').write_text('OLD CERTIFICATE')
    data = {'cert_dir': str(target), 'pem_name': 'example.pem', 'pem': 'NEW CERTIFICATE',
            'docker': False, 'config_path': '/etc/haproxy/haproxy.cfg'}
    return target, root, data


def test_atomic_deploy_is_repeatable_without_unnecessary_reload(deployment, monkeypatch):
    target, root, data = deployment
    commands = []
    monkeypatch.setattr(remote, 'command', lambda args, stage, **kw: commands.append(args) or b'')
    remote.deploy(data)
    assert (target / 'example.pem').read_text() == 'NEW CERTIFICATE'
    assert commands[-1] == ['systemctl', 'reload', 'haproxy']
    remote.deploy(data)
    assert commands.count(['systemctl', 'reload', 'haproxy']) == 1
    assert not list(root.rglob('pending.json'))


@pytest.mark.parametrize('fail_stage', ['HAProxy configuration validation', 'HAProxy reload'])
def test_failed_deployment_restores_previous_file_and_runtime(deployment, monkeypatch, fail_stage):
    target, root, data = deployment
    stages = []
    def command(args, stage, **kw):
        stages.append(stage)
        if stage == fail_stage:
            raise RuntimeError('Failed validation')
        return b''
    monkeypatch.setattr(remote, 'command', command)
    with pytest.raises(RuntimeError):
        remote.deploy(data)
    assert (target / 'example.pem').read_text() == 'OLD CERTIFICATE'
    assert stages[-2:] == ['Rollback configuration validation', 'Rollback HAProxy reload']
    assert not list(root.rglob('pending.json'))


def test_killed_worker_is_recovered_before_next_deployment(deployment, monkeypatch):
    target, root, data = deployment
    def killed(*args, **kwargs):
        raise SystemExit('simulate process death')
    monkeypatch.setattr(remote, 'command', killed)
    with pytest.raises(SystemExit):
        remote.deploy(data)
    assert list(root.rglob('pending.json'))
    assert (target / 'example.pem').read_text() == 'NEW CERTIFICATE'
    stages = []
    def recovered(args, stage, **kwargs):
        stages.append(stage)
        if stage == 'Rollback configuration validation':
            assert (target / 'example.pem').read_text() == 'OLD CERTIFICATE'
        return b''
    monkeypatch.setattr(remote, 'command', recovered)
    remote.deploy(data)
    assert stages[:2] == ['Rollback configuration validation', 'Rollback HAProxy reload']
    assert not list(root.rglob('pending.json'))


def test_docker_target_maps_directory_mount_and_uses_graceful_signal(tmp_path, monkeypatch):
    bind = tmp_path / 'bind'
    monkeypatch.setattr(remote, 'command', lambda *args, **kwargs: json.dumps([
        {'Source': str(bind), 'Destination': '/certificates'}
    ]).encode())
    # Pure local path behavior is platform dependent; use a native absolute
    # container-path stand-in so mapping is tested on both Windows and Linux.
    data = {'docker': True, 'container': 'haproxy', 'cert_dir': str(tmp_path / 'container'),
            'config_path': '/usr/local/etc/haproxy/haproxy.cfg'}
    def command(args, *a, **kw):
        if '/proc/1/cmdline' in args:
            return b'/usr/local/sbin/haproxy\x00-W\x00-db\x00'
        return json.dumps([{'Source': str(bind), 'Destination': data['cert_dir']}]).encode()
    monkeypatch.setattr(remote, 'command', command)
    assert remote.certificate_directory(data) == bind
    check, reload = remote.service_commands(data)
    assert check[:4] == ['docker', 'exec', 'haproxy', 'haproxy']
    assert reload == ['docker', 'kill', '--signal=USR2', 'haproxy']
    monkeypatch.setattr(remote, 'command', lambda *args, **kwargs: b'[]')
    with pytest.raises(RuntimeError, match='persistent directory mount'):
        remote.certificate_directory(data)


def test_docker_without_master_worker_mode_is_not_signalled(monkeypatch):
    monkeypatch.setattr(remote, 'command', lambda *args, **kwargs: b'haproxy\x00-db\x00')
    with pytest.raises(RuntimeError, match='PID 1'):
        remote.service_commands({'docker': True, 'container': 'haproxy', 'config_path': '/etc/haproxy/haproxy.cfg'})


@pytest.mark.parametrize('provider', ['cloudflare', 'digitalocean', 'linode', 'route53'])
def test_dns_provider_arguments_and_secret_files(tmp_path, monkeypatch, provider):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'ambient-credentials-must-not-leak')
    data = {'type': provider, 'api_key': 'access', 'api_token': 'super-secret',
            'email': None, 'domains': ['example.com', '*.example.com']}
    args, env = certbot.dns_command(data, tmp_path, 12)
    assert '--non-interactive' in args and '--agree-tos' in args
    assert '--register-unsafely-without-email' in args
    assert 'super-secret' not in ' '.join(args)
    assert 'AWS_ACCESS_KEY_ID' not in env
    assert (tmp_path / 'credentials.ini').read_text().count('super-secret') == 1
    if provider == 'route53':
        assert '--dns-route53-credentials' not in args
        assert '--dns-route53-propagation-seconds' not in args
        assert Path(env['AWS_SHARED_CREDENTIALS_FILE']) == tmp_path / 'credentials.ini'
    else:
        assert f'--dns-{provider}-credentials' in args


def test_staging_flag_and_email_are_explicit(tmp_path):
    data = {'type': 'cloudflare', 'api_token': 'token', 'domains': ['example.com'], 'email': 'admin@example.com'}
    args, _ = certbot.dns_command(data, tmp_path, 1, test=True)
    assert '--dry-run' in args
    assert args[args.index('--email') + 1] == 'admin@example.com'


def test_legacy_cron_cleanup_preserves_unrelated_jobs():
    original = ("# keep this\n0 1 * * * /usr/bin/backup\n"
                "#Ansible: Let's encrypt renew script\n@monthly /etc/haproxy/scripts/renew_letsencrypt.sh\n"
                "#Ansible: Roxy-WI certbot certificate renew\n0 0,12 * * * root broken-job\n"
                "#Ansible: Roxy-WI le certificate example.com 192.0.2.1\n@monthly rsync certificate\n"
                "#Ansible: other certificate job\n0 1 * * * certbot renew\n")
    result, removed = remote.remove_legacy_entries(original)
    assert removed == 3
    assert result == ("# keep this\n0 1 * * * /usr/bin/backup\n"
                      "#Ansible: other certificate job\n0 1 * * * certbot renew\n")
    assert remote.remove_legacy_entries(result) == (result, 0)


def test_malformed_cron_marker_does_not_remove_arbitrary_lines():
    with pytest.raises(RuntimeError):
        remote.remove_legacy_entries("#Ansible: Let's encrypt renew script\nunrelated text\n")


def test_cutover_refuses_active_timer_and_archives_only_owned_lineages(tmp_path, monkeypatch):
    root, saved = tmp_path / 'legacy', tmp_path / 'saved'
    (root / 'renewal').mkdir(parents=True)
    managed = root / 'renewal/example.com.conf'
    other = root / 'renewal/unrelated.conf'
    managed.write_text('managed renewal')
    other.write_text('unrelated renewal')
    monkeypatch.setattr(remote, 'LEGACY', root)
    monkeypatch.setattr(remote, 'LEGACY_BACKUP', saved)
    monkeypatch.setattr(remote.subprocess, 'run', lambda args, **kw:
                        SimpleNamespace(returncode=0 if args[-1] == 'certbot.timer' else 3))
    with pytest.raises(RuntimeError, match='Certbot timers'):
        remote.legacy_disable({'names': ['example.com']})
    assert managed.exists()
    monkeypatch.setattr(remote.subprocess, 'run', lambda *args, **kw: SimpleNamespace(returncode=3))
    crontab = ["#Ansible: Let's encrypt renew script\n@monthly old-script\n0 1 * * * other-job\n"]
    monkeypatch.setattr(remote, 'read_crontab', lambda: crontab[0])
    def command(args, *a, **kw):
        if args[0] == 'crontab':
            crontab[0] = kw['input'].decode()
        return b''
    monkeypatch.setattr(remote, 'command', command)
    assert remote.legacy_disable({'names': ['example.com']})['removed'] == 1
    assert not managed.exists() and other.exists()
    assert list(saved.glob('example.com-*.conf'))[0].read_text() == 'managed renewal'
    assert crontab[0] == '0 1 * * * other-job\n'
    assert remote.legacy_disable({'names': ['example.com']})['removed'] == 0


def test_delete_only_managed_state_and_preserve_deployed_pem(deployment):
    target, root, _ = deployment
    managed = root / '12'
    managed.mkdir()
    (managed / 'key').write_text('private')
    remote.delete({'le_id': 12})
    assert not managed.exists()
    assert (target / 'example.pem').exists()
    with pytest.raises(ValueError):
        remote.delete({'le_id': -1})


@pytest.mark.skipif(os.name == 'nt', reason='Certbot dependencies are installed on POSIX control nodes')
def test_installed_certbot_entrypoint_discovers_all_dns_plugins(tmp_path):
    result = subprocess.run([
        sys.executable, '-c', 'from certbot.main import main; raise SystemExit(main())',
        'plugins', '--non-interactive', '--authenticators',
        '--config-dir', str(tmp_path / 'config'), '--work-dir', str(tmp_path / 'work'),
        '--logs-dir', str(tmp_path / 'logs'),
    ], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    for name in ('dns-cloudflare', 'dns-digitalocean', 'dns-linode', 'dns-route53'):
        assert name in result.stdout


def test_transaction_preserves_previous_pem_until_global_commit(deployment, monkeypatch):
    target, root, data = deployment
    monkeypatch.setattr(remote, 'command', lambda *args, **kwargs: b'')
    data['transaction'] = 'operation-1'
    remote.deploy(data)
    assert (target / 'example.pem').read_text() == 'NEW CERTIFICATE'
    assert list(root.rglob('pending.json'))
    remote.deploy(data)  # retry after a lost SSH acknowledgement
    remote.finish_deployment(dict(data, operation='rollback'))
    assert (target / 'example.pem').read_text() == 'OLD CERTIFICATE'
    assert not list(root.rglob('pending.json'))
    remote.deploy(dict(data, transaction='operation-2'))
    remote.finish_deployment(dict(data, transaction='operation-2', operation='commit'))
    remote.finish_deployment(dict(data, transaction='operation-2', operation='commit'))
    assert (target / 'example.pem').read_text() == 'NEW CERTIFICATE'
    assert not list(root.rglob('previous.pem'))


def test_pending_deployment_cannot_be_taken_over(deployment, monkeypatch):
    target, root, data = deployment
    monkeypatch.setattr(remote, 'command', lambda *args, **kwargs: b'')
    remote.deploy(dict(data, transaction='first'))
    with pytest.raises(RuntimeError, match='previous certificate deployment'):
        remote.deploy(dict(data, transaction='other', pem='UNRELATED'))
    assert (target / 'example.pem').read_text() == 'NEW CERTIFICATE'


@pytest.mark.parametrize('output,code', [
    ('DNS problem: NXDOMAIN token=private-token', 'dns_validation'),
    ('Invalid API token: private-token', 'dns_credentials'),
    ('CAA forbids issuance', 'caa_denied'),
    ('Timeout during connect', 'http_validation'),
    ('unknown error private-token', 'acme_failed'),
])
def test_acme_diagnostics_never_expose_raw_provider_output(output, code):
    error = remote.diagnose_acme(output)
    assert error.code == code
    assert 'private-token' not in str(error)


def test_acme_retry_after_is_preserved():
    error = remote.diagnose_acme('urn:ietf:params:acme:error:rateLimited; retry after 2099-09-20 12:30:00 UTC')
    assert error.code == 'rate_limited'
    assert error.retry_at == '2099-09-20T12:30:00+00:00'
    error = remote.diagnose_acme('HTTP 429\nRetry-After: 3600\nprivate-token')
    from datetime import datetime, timezone, timedelta
    assert datetime.fromisoformat(error.retry_at) > datetime.now(timezone.utc) + timedelta(minutes=59)
    assert 'private-token' not in str(error)


def test_runtime_verification_requires_new_worker_and_matching_fingerprint(monkeypatch):
    pem = '-----BEGIN CERTIFICATE-----\nYWJj\n-----END CERTIFICATE-----'
    fingerprint = hashlib.sha1(b'abc').hexdigest().upper()
    data = {'runtime_port': 1999, 'cert_dir': '/certificates', 'pem_name': 'example.pem'}
    pid = ['12']
    result = ['SHA1 FingerPrint: ' + fingerprint + '\nStatus: Used']
    monkeypatch.setattr(remote, 'runtime_request', lambda data, request:
                        'Pid: ' + pid[0] + '\n' if request == 'show info' else result[0])
    assert remote.verify_runtime(data, pem, previous_pid='11', timeout=0) == 'loaded'
    with pytest.raises(RuntimeError, match='not confirmed'):
        remote.verify_runtime(data, pem, previous_pid='12', timeout=0)
    result[0] = 'SHA1 FingerPrint: DEADBEEF'
    with pytest.raises(RuntimeError, match='not confirmed'):
        remote.verify_runtime(data, pem, previous_pid='11', timeout=0)
    result[0] = "Can't display the certificate: Not found"
    assert remote.verify_runtime(data, pem, previous_pid='11', timeout=0) == 'stored_unreferenced'
    with pytest.raises(RuntimeError, match='not confirmed'):
        remote.verify_runtime(data, pem, previous_pid='11', timeout=0, require_loaded=True)


def test_acme_account_reuse_keeps_one_account_per_ca_and_existing_identity(tmp_path):
    source, destination = tmp_path / 'canonical', tmp_path / 'revision'
    def account(root, name, secret):
        path = root / 'acme.example.test' / 'directory' / name
        path.mkdir(parents=True)
        (path / 'regr.json').write_text('{}')
        (path / 'private_key.json').write_text(secret)
        return path
    account(source, 'first', 'account-secret')
    account(source, 'second', 'unused-secret')
    remote.copy_accounts(source, destination)
    assert len(list(destination.rglob('regr.json'))) == 1
    assert next(destination.rglob('private_key.json')).read_text() == 'account-secret'
    existing = tmp_path / 'old-lineage'
    previous = account(existing, 'original', 'original-secret')
    remote.copy_accounts(source, existing)
    assert list(existing.rglob('regr.json')) == [previous / 'regr.json']


def test_cached_pem_does_not_bypass_certbot_renewal_check(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    monkeypatch.setenv('ROXYWI_LIB_PATH', str(tmp_path))
    root = certbot.revision_root(1, 1)
    (root / 'bundle.json').write_text(json.dumps({'fullchain': 'cached', 'key': 'cached'}))
    monkeypatch.setattr(certbot, 'inspect_bundle', lambda *args: (datetime.now() + timedelta(days=80), 'fingerprint'))
    monkeypatch.setattr(certbot.sql, 'get_setting', lambda *args, **kwargs: None)
    calls = []
    monkeypatch.setattr(certbot.subprocess, 'run', lambda args, **kwargs:
                        calls.append(args) or SimpleNamespace(returncode=1, stderr=b'NXDOMAIN', stdout=b''))
    with pytest.raises(certbot.CertificateError, match='DNS challenge'):
        certbot.obtain({'type': 'cloudflare', 'api_token': 'token', 'domains': ['example.com']},
                       SimpleNamespace(le_id=1, revision=1), SimpleNamespace(group_id='1'))
    assert len(calls) == 1


def test_preflight_caa_inheritance_and_wildcard_authorization(monkeypatch):
    import dns.resolver
    from app.modules.service.le import le_preflight
    def resolve(name, kind, **kwargs):
        if name == 'sub.example.com':
            raise dns.resolver.NoAnswer()
        return [SimpleNamespace(flags=0, tag=b'issue', value=b'letsencrypt.org'),
                SimpleNamespace(flags=0, tag=b'issuewild', value=b';')]
    monkeypatch.setattr(dns.resolver.Resolver, 'resolve', lambda self, *args, **kwargs: resolve(*args, **kwargs))
    assert 'passed' in le_preflight.check_dns('sub.example.com', False)
    with pytest.raises(certbot.CertificateError, match='CAA'):
        le_preflight.check_dns('*.sub.example.com', False)
