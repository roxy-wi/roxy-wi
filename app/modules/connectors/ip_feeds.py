"""Pinned, verified HTTPS downloads and strict IP/CIDR feed normalization."""
import hashlib
import http.client
import ipaddress
import ssl
import time
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator
from cryptography import x509
from app.modules.service import network_probe


MAX_BYTES=2*1024*1024


class HttpsSettings(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    url: str=Field(min_length=1,max_length=2048)
    allow_private: bool=Field(default=False,strict=True)
    ca_pem: str=Field(default='',max_length=131072)
    max_entries: int=Field(default=50000,ge=1,le=100000)
    min_ipv4_prefix: int=Field(default=8,ge=0,le=32)
    min_ipv6_prefix: int=Field(default=16,ge=0,le=128)

    @field_validator('url')
    @classmethod
    def valid_url(cls,value):
        parsed=urlsplit(value)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or any(ord(c)<33 or ord(c)>126 for c in value) or '\\' in value:
            raise ValueError('Use an HTTPS feed without URL credentials or fragments')
        if parsed.port is not None and not 1<=parsed.port<=65535:raise ValueError('Invalid HTTPS port')
        return value

    @field_validator('ca_pem')
    @classmethod
    def public_ca(cls,value):
        if value and ('PRIVATE KEY' in value or not x509.load_pem_x509_certificates(value.encode())):
            raise ValueError('Use a public PEM CA bundle')
        return value


def normalize(text,settings):
    if not isinstance(text,str) or len(text.encode())>MAX_BYTES:raise ValueError('Feed exceeds its size limit')
    entries=set()
    for line in text.lstrip('\ufeff').splitlines():
        line=line.split('#',1)[0].strip()
        if not line:continue
        if any(c.isspace() for c in line):raise ValueError('Each feed line must contain one IP or CIDR')
        net=ipaddress.ip_network(line,strict=False)
        minimum=settings['min_ipv4_prefix'] if net.version==4 else settings['min_ipv6_prefix']
        if net.prefixlen<minimum:raise ValueError('Feed contains a network broader than the approved prefix policy')
        if net.is_multicast or net.is_unspecified or net.is_loopback or net.is_link_local:
            raise ValueError('Feed contains a special-purpose network')
        entries.add(str(net))
        if len(entries)>settings['max_entries']:raise ValueError('Feed contains too many entries')
    if not entries:raise ValueError('An empty feed cannot replace an ACL')
    result=sorted(entries)
    content='\n'.join(result)+'\n'
    if len(content.encode())>MAX_BYTES:raise ValueError('Normalized feed exceeds its size limit')
    return content


def fingerprint(content):return hashlib.sha256(content.encode()).hexdigest()


class HttpsIpFeed:
    label='HTTPS IP/CIDR text feed'
    settings_model=HttpsSettings

    @staticmethod
    def fetch(settings):
        parsed=urlsplit(settings['url']);host=parsed.hostname;port=parsed.port or 443
        addresses=network_probe.resolve(host)
        # Validate all answers before contacting any. Resolution is never repeated
        # by the HTTP client, and TLS still verifies the original host/SNI.
        for value in addresses:
            ip=ipaddress.ip_address(network_probe.address(value,loopback=False))
            if not settings['allow_private'] and not ip.is_global:raise ValueError('Feed DNS includes a non-public address')
        context=ssl.create_default_context()
        if settings.get('ca_pem'):context.load_verify_locations(cadata=settings['ca_pem'])
        connection=http.client.HTTPSConnection(host,port,timeout=10,context=context)
        def connect():
            raw=network_probe.connect(addresses[0],port)
            try:connection.sock=context.wrap_socket(raw,server_hostname=host)
            except BaseException:raw.close();raise
        connection.connect=connect
        try:
            path=parsed.path or '/'
            if parsed.query:path+='?'+parsed.query
            connection.request('GET',path,headers={'Accept':'text/plain','Accept-Encoding':'identity','User-Agent':'Roxy-WI managed ACL feed','Connection':'close'})
            response=connection.getresponse()
            if response.status!=200 or response.getheader('Content-Encoding','identity').lower()!='identity':
                raise ValueError('Feed must return an uncompressed HTTP 200 response without redirects')
            total=bytearray();deadline=time.monotonic()+45
            while True:
                chunk=response.read1(65536)
                if not chunk:break
                total.extend(chunk)
                if len(total)>MAX_BYTES or time.monotonic()>deadline:raise ValueError('Feed exceeded its size/time limit')
            return normalize(total.decode('utf-8'),settings)
        finally:connection.close()


PROVIDERS={'https-ip-list':HttpsIpFeed}


def provider(name):
    if name not in PROVIDERS:raise ValueError('Unsupported IP-feed provider')
    return PROVIDERS[name]
