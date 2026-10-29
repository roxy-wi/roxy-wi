"""Shared certificate validation, SSH transport and HAProxy deployment."""
import json
import os
from pathlib import Path
import re
import shlex
import tempfile
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from app.modules.db import sql, service as service_sql
from app.modules.db.db_model import Server
from app.modules.config import candidate, haproxy_files,haproxy_discovery
from app.modules.config.path_tokens import encode_file_path
from app.modules.roxywi.exception import RoxywiPublicError, RoxywiResourceNotFound, RoxywiValidationError
from app.modules.server.ssh import return_ssh_keys_path
from app.modules.server.ssh_connection import SshConnection
from app.modules.common.execution_context import group_settings
from app.modules.service import haproxy_runtime, container_settings
from app.modules.connectors import containers


MAX_PEM_BYTES = 1024 * 1024
REMOTE_BOOTSTRAP = '''import sys
size = int(sys.stdin.buffer.readline(32), 16)
if not 0 < size <= 512 * 1024:
    raise ValueError('Invalid certificate helper frame size')
source = sys.stdin.buffer.read(size)
if len(source) != size:
    raise ValueError('Incomplete certificate helper frame')
exec(compile(source, 'roxywi-certificate-helper', 'exec'))
'''


def remote_source():
    """Ship the existing validator with the helper; managed hosts need no app install."""
    helper = Path(__file__).resolve().parents[2] / 'scripts' / 'certificate_remote.py'
    source = containers.embedded()
    from app.scripts import certificate_cluster_remote,certificate_passive
    for name, module in (('roxywi_config_candidate', candidate), ('roxywi_haproxy_runtime', haproxy_runtime),
                         ('roxywi_haproxy_discovery',haproxy_discovery),
                         ('roxywi_certificate_cluster',certificate_cluster_remote),('roxywi_certificate_passive',certificate_passive)):
        content = Path(module.__file__).read_text(encoding='utf-8')
        source += (f'module = types.ModuleType({name!r})\n'
                   'sys.modules[module.__name__] = module\n')
        if name == 'roxywi_haproxy_runtime':
            source += f'module.__source__ = {content!r}\n'
        source += f'exec(compile({content!r}, {name!r}, "exec"), module.__dict__)\n'
    return source + helper.read_text(encoding='utf-8')


def certificate_metadata(pem):
    certificate = x509.load_pem_x509_certificate(pem.encode('ascii'))
    try:
        names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        domains = names.get_values_for_type(x509.DNSName) + [str(ip) for ip in names.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        domains = [item.value for item in certificate.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)]
    return dict(domains=domains, not_after=certificate.not_valid_after_utc.isoformat(),
                not_before=certificate.not_valid_before_utc.isoformat(),
                fingerprint=certificate.fingerprint(hashes.SHA256()).hex(), fingerprint_algorithm='SHA-256',
                issuer=certificate.issuer.rfc4514_string(), serial=str(certificate.serial_number))


def inspect_pem(pem):
    if not isinstance(pem, str) or not pem or len(pem.encode('utf-8')) > MAX_PEM_BYTES:
        raise CertificateError('Invalid PEM size', 'invalid_pem')
    certificates = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', pem, re.S)
    keys = re.findall(r'-----BEGIN ((?:RSA |EC )?PRIVATE KEY)-----.*?-----END \1-----', pem, re.S)
    key = re.search(r'-----BEGIN ((?:RSA |EC )?PRIVATE KEY)-----.*?-----END \1-----', pem, re.S)
    if not certificates or len(keys) != 1:
        raise CertificateError('Provide a PEM certificate chain and one unencrypted private key', 'invalid_pem')
    bundle = {'fullchain': '\n'.join(certificates) + '\n', 'key': key.group(0) + '\n'}
    try:
        inspect_bundle(bundle)
        metadata = certificate_metadata(bundle['fullchain'])
    except CertificateError:
        raise
    except (ValueError, TypeError, UnicodeError):
        raise CertificateError('Invalid certificate or private key', 'invalid_pem') from None
    return bundle, metadata


def targets_for(server_id, group_id, *, cluster_id=None):
    server = Server.get_or_none((Server.server_id == server_id) & (Server.group_id == str(group_id)))
    if server is None:
        raise RoxywiResourceNotFound('Certificate server not found in this group')
    if cluster_id is not None:
        from app.modules.pacemaker import service
        checked = service.members(service.get_cluster(cluster_id, group_id))
        if server_id not in {member.server_id for member, _s in checked}:
            raise RoxywiValidationError('The certificate server must belong to the selected Pacemaker cluster')
        return [server, *[target for _member, target in checked if target.server_id != server_id]]
    children = list(Server.select().where(Server.master == server_id))
    if any(str(child.group_id) != str(group_id) for child in children):
        raise RoxywiValidationError('HA certificate targets must belong to the same group')
    return [server, *children]


def catalog(server, service='haproxy'):
    data = (deployment_settings(server, '', verify_startup=False) if service == 'haproxy' else
            dict(cert_dir=container_settings.certificate_directory(server, service), runtime=False))
    result = remote(server, dict(data, operation='catalog'))
    for item in result['certificates']:
        item['file_token'] = encode_file_path(item['path'])
        pem = item.pop('certificate', '')
        if pem:
            try:
                item['disk'] = certificate_metadata(pem)
            except (ValueError, UnicodeError):
                item['disk_status'] = 'invalid'
                item['can_update'] = False
        item.update(item.get('runtime') or item.get('disk') or {})
    return result


def certificate_file(server, service, path, *, revision=None):
    data = (deployment_settings(server, '', verify_startup=revision is not None) if service == 'haproxy' else
            dict(cert_dir=container_settings.certificate_directory(server, service), runtime=False))
    return remote(server, dict(data, operation='remove-file' if revision is not None else 'read-file',
                               path=path, revision=revision))


def store_uploaded_file(server_ip, name, content, *, service=None):
    """Use the shared privileged transport for uploads, including non-root SSH users."""
    server = Server.get(Server.ip == str(server_ip))
    directory = container_settings.certificate_directory(server, service) if service else sql.get_setting('cert_path', group_id=server.group_id)
    return remote(server, dict(operation='store', cert_dir=directory,
                               pem_name=name, pem=content))


class CertificateError(RoxywiPublicError):
    def __init__(self, message, code='certificate_failed', retry_at=None):
        super().__init__(message)
        self.code = code
        self.retry_at = datetime.fromisoformat(retry_at).astimezone(timezone.utc).replace(tzinfo=None) if retry_at else None


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


def inspect_bundle(bundle, domains=None, allow_expired=False):
    certificates = x509.load_pem_x509_certificates(bundle['fullchain'].encode('ascii'))
    certificate = certificates[0]
    key = serialization.load_pem_private_key(bundle['key'].encode('ascii'), password=None)
    public = lambda value: value.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if public(certificate.public_key()) != public(key.public_key()):
        raise CertificateError('Certificate and private key do not match', 'key_mismatch')
    actual = set(certificate_metadata(bundle['fullchain'])['domains'])
    if domains is not None and actual != set(domains):
        raise CertificateError('Certificate domains do not match the requested domains')
    now = datetime.now(timezone.utc)
    if certificate.not_valid_before_utc > now or (not allow_expired and certificate.not_valid_after_utc <= now):
        raise CertificateError('Certificate is expired or not yet valid', 'invalid_dates')
    return certificate.not_valid_after_utc.replace(tzinfo=None), certificate.fingerprint(hashes.SHA256()).hex()


def remote(server, data):
    settings = return_ssh_keys_path(server.ip)
    source = remote_source()
    size = len(source.encode('utf-8'))
    if size > 512 * 1024:
        raise CertificateError('Certificate helper exceeded its transport size limit')
    argv = ([] if settings['user'] == 'root' else ['sudo', '-n']) + ['python3', '-c', REMOTE_BOOTSTRAP]
    with SshConnection(server.ip, settings, banner_timeout=30) as connection:
        stdin, stdout, stderr = connection.ssh.exec_command(shlex.join(argv), timeout=2700)
        # The helper exceeds some systems' per-argument limit. Code and private
        # certificate data share a framed stdin stream; neither enters argv.
        stdin.write(format(size, 'x') + '\n' + source + json.dumps(data))
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
            raise CertificateError(result.get('error') or 'Remote certificate operation failed',
                                   result.get('code', 'remote_failed'), result.get('retry_at'))
        return result


def deployment_settings(server, pem_name, *, verify_startup=True):
    settings = {
        'pem_name': pem_name, 'cert_dir': container_settings.certificate_directory(server, 'haproxy'),
        'config_path': sql.get_setting('haproxy_config_path', group_id=server.group_id),
        'docker': service_sql.select_service_setting(server.server_id, 'haproxy', 'dockerized') == '1',
        'container': container_settings.name(server.server_id, 'haproxy'),
        'runtime_port': int(sql.get_setting('haproxy_sock_port', group_id=server.group_id)),
        'apply_mode': 'auto',
    }
    from app.modules.service.common import get_correct_service_name
    settings['service_unit']=get_correct_service_name('haproxy',server.server_id)
    settings['root']=sql.get_setting('haproxy_dir',group_id=server.group_id)
    settings.update(container_settings.context(server.server_id, 'haproxy'))
    if verify_startup:
        try:
            with group_settings(server.group_id):
                context = haproxy_files.configuration_context(server.ip, server.server_id, verify_startup=True)
        except ValueError:
            raise CertificateError('Cannot determine HAProxy configuration sources', 'configuration_unavailable') from None
        settings['validation'] = dict(service='haproxy', target=context['main'], candidate='', action='check',
                                     container=settings['container'] if settings['docker'] else '', **context)
    return settings


def deploy(server, bundle, pem_name, *, settings=None, transaction=None):
    data = settings or deployment_settings(server, pem_name)
    return remote(server, dict(data, operation='deploy', transaction=transaction,
                              pem=bundle['fullchain'].rstrip() + '\n' + bundle['key'].rstrip() + '\n'))


def cluster_deployment_settings(server,pem_name,proof):
    data=deployment_settings(server,pem_name,verify_startup=proof['mode']!='passive')
    data['cluster_proof']=proof
    if proof['mode']=='passive':
        data['apply_mode']='disk_stage'
        data['validation']=remote(server,dict(data,operation='passive-context'))
    return data


def passive_inspection(server,pem_name,proof,*,directory=None,destination=None,expected_digest=None):
    data=cluster_deployment_settings(server,pem_name,proof)
    if directory:data['update_directory']=directory
    if destination:data['destination']=destination
    if expected_digest:data['verify_passive_digest']=expected_digest
    result=remote(server,dict(data,operation='passive-inspect'))
    pem=result.pop('certificate','')
    if pem:result['certificate']=certificate_metadata(pem)
    return data,result
