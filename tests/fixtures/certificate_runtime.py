"""Real PEM files with a deterministic substitute for the external HAProxy socket."""
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import shlex

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.scripts import certificate_remote as remote


def make_pem(serial=1, domains=('example.test',)):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domains[0])])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(serial).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=60)).add_extension(
                x509.SubjectAlternativeName([x509.DNSName(domain) for domain in domains]), critical=False)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode() + key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()


class Runtime:
    def __init__(self, root, monkeypatch):
        self.root = root
        self.files, self.active, self.staged, self.calls = {}, {}, {}, []
        self.sources, self.unused = {}, set()
        self.fail_validation = False
        self.lose_commit = False
        self.unreachable = False
        self.pid = '123'
        self.level = 'admin'
        monkeypatch.setattr(remote, 'ROOT', root / 'journals')
        monkeypatch.setattr(remote, 'runtime_request', self.request)
        monkeypatch.setattr(remote, 'validate_configuration', self.validate)
        monkeypatch.setattr(remote.os, 'chown', lambda *args: None, raising=False)

    def add(self, name, pem):
        path = self.root / name / 'site.pem'
        path.parent.mkdir(parents=True)
        path.write_text(pem, encoding='ascii')
        self.files[name] = path
        self.active[str(path)] = pem
        self.sources[str(path.parent)] = [str(path)]
        listing = path.parent / 'certificates.list'
        listing.write_text(str(path) + '\n', encoding='utf-8')
        self.sources[str(listing)] = [str(path)]
        return self.settings(name)

    def settings(self, name):
        path = self.files[name]
        return dict(cert_dir=str(path.parent), pem_name=path.name, runtime_port=1999,
                    docker=False, apply_mode='runtime', config_path='/etc/haproxy/haproxy.cfg', fixture_host=name)

    def validate(self, data, *args, **kwargs):
        if self.fail_validation and not kwargs.get('rollback'):
            raise remote.CertificateFailure('validation_failed')

    def request(self, data, command):
        self.calls.append(command)
        if self.unreachable:
            raise OSError('private diagnostic')
        path = str(Path(data['cert_dir']) / data['pem_name'])

        def visible(value):
            return not any(
                Path(value) == file.parent or file.parent in Path(value).parents
                for name, file in self.files.items() if name != data.get('fixture_host'))
        if command == 'show info':
            return 'Pid: ' + self.pid + '\n'
        if command == 'show cli level':
            return self.level + '\n'
        if command == 'help':
            return 'set ssl cert\ncommit ssl cert\nabort ssl cert\nnew ssl cert\ndel ssl cert\nshow ssl crt-list\nadd ssl crt-list\ndel ssl crt-list'
        if command == 'show ssl crt-list':
            return '\n'.join(p for p in self.sources if visible(p)) + '\n\n'
        if command.startswith('show ssl crt-list '):
            source = shlex.split(command)[3]
            return '# ' + source + '\n' + '\n'.join(self.sources[source]) if source in self.sources else 'Unknown crt-list'
        if command.startswith(('add ssl crt-list ', 'del ssl crt-list ')):
            action, _, _, source, entry = shlex.split(command)
            if action == 'add':
                if entry not in self.active or not self.active[entry]:
                    return 'Certificate not found'
                self.sources[source].append(entry)
                self.unused.discard(entry)
            else:
                self.sources[source].remove(entry)
                if not any(entry in values for values in self.sources.values()):
                    self.unused.add(entry)
            return 'Success'
        if command.startswith('new ssl cert '):
            self.active[path] = ''
            self.unused.add(path)
            return 'New empty certificate store'
        if command.startswith('del ssl cert '):
            if path not in self.unused:
                return 'Certificate still used'
            del self.active[path]
            self.unused.remove(path)
            return 'Success'
        if command == 'show ssl cert':
            return '# filename\n' + '\n'.join(p for p in self.active if visible(p)) + '\n' + ''.join('*' + key + '\n' for key in self.staged if visible(key))
        if command.startswith('show ssl cert '):
            requested = command[len('show ssl cert '):].replace('\\ ', ' ').replace('\\\\', '\\')
            pem = self.staged.get(requested[1:], '') if requested.startswith('*') else self.active.get(requested, '')
            if not pem:
                return 'Certificate not found'
            certificate = x509.load_pem_x509_certificate(pem.encode())
            domains = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            return ('Status: ' + ('Unused' if requested in self.unused else 'Used') + '\nSHA1 FingerPrint: ' + remote.pem_fingerprint(pem)
                    + '\nSubject Alternative Name: ' + ', '.join(domains.get_values_for_type(x509.DNSName))
                    + '\nnotAfter: ' + certificate.not_valid_after_utc.strftime('%b %d %H:%M:%S %Y GMT'))
        if command.startswith('set ssl cert '):
            self.staged[path] = command.split(' <<\n', 1)[1].rstrip() + '\n'
            return 'Transaction created for certificate ' + path + '!'
        if command.startswith('commit ssl cert '):
            self.active[path] = self.staged.pop(path)
            if self.lose_commit:
                self.lose_commit = False
                raise OSError('lost acknowledgement')
            return 'Success'
        if command.startswith('abort ssl cert '):
            self.staged.pop(path, None)
            return 'Aborted'
        raise AssertionError(command)

    def revision(self, name):
        return hashlib.sha256(self.files[name].read_bytes()).hexdigest()
