"""Certificate-source connectors return PEM; deployment remains owned by Roxy-WI."""
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, urlsplit

import requests
from cryptography import x509
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.roxywi.exception import RoxywiValidationError
from app.modules.service.certificates import MAX_PEM_BYTES, private_write


class CertWardenSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    url: str = Field(max_length=2048)
    certificate: str = Field(min_length=1, max_length=255)
    certificate_api_key: str = Field(min_length=1, max_length=4096, repr=False)
    private_key_api_key: str = Field(min_length=1, max_length=4096, repr=False)
    ca_pem: str = Field(default='', max_length=65536)

    @field_validator('url')
    @classmethod
    def endpoint(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or any(c in value for c in '\r\n\x00\\')):
            raise ValueError('Use an HTTPS server URL without credentials, query or fragment')
        _port = parsed.port
        return value.rstrip('/')

    @field_validator('certificate', 'certificate_api_key', 'private_key_api_key')
    @classmethod
    def single_line(cls, value):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Names and credentials must be single-line values')
        return value

    @field_validator('certificate')
    @classmethod
    def certificate_name(cls, value):
        if value in ('.', '..') or any(c in value for c in '/\\'):
            raise ValueError('Provide a certificate name without path components')
        return value

    @field_validator('ca_pem')
    @classmethod
    def ca_certificates(cls, value):
        if value and not x509.load_pem_x509_certificates(value.encode('ascii')):
            raise ValueError('Provide PEM CA certificates')
        return value


class CertWarden:
    label = 'CertWarden'
    settings_model = CertWardenSettings
    secret_fields = ('certificate_api_key', 'private_key_api_key')

    @staticmethod
    def fetch(settings):
        """Only the configured HTTPS endpoint receives keys; redirects are refused."""
        url = settings['url'] + '/certwarden/api/v1/download/privatecertchains/' + quote(settings['certificate'], safe='')
        key = settings['certificate_api_key'] + '.' + settings['private_key_api_key']
        try:
            with TemporaryDirectory(prefix='roxywi-provider-') as directory, requests.Session() as http:
                http.trust_env = False
                verify = True
                if settings.get('ca_pem'):
                    ca = Path(directory) / 'ca.pem'
                    private_write(ca, settings['ca_pem'])
                    verify = str(ca)
                with http.get(url, headers={'X-API-Key': key}, verify=verify, allow_redirects=False,
                              timeout=(5, 15), stream=True) as response:
                    if response.status_code != 200:
                        raise RoxywiValidationError('Certificate provider refused the download; check endpoint and credentials')
                    result = bytearray()
                    deadline = time.monotonic() + 45
                    for chunk in response.iter_content(65536):
                        result.extend(chunk)
                        if len(result) > MAX_PEM_BYTES or time.monotonic() > deadline:
                            raise RoxywiValidationError('Certificate provider response exceeded the size or time limit')
                    return result.decode('ascii')
        except (requests.RequestException, UnicodeError, OSError):
            raise RoxywiValidationError('Certificate provider download failed; check connectivity, TLS trust and credentials') from None


PROVIDERS = {'certwarden': CertWarden}


def provider(name):
    try:
        return PROVIDERS[name]
    except KeyError:
        raise RoxywiValidationError('Unsupported certificate provider') from None


def validate_settings(name, settings):
    return provider(name).settings_model.model_validate(settings).model_dump()
