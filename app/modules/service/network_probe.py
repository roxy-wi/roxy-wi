"""Fixed stdlib probes; targets are numerical, bounded and never follow redirects."""
import base64
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import time


def address(value,*,loopback=True):
    ip=ipaddress.ip_address(value)
    if isinstance(ip,ipaddress.IPv6Address) and ip.ipv4_mapped:ip=ip.ipv4_mapped
    if ip.is_unspecified or ip.is_multicast or ip.is_link_local or str(ip) in ('255.255.255.255','100.100.100.200','fd00:ec2::254','fd20:ce::254') or (ip.is_loopback and not loopback):
        raise ValueError('A metadata, multicast, unspecified or out-of-scope address is not a probe target')
    return str(ip)


DNS_CODE='''import json,socket,sys
values=sorted({v[4][0] for v in socket.getaddrinfo(sys.argv[1],None,type=socket.SOCK_STREAM)})
if len(values)>16:raise ValueError('Too many DNS answers')
print(json.dumps(values))
'''


def resolve(host):
    try:return [address(host)]
    except ValueError:
        # A numerical blocked address must not be passed to a second resolver.
        try:ipaddress.ip_address(host)
        except ValueError:pass
        else:raise
    if not isinstance(host,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',host):raise ValueError('Invalid DNS name')
    result=subprocess.run([sys.executable,'-c',DNS_CODE,host],capture_output=True,text=True,timeout=6,check=True)
    if len(result.stdout)>8192:raise ValueError('DNS response is too large')
    values=json.loads(result.stdout)
    if not isinstance(values,list) or not 1<=len(values)<=16:raise ValueError('DNS did not return a bounded address set')
    return sorted({address(value) for value in values})


def connect(ip,port):
    family=socket.AF_INET6 if ipaddress.ip_address(ip).version==6 else socket.AF_INET
    connection=socket.socket(family,socket.SOCK_STREAM);connection.settimeout(3)
    try:connection.connect((ip,port));return connection
    except BaseException:connection.close();raise


def probe(data):
    ip=address(data['ip'],loopback=bool(data.get('allow_loopback',True)))
    port=data['port']
    if not isinstance(port,int) or not 1<=port<=65535:raise ValueError('Invalid port')
    domain=data.get('domain','')
    if domain and (len(domain)>253 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*',domain)):raise ValueError('Invalid SNI/Host name')
    path=data.get('path','/')
    if not isinstance(path,str) or not path.startswith('/') or len(path)>2048 or any(ord(c)<33 or ord(c)>126 for c in path):raise ValueError('Invalid request path')
    started=time.monotonic();result=dict(ip=ip,port=port,tcp='unknown',tls='not-requested',http='not-requested')
    connection=None
    try:
        connection=connect(ip,port);result.update(tcp='connected',connect_ms=round((time.monotonic()-started)*1000,1))
        if data.get('tls'):
            context=ssl.create_default_context()
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            if data.get('ca_pem'):
                ca=data['ca_pem']
                if not isinstance(ca,str) or len(ca.encode())>131072 or 'PRIVATE KEY' in ca:raise ValueError('Invalid public CA bundle')
                context.load_verify_locations(cadata=ca)
            context.set_alpn_protocols(['http/1.1'])
            try:
                connection=context.wrap_socket(connection,server_hostname=domain)
                certificate=connection.getpeercert(binary_form=True)
                result.update(tls='verified',certificate_der=base64.b64encode(certificate).decode(),
                              fingerprint=hashlib.sha256(certificate).hexdigest(),protocol=connection.version())
            except ssl.SSLCertVerificationError as error:
                result.update(tls='untrusted',tls_error=error.verify_code)
                if connection:connection.close()
                connection=None
                # A separate read-only handshake observes the rejected certificate;
                # no HTTP request or credentials cross this unverified connection.
                raw=connect(ip,port);inspection=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                inspection.minimum_version=ssl.TLSVersion.TLSv1_2
                inspection.check_hostname=False;inspection.verify_mode=ssl.CERT_NONE
                try:
                    with inspection.wrap_socket(raw,server_hostname=domain) as peer:
                        certificate=peer.getpeercert(binary_form=True)
                        result.update(certificate_der=base64.b64encode(certificate).decode(),fingerprint=hashlib.sha256(certificate).hexdigest())
                finally:raw.close()
                result['http']='skipped-untrusted-tls';return result
        if data.get('http'):
            host=domain+(':'+str(port) if port not in (80,443) else '')
            wire=f'HEAD {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\nUser-Agent: Roxy-WI-diagnostics\r\n\r\n'
            connection.sendall(wire.encode('ascii'))
            with connection.makefile('rb') as stream:line=stream.readline(4097)
            match=re.fullmatch(rb'HTTP/1\.[01] ([1-5][0-9][0-9])[^\r\n]*\r?\n',line)
            result['http']=int(match[1]) if match else 'invalid-status-line'
        return result
    except (ConnectionRefusedError,TimeoutError,socket.timeout,OSError,ssl.SSLError) as error:
        if result['tcp']=='unknown':result['tcp']='refused' if isinstance(error,ConnectionRefusedError) else 'timeout' if isinstance(error,(TimeoutError,socket.timeout)) else 'unreachable'
        elif data.get('tls') and result['tls']=='not-requested':result['tls']='handshake-failed'
        else:result['http']='probe-failed'
        return result
    finally:
        if connection:connection.close()


def source(operation):
    if operation not in ('resolve','probe'):raise ValueError('Unsupported network probe')
    return Path(__file__).read_text()+'\nrequest=json.load(sys.stdin)\nprint(json.dumps('+('resolve(request["host"])' if operation=='resolve' else 'probe(request)')+'))\n'
