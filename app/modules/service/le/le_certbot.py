"""Certbot adapter and verified, atomic HAProxy certificate deployment."""

import json
import os
from pathlib import Path
import subprocess
import sys

from app.modules.db import sql
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.service.certificates import (
    CertificateError, private_write, inspect_bundle, remote, deployment_settings, deploy,
)
from app.modules.service.le.le_lock import file_lock
from app.scripts.certificate_remote import copy_accounts, diagnose_acme


def storage_root():
    path = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'letsencrypt'
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def revision_root(le_id, revision):
    path = storage_root() / str(int(le_id)) / ('r' + str(int(revision)))
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


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
                  f'--dns-{provider}-propagation-seconds', str(data.get('propagation_seconds', 60))]
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
        if bundle.get('imported'):
            inspect_bundle(bundle, data['domains'], allow_expired=True)
            from app.modules.service.le.le_legacy_renewal import due
            proxy = sql.get_setting('proxy', group_id=server.group_id)
            proxies = {'http': proxy, 'https': proxy} if proxy and proxy != 'None' else None
            if not due(bundle, root, proxies):
                return bundle
    # Always let Certbot check ARI and its lifetime-dependent renewal window.
    # A cached bundle is a deployment artifact, not a renewal decision.
    if data['type'] == 'standalone':
        bundle = remote(server, dict(operation='issue', domains=data['domains'], email=data['email'],
                                     le_id=state.le_id, revision=state.revision, test=test, group_id=int(server.group_id),
                                     proxy=sql.get_setting('proxy', group_id=server.group_id)))
    else:
        args, environment = dns_command(data, root, state.le_id, test)
        proxy = sql.get_setting('proxy', group_id=server.group_id)
        if proxy and proxy != 'None':
            environment.update(http_proxy=proxy, https_proxy=proxy, HTTP_PROXY=proxy, HTTPS_PROXY=proxy)
        accounts = storage_root() / 'accounts' / str(int(server.group_id))
        with file_lock(storage_root() / f'accounts-{int(server.group_id)}.lock'):
            copy_accounts(accounts, root / 'config' / 'accounts')
            try:
                result = subprocess.run(args, env=environment, capture_output=True, timeout=1200)
            finally:
                copy_accounts(root / 'config' / 'accounts', accounts)
        if result.returncode:
            error = diagnose_acme(result.stderr + result.stdout)
            raise CertificateError(str(error), error.code, error.retry_at)
        if test:
            return None
        live = root / 'config' / 'live' / f'roxywi-{state.le_id}'
        bundle = {'fullchain': (live / 'fullchain.pem').read_text(), 'key': (live / 'privkey.pem').read_text()}
    if test:
        return None
    inspect_bundle(bundle, data['domains'])
    private_write(bundle_path, json.dumps(bundle))
    return bundle
