"""Certbot adapter and verified, atomic HAProxy certificate deployment."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from app.modules.db import sql, service as service_sql
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi.exception import RoxywiPublicError
from app.modules.server.ssh import return_ssh_keys_path
from app.modules.server.ssh_connection import SshConnection


class CertificateError(RoxywiPublicError):
    pass


def storage_root():
    path = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'letsencrypt'
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def revision_root(le_id, revision):
    path = storage_root() / str(int(le_id)) / ('r' + str(int(revision)))
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def private_write(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix='.le-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def inspect_bundle(bundle, domains, allow_expired=False):
    certificates = x509.load_pem_x509_certificates(bundle['fullchain'].encode('ascii'))
    certificate = certificates[0]
    key = serialization.load_pem_private_key(bundle['key'].encode('ascii'), password=None)
    public = lambda value: value.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if public(certificate.public_key()) != public(key.public_key()):
        raise CertificateError('Certificate and private key do not match')
    actual = set(certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName))
    if actual != set(domains):
        raise CertificateError('Certificate domains do not match the requested domains')
    now = datetime.now(timezone.utc)
    if certificate.not_valid_before_utc > now or (not allow_expired and certificate.not_valid_after_utc <= now):
        raise CertificateError('Certificate is expired or not yet valid')
    return certificate.not_valid_after_utc.replace(tzinfo=None), certificate.fingerprint(hashes.SHA256()).hex()


def remote(server, data):
    settings = return_ssh_keys_path(server.ip)
    helper = Path(__file__).resolve().parents[3] / 'scripts' / 'letsencrypt_remote.py'
    argv = ([] if settings['user'] == 'root' else ['sudo', '-n']) + ['python3', '-c', helper.read_text(encoding='utf-8')]
    with SshConnection(server.ip, settings, banner_timeout=30) as connection:
        stdin, stdout, stderr = connection.ssh.exec_command(shlex.join(argv), timeout=2700)
        stdin.write(json.dumps(data))
        stdin.flush()
        stdin.channel.shutdown_write()
        output = stdout.read(1024 * 1024)
        stderr.read(65536)
        status = stdout.channel.recv_exit_status()
        try:
            result = json.loads(output)
        except (ValueError, UnicodeDecodeError):
            raise CertificateError('SSH certificate helper failed; check Python 3 and noninteractive sudo access') from None
        if status or result.get('error'):
            raise CertificateError(result.get('error') or 'Remote certificate operation failed')
        return result


def dns_command(data, root, le_id, test=False):
    provider = data['type']
    credentials = root / 'credentials.ini'
    environment = {key: value for key, value in os.environ.items() if not key.startswith('AWS_')}
    if provider == 'route53':
        content = '[default]\naws_access_key_id = ' + data['api_key'] + '\naws_secret_access_key = ' + data['api_token'] + '\n'
        environment['AWS_SHARED_CREDENTIALS_FILE'] = str(credentials.resolve())
        environment['AWS_CONFIG_FILE'] = str((root / 'aws-config').resolve())
        environment['AWS_EC2_METADATA_DISABLED'] = 'true'
        plugin = ['--dns-route53']
    else:
        field = {'cloudflare': 'api_token', 'digitalocean': 'token', 'linode': 'key'}[provider]
        content = f'dns_{provider}_{field} = {data["api_token"]}\n'
        if provider == 'linode':
            content += 'dns_linode_version = 4\n'
        plugin = [f'--dns-{provider}', f'--dns-{provider}-credentials', str(credentials.resolve()),
                  f'--dns-{provider}-propagation-seconds', '60']
    private_write(credentials, content)
    args = [sys.executable, '-c', 'from certbot.main import main; raise SystemExit(main())',
            'certonly', '--non-interactive', '--agree-tos',
            '--keep-until-expiring', '--cert-name', f'roxywi-{int(le_id)}',
            '--config-dir', str(root / 'config'), '--work-dir', str(root / 'work'),
            '--logs-dir', str(root / 'logs'), *plugin]
    args += ['--email', data['email']] if data.get('email') else ['--register-unsafely-without-email']
    for domain in data['domains']:
        args.extend(['-d', domain])
    if test:
        args.append('--dry-run')
    return args, environment


def obtain(data, state, server, test=False):
    root = revision_root(state.le_id, state.revision)
    bundle_path = root / 'bundle.json'
    if not test and bundle_path.exists():
        bundle = json.loads(bundle_path.read_text())
        try:
            expires, _ = inspect_bundle(bundle, data['domains'])
        except (ValueError, CertificateError):
            pass  # Invalid/expired stored material must be replaced by ACME.
        else:
            # Renew short-lived certificates too; Certbot makes the final due decision.
            if expires > datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30):
                return bundle
    if data['type'] == 'standalone':
        bundle = remote(server, dict(operation='issue', domains=data['domains'], email=data['email'],
                                     le_id=state.le_id, revision=state.revision, test=test,
                                     proxy=sql.get_setting('proxy', group_id=server.group_id)))
    else:
        args, environment = dns_command(data, root, state.le_id, test)
        proxy = sql.get_setting('proxy', group_id=server.group_id)
        if proxy and proxy != 'None':
            environment.update(http_proxy=proxy, https_proxy=proxy, HTTP_PROXY=proxy, HTTPS_PROXY=proxy)
        result = subprocess.run(args, env=environment, capture_output=True, timeout=1200)
        if result.returncode:
            raise CertificateError('DNS ACME challenge failed; check provider credentials, DNS propagation and Certbot plugins')
        if test:
            return None
        live = root / 'config' / 'live' / f'roxywi-{state.le_id}'
        bundle = {'fullchain': (live / 'fullchain.pem').read_text(), 'key': (live / 'privkey.pem').read_text()}
    if test:
        return None
    inspect_bundle(bundle, data['domains'])
    private_write(bundle_path, json.dumps(bundle))
    return bundle


def deploy(server, bundle, pem_name):
    return remote(server, {
        'operation': 'deploy', 'pem': bundle['fullchain'].rstrip() + '\n' + bundle['key'].rstrip() + '\n',
        'pem_name': pem_name, 'cert_dir': sql.get_setting('cert_path', group_id=server.group_id),
        'config_path': sql.get_setting('haproxy_config_path', group_id=server.group_id),
        'docker': service_sql.select_service_setting(server.server_id, 'haproxy', 'dockerized') == '1',
        'container': sql.get_setting('haproxy_container_name', group_id=server.group_id),
    })
