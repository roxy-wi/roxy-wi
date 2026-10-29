from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import io
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import threading
from types import SimpleNamespace
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from app.modules.service import network_probe as probe,published_endpoints as endpoints


@contextmanager
def endpoint(tmp_path,*,tls=False,bind='127.0.0.1',feed=None,feed_status=200):
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(dict(path=self.path,headers=dict(self.headers)))
            self.send_response(feed_status);self.send_header('Content-Type','text/plain')
            if feed_status==302:self.send_header('Location','https://must-not-follow.invalid/')
            self.end_headers()
            if feed:self.wfile.write(feed)
        def do_HEAD(self):
            requests.append(dict(path=self.path,headers=dict(self.headers)))
            self.send_response(302);self.send_header('Location','https://must-not-follow.invalid/')
            self.send_header('Set-Cookie','secret-session=NeverCollectThis');self.end_headers()
        def log_message(self,*args):pass
    server=ThreadingHTTPServer((bind,0),Handler)
    ca=None
    if tls:
        now=datetime.now(timezone.utc);key=ec.generate_private_key(ec.SECP256R1());leaf_key=ec.generate_private_key(ec.SECP256R1())
        root_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Diagnostic CA '+tmp_path.name[-32:])])
        ca=(x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name).public_key(key.public_key()).serial_number(1)
            .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256()))
        certificate=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'example.test')]))
            .issuer_name(root_name).public_key(leaf_key.public_key()).serial_number(2).not_valid_before(now-timedelta(days=1))
            .not_valid_after(now+timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('example.test')]),critical=False)
            .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True).sign(key,hashes.SHA256()))
        cert=tmp_path/'cert.pem';private=tmp_path/'key.pem'
        cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM)+ca.public_bytes(serialization.Encoding.PEM))
        private.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));private.chmod(0o600)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert,private)
        server.socket=context.wrap_socket(server.socket,server_side=True)
        ca=ca.public_bytes(serialization.Encoding.PEM).decode()
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield server.server_port,requests,ca
    finally:server.shutdown();server.server_close();thread.join(timeout=3)


def test_real_head_request_never_follows_redirect_or_sends_authentication(tmp_path,monkeypatch):
    monkeypatch.setenv('HTTP_PROXY','http://credentials:secret@must-not-contact.invalid')
    with endpoint(tmp_path) as (port,requests,_ca):
        result=probe.probe(dict(ip='127.0.0.1',port=port,domain='example.test',path='/health?q=1',http=True,tls=False))
    assert result['http']==302 and len(requests)==1
    assert requests[0]['path']=='/health?q=1' and requests[0]['headers']['Host']=='example.test:'+str(port)
    assert 'Authorization' not in requests[0]['headers'] and 'Cookie' not in requests[0]['headers']
    assert 'NeverCollectThis' not in json.dumps(result) and 'must-not-follow' not in json.dumps(result)


def test_real_tls_validates_private_ca_and_hostname(tmp_path):
    with endpoint(tmp_path,tls=True) as (port,requests,ca):
        result=probe.probe(dict(ip='127.0.0.1',port=port,domain='example.test',path='/',http=True,tls=True,ca_pem=ca))
    assert result['tls']=='verified' and result['http']==302 and len(result['fingerprint'])==64
    assert len(requests)==1 and result['certificate_der']


@pytest.mark.parametrize('failure',['trust','name'])
def test_rejected_tls_only_observes_certificate_and_sends_no_head(tmp_path,failure):
    with endpoint(tmp_path,tls=True) as (port,requests,ca):
        result=probe.probe(dict(ip='127.0.0.1',port=port,domain='wrong.test' if failure=='name' else 'example.test',path='/',
            http=True,tls=True,**(dict(ca_pem=ca) if failure=='name' else {})))
    assert result['tls']=='untrusted' and result['http']=='skipped-untrusted-tls'
    assert result['certificate_der'] and requests==[]


@pytest.mark.parametrize('value',['169.254.169.254','fe80::1','::ffff:169.254.169.254','224.0.0.1','0.0.0.0','fd00:ec2::254','100.100.100.200','fd20:ce::254'])
def test_metadata_and_special_targets_are_rejected_before_socket_use(value,monkeypatch):
    monkeypatch.setattr(probe,'connect',lambda *_:pytest.fail('Blocked address reached a socket'))
    with pytest.raises(ValueError):probe.probe(dict(ip=value,port=80,http=True))


def test_controller_probe_cannot_target_its_own_loopback():
    with pytest.raises(ValueError):probe.probe(dict(ip='127.0.0.1',port=80,allow_loopback=False))


def test_native_inventory_parsers_preserve_listener_and_backend_scope():
    nginx=endpoints.parse('nginx','http { upstream pool { server 192.0.2.88:8080; } server { listen 443 ssl; server_name example.test; location / { proxy_pass http://pool; } } }')
    front=nginx['frontends'][0]
    assert front['tls'] and front['domains']==['example.test'] and front['backends'][0]['host']=='192.0.2.88'
    apache=endpoints.parse('apache','<VirtualHost *:443>\nServerName example.test\nSSLEngine on\nProxyPass / http://192.0.2.88:8080/\n</VirtualHost>')
    assert apache['frontends'][0]['backends'][0]['port']==8080


@pytest.mark.parametrize('value',['unix:/run/backend.sock','http://user:password@example.test/','$unresolved:80','127.0.0.1:1-1024','fd@5'])
def test_dynamic_or_credentialed_targets_are_not_probed(value):
    assert endpoints.endpoint(value) is None


def test_dumped_nginx_includes_retain_server_context_and_do_not_cross_directories():
    from app.modules.service import nginx
    dump='''# configuration file /etc/nginx/nginx.conf:
events {}
http { include /etc/nginx/sites/*.conf; }
# configuration file /etc/nginx/sites/site.conf:
server { listen 443 ssl; server_name example.test; include snippets/backend.conf; }
# configuration file /etc/nginx/snippets/backend.conf:
location / { proxy_pass http://192.0.2.88:8080; }
# configuration file /etc/nginx/sites/nested/not-in-glob.conf:
server { listen 9999; }
'''
    expanded,partial=nginx.expand_dump(dump)
    result=endpoints.parse('nginx',dump)
    assert not partial and len(result['frontends'])==1
    assert result['frontends'][0]['backends'][0]['port']==8080
    assert '9999' not in expanded


def test_apache_includes_keep_the_virtual_host_context():
    files={'/etc/apache2/apache2.conf':'ServerRoot "/etc/apache2"\n<VirtualHost *:443>\nServerName example.test\nInclude sites/backend.conf\n</VirtualHost>',
           '/etc/apache2/sites/backend.conf':'ProxyPass / http://192.0.2.88:8080/'}
    text,partial=endpoints.apache_configuration(files,'/etc/apache2/apache2.conf')
    assert not partial and endpoints.parse('apache',text)['frontends'][0]['backends'][0]['port']==8080


@pytest.mark.parametrize(('available', 'expected'), [
    (('httpd', 'apachectl'), 'httpd'),
    (('apache2ctl', 'apachectl', 'httpd'), 'apache2ctl'),
    (('apachectl',), 'apachectl'),
])
def test_apache_inventory_uses_configuration_capable_command(monkeypatch, capsys, available, expected):
    main = '/etc/httpd/conf/httpd.conf'
    content = '<VirtualHost *:80>\nServerName example.test\n</VirtualHost>'
    monkeypatch.setattr(shutil, 'which', lambda value: value if value in available else None)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(dict(main=main))))

    def run(args, **kwargs):
        assert args == [expected, '-t', '-D', 'DUMP_INCLUDES', '-f', main]
        assert kwargs['check'] and kwargs['timeout'] == 30
        return SimpleNamespace(stdout=f'Included configuration files:\n  (*) {main}\n', stderr='')

    def read_text(path):
        assert path == Path(main)
        return content

    monkeypatch.setattr(subprocess, 'run', run)
    monkeypatch.setattr(Path, 'read_text', read_text)
    exec(endpoints.APACHE_FILES, {})
    assert json.loads(capsys.readouterr().out) == dict(files={main: content}, root=main)


def test_apache_inventory_does_not_hide_configuration_errors(monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda value: value if value == 'httpd' else None)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(dict(main='/etc/httpd/conf/httpd.conf'))))

    def run(args, **_kwargs):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        exec(endpoints.APACHE_FILES, {})
