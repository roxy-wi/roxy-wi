"""Backup transports. No package installation, cron or shell interpolation."""

import errno
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from urllib.parse import urlsplit

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError
from werkzeug.utils import secure_filename

from app.modules.db.db_model import Server
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.server.ssh import return_ssh_keys_path
from app.modules.server.ssh_connection import SshConnection


DIRECTORIES = {'haproxy': 'hap_config', 'keepalived': 'kp_config',
               'nginx': 'nginx_config', 'apache': 'apache_config'}


def owns_file(name, address, addresses=()):
    prefixes = {address + '-', secure_filename(address) + '-'}
    if not any(name.startswith(prefix) for prefix in prefixes):
        return False
    # DNS names may share a prefix, unlike a delimited IPv4 address.
    for other in addresses:
        if other == address:
            continue
        for prefix in (other + '-', secure_filename(other) + '-'):
            if any(prefix.startswith(ours) for ours in prefixes) and name.startswith(prefix):
                return False
    return name.endswith(('.cfg', '.conf'))


def source_files(server):
    config = GetConfigVar()
    addresses = [row.ip for row in Server.select(Server.ip)]
    result = {}
    for service, folder in DIRECTORIES.items():
        directory = Path(config.get_config_var('configs', f'{service}_save_configs_dir'))
        if not directory.is_dir():
            continue
        files = []
        for path in sorted(directory.iterdir()):
            if owns_file(path.name, server.ip, addresses):
                if path.is_symlink() or not path.is_file():
                    raise ValueError('Backup source must be a regular configuration file')
                files.append(path)
        result[folder] = files
    if not any(result.values()):
        raise ValueError('No saved configurations found; check the shared configuration volume')
    return result, addresses


def endpoint_url(value):
    value = str(value).strip()
    if '://' not in value:
        value = 'https://' + value
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/')):
        raise ValueError('S3 endpoint must be an HTTP(S) origin without credentials or a path')
    return value.rstrip('/')


def s3_client(config):
    return boto3.client(
        's3', endpoint_url=endpoint_url(config.s3_server),
        aws_access_key_id=config.access_key, aws_secret_access_key=config.secret_key,
        region_name=os.environ.get('ROXYWI_BACKUP_S3_REGION', 'us-east-1'),
        config=Config(connect_timeout=10, read_timeout=60,
                      retries={'mode': 'standard', 'total_max_attempts': 3},
                      s3={'addressing_style': 'path'}),
    )


def _missing(error):
    return str(error.response.get('Error', {}).get('Code')) in ('404', 'NoSuchBucket', 'NoSuchKey', 'NotFound')


def _digest(path, algorithm='sha256'):
    digest = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def upload_s3(config, server, files):
    client = s3_client(config)
    try:
        try:
            client.head_bucket(Bucket=config.bucket)
        except ClientError as error:
            if not _missing(error):
                raise
            args = {'Bucket': config.bucket}
            region = client.meta.region_name
            if region != 'us-east-1':
                args['CreateBucketConfiguration'] = {'LocationConstraint': region}
            try:
                client.create_bucket(**args)
            except ClientError as creation_error:
                if creation_error.response['Error']['Code'] != 'BucketAlreadyOwnedByYou':
                    raise
        transfer = TransferConfig(max_concurrency=1, use_threads=False)
        for folder, paths in files.items():
            for path in paths:
                # Preserve the original S3 namespace, while selecting the actual
                # saved files by server address (not its display name).
                key = f'{server.hostname}/{folder}/{path.name}'
                digest = _digest(path)
                try:
                    remote = client.head_object(Bucket=config.bucket, Key=key)
                except ClientError as error:
                    if not _missing(error):
                        raise
                else:
                    if remote.get('Metadata', {}).get('sha256') == digest:
                        continue
                client.upload_file(str(path), config.bucket, key,
                                   ExtraArgs={'Metadata': {'sha256': digest}}, Config=transfer)
    finally:
        client.close()


def _mkdirs(sftp, path):
    current = '/'
    for component in PurePosixPath(path).parts[1:]:
        current = str(PurePosixPath(current) / component)
        try:
            attributes = sftp.lstat(current)
        except OSError as error:
            if error.errno != errno.ENOENT:
                raise
            try:
                sftp.mkdir(current, mode=0o700)
            except OSError:
                # Another backup may have created the common parent directory.
                if not stat.S_ISDIR(sftp.lstat(current).st_mode):
                    raise
        else:
            if not stat.S_ISDIR(attributes.st_mode):
                raise ValueError('Backup destination contains a non-directory or symlink')


def upload_filesystem(config, server, files, addresses, run_key):
    root = PurePosixPath(config.rpath)
    if not root.is_absolute() or '..' in root.parts:
        raise ValueError('Backup destination must be an absolute path without parent traversal')
    settings = return_ssh_keys_path(server.ip, config.cred_id)
    # The destination is an independent backup host. The legacy transport used
    # its standard SSH port, not the managed source server's port.
    settings['port'] = 22
    with SshConnection(config.rserver, settings, banner_timeout=30) as connection:
        with connection.ssh.open_sftp() as sftp:
            sftp.get_channel().settimeout(60)
            for folder, paths in files.items():
                target = str(root / 'roxy-wi-configs-backup' / 'configs' / folder)
                _mkdirs(sftp, target)
                for path in paths:
                    destination = f'{target}/{path.name}'
                    temporary = f'{target}/.roxywi-{run_key}-{path.name}'
                    try:
                        sftp.put(str(path), temporary)
                        sftp.chmod(temporary, 0o600)
                        sftp.posix_rename(temporary, destination)
                    except Exception:
                        try:
                            sftp.remove(temporary)
                        except OSError as cleanup_error:
                            if cleanup_error.errno != errno.ENOENT:
                                raise RuntimeError('Backup failed and temporary remote file cleanup failed') from None
                        raise
                if config.type == 'synchronization':
                    retained = {path.name for path in paths}
                    for entry in sftp.listdir_attr(target):
                        if (entry.filename not in retained and stat.S_ISREG(entry.st_mode)
                                and owns_file(entry.filename, server.ip, addresses)):
                            sftp.remove(f'{target}/{entry.filename}')


def transfer_backup(kind, config, run_key):
    server = Server.get_by_id(int(config.server_id))
    selected, addresses = source_files(server)
    # A retry may repeat successful uploads, but names stay stable and each
    # object/file replacement is atomic. Freeze local files before network I/O.
    with tempfile.TemporaryDirectory(prefix='roxywi-backup-') as temporary:
        snapshot = {}
        for folder, paths in selected.items():
            directory = Path(temporary) / folder
            directory.mkdir()
            snapshot[folder] = []
            for path in paths:
                target = directory / path.name
                descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
                with os.fdopen(descriptor, 'rb') as source, target.open('xb') as dest:
                    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                        raise ValueError('Backup source is not a regular file')
                    shutil.copyfileobj(source, dest)
                snapshot[folder].append(target)
        if kind == 's3':
            upload_s3(config, server, snapshot)
        else:
            upload_filesystem(config, server, snapshot, addresses, run_key)
