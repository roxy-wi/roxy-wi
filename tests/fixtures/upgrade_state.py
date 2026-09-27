"""Synthetic state shared by the native-release upgrade and container restore drills.

Run from the application checkout with its Python environment. Never use against
an existing installation: seeding requires ROXYWI_REHEARSAL=1 and an empty inventory.
No external services or ACME requests are made by this fixture.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys


def run(action, legacy_cert_root=None):
    sys.path.insert(0, str(Path.cwd()))
    from app.modules.db.db_model import (
        Backup, ConfigVersion, Cred, InstallationTasks, LetsEncrypt, S3Backup,
        Server, User, close_database_connection,
    )
    from app.modules.roxy_wi_tools import GetConfigVar
    from app.modules.server.ssh import crypt_password, decrypt_password
    config = GetConfigVar()
    root = Path(config.get_config_var('main', 'lib_path'))
    manifest_path = root / 'rehearsal-manifest.json'
    try:
        if action == 'seed':
            if os.environ.get('ROXYWI_REHEARSAL') != '1' or Server.select().exists() or manifest_path.exists():
                raise RuntimeError('Seeding requires an explicitly disposable, empty installation')
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.x509.oid import NameOID
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            private_key = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption()).decode()
            cred = Cred.create(name='rehearsal-ssh', username='fixture', key_enabled=0,
                               password=crypt_password('rehearsal-ssh-password').decode(),
                               passphrase=crypt_password('rehearsal-key-passphrase').decode(),
                               private_key=crypt_password(private_key).decode(), group_id=1)
            server = Server.create(hostname='rehearsal', ip='192.0.2.10', group_id='1',
                                   enabled=0, haproxy=1, cred_id=cred.id)
            Backup.create(server_id=str(server.server_id), rserver='192.0.2.20',
                          rpath='/srv/rehearsal', type='backup', time='weekly', cred_id=cred.id)
            S3Backup.create(server_id=str(server.server_id), s3_server='https://s3.example.invalid',
                            bucket='rehearsal', access_key='rehearsal-s3-access',
                            secret_key='rehearsal-s3-secret', time='daily')
            le = LetsEncrypt.create(server_id=server.server_id, domains="['rehearsal.example.org']",
                                    email='operator@example.org', type='cloudflare',
                                    api_key='', api_token='rehearsal-dns-token', description='Restore drill')
            InstallationTasks.create(service_name='rehearsal-history', status='completed',
                                     group_id=1, user_id=1, server_ids=[server.server_id])
            files = {}
            for service in ('haproxy', 'nginx', 'apache', 'keepalived'):
                path = Path(config.get_config_var('configs', service + '_save_configs_dir')) / '192.0.2.10-rehearsal.cfg'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f'# {service} configuration retained by restore drill\n', encoding='utf-8')
                ConfigVersion.create(server_id=server.server_id, user_id=1, service=service,
                                     local_path=str(path), remote_path=f'/etc/{service}/rehearsal.conf',
                                     diff='+ rehearsal', message='Restore drill')
                files[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
            account = root / 'keys' / 'rehearsal-private-key'
            account.parent.mkdir(parents=True, exist_ok=True)
            account.write_text(private_key, encoding='ascii')
            account.chmod(0o600)
            files[str(account.relative_to(root))] = hashlib.sha256(account.read_bytes()).hexdigest()
            subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'rehearsal.example.org')])
            now = datetime.now(timezone.utc)
            certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                           .public_key(key.public_key()).serial_number(x509.random_serial_number())
                           .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=90))
                           .add_extension(x509.SubjectAlternativeName([x509.DNSName('rehearsal.example.org')]), False)
                           .sign(key, hashes.SHA256()))
            bundle = dict(name='rehearsal.example.org', key=private_key,
                          fullchain=certificate.public_bytes(serialization.Encoding.PEM).decode())
            if legacy_cert_root:
                cert_root = Path(legacy_cert_root)
                live = cert_root / 'live' / bundle['name']
                live.mkdir(parents=True, mode=0o700)
                for filename, content in (('fullchain.pem', bundle['fullchain']), ('privkey.pem', private_key)):
                    (live / filename).write_text(content, encoding='ascii')
                    (live / filename).chmod(0o600)
                (cert_root / 'renewal').mkdir(exist_ok=True)
                (cert_root / 'renewal' / (bundle['name'] + '.conf')).write_text('# Synthetic Certbot lineage\n')
            else:
                from app.modules.db.db_model import BackupSchedule, LetsEncryptState
                from app.modules.operations.queue import serialize_operation_payload
                for kind, model in (('fs', Backup), ('s3', S3Backup)):
                    BackupSchedule.create(kind=kind, backup_id=model.get().id, timezone='UTC',
                                          next_run_at=datetime(2050, 1, 1))
                LetsEncryptState.create(le_id=le.id, pem_name='rehearsal.example.org.pem',
                                        credentials=serialize_operation_payload({'api_key': '', 'api_token': le.api_token}),
                                        next_run_at=datetime(2050, 1, 1))
                le.api_key = le.api_token = ''
                le.save()
                target = root / 'letsencrypt' / str(le.id) / 'r1'
                target.mkdir(parents=True, mode=0o700)
                (target / 'bundle.json').write_text(json.dumps(bundle), encoding='utf-8')
                (target / 'bundle.json').chmod(0o600)
            manifest = dict(files=files, credential=cred.id, le=le.id,
                            certificate=certificate.fingerprint(hashes.SHA256()).hex(),
                            admin_hash=User.get_by_id(1).password)
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            manifest_path.chmod(0o600)
        else:
            manifest = json.loads(manifest_path.read_text())
            assert User.get_by_id(1).password == manifest['admin_hash'], 'Admin account was reset'
            cred = Cred.get_by_id(manifest['credential'])
            assert decrypt_password(cred.password) == 'rehearsal-ssh-password'
            assert decrypt_password(cred.passphrase) == 'rehearsal-key-passphrase'
            assert decrypt_password(cred.private_key) == (root / 'keys/rehearsal-private-key').read_text()
            assert Server.get(Server.hostname == 'rehearsal').cred_id == cred.id
            assert Backup.get().time == 'weekly' and Backup.get().type == 'backup'
            assert S3Backup.get().secret_key == 'rehearsal-s3-secret'
            assert InstallationTasks.get(InstallationTasks.service_name == 'rehearsal-history').status == 'completed'
            assert ConfigVersion.select().count() == 4
            for name, digest in manifest['files'].items():
                assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
            for version in ConfigVersion.select():
                assert Path(version.local_path).is_file(), 'Persisted absolute config path is broken'
            if action != 'verify-legacy':
                from app.modules.db.db_model import BackupSchedule, LetsEncryptState
                from app.modules.operations.queue import deserialize_operation_payload
                state = LetsEncryptState.get(le_id=manifest['le'])
                assert deserialize_operation_payload(state.credentials)['api_token'] == 'rehearsal-dns-token'
                assert LetsEncrypt.get_by_id(manifest['le']).api_token == ''
                schedules = list(BackupSchedule.select())
                assert len(schedules) == 2
                pending = action == 'verify-migrated'
                assert all(schedule.legacy_pending == pending for schedule in schedules)
                assert state.legacy_pending == pending
                if not pending:
                    from app.modules.service.le.le_certbot import inspect_bundle
                    bundle_file = root / 'letsencrypt' / str(state.le_id) / 'r1/bundle.json'
                    bundle = json.loads(bundle_file.read_text())
                    assert inspect_bundle(bundle, ['rehearsal.example.org'])[1] == manifest['certificate']
                    assert bundle_file.stat().st_mode & 0o077 == 0, 'Private certificate permissions changed'
                if action == 'quiesce':
                    BackupSchedule.update(next_run_at=datetime(2050, 1, 1)).execute()
                    LetsEncryptState.update(next_run_at=datetime(2050, 1, 1)).execute()
        print(f'{action}: users, encrypted credentials, configuration history, backups and LE state OK')
    finally:
        close_database_connection()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('seed', 'verify-legacy', 'verify-migrated', 'verify-restored', 'quiesce'))
    parser.add_argument('--legacy-cert-root')
    args = parser.parse_args()
    run(args.action, args.legacy_cert_root)
