"""Validated outbound options shared by connection profiles and integration adapters."""
import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.modules.roxywi.exception import RoxywiValidationError


SECRET_FIELDS = frozenset({'password', 'token', 'ca_pem', 'client_cert_pem', 'client_key_pem'})
IDENTITY_FIELDS = ('transport', 'host', 'port', 'url', 'auth', 'username', 'header_name')
AUTHENTICATION_FIELDS = frozenset({'password', 'token', 'client_cert_pem', 'client_key_pem'})


@dataclass(frozen=True)
class ResolvedConnection:
    profile_id: int
    revision: int
    settings: dict
    credentials: dict = field(repr=False)


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=128)
    group_id: int = Field(ge=0)
    enabled: bool = True
    revision: int | None = Field(default=None, ge=1)
    transport: Literal['tcp_tls', 'tcp', 'udp', 'https'] = 'tcp_tls'
    host: str = Field(default='', max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)
    url: str = Field(default='', max_length=2048)
    timeout: int = Field(default=5, ge=1, le=10)
    framing: Literal['octet_counting', 'newline'] = 'octet_counting'
    auth: Literal['none', 'basic', 'bearer', 'api_key'] = 'none'
    username: str = Field(default='', max_length=256)
    header_name: str = Field(default='X-API-Key', max_length=128)
    secrets: dict[str, str] = Field(default_factory=dict)
    clear_secrets: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode='after')
    def compatible(self):
        if self.port is None:
            self.port = {'tcp_tls': 6514, 'tcp': 514, 'udp': 514, 'https': 443}[self.transport]
        self.name = self.name.strip()
        if not self.name:
            raise ValueError('A profile name is required')
        if set(self.secrets) - SECRET_FIELDS or set(self.clear_secrets) - SECRET_FIELDS:
            raise ValueError('Unknown credential field')
        if any(len(value) > 65536 for value in self.secrets.values()):
            raise ValueError('Credential is too large')
        if self.transport == 'https':
            parts = urlsplit(self.url)
            if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
                    or parts.fragment or parts.query):
                raise ValueError('Use an HTTPS URL without credentials, query or fragment')
            self.host = parts.hostname
            self.port = parts.port or 443
            if self.auth == 'basic' and not self.username:
                raise ValueError('Basic authentication requires a username')
            if ':' in self.username or any(c in self.username for c in '\r\n'):
                raise ValueError('Invalid username')
            if (not re.fullmatch(r'[A-Za-z0-9!#$%&\'*+.^_`|~-]+', self.header_name)
                    or self.header_name.lower() in {'host', 'authorization', 'connection', 'content-length',
                                                    'transfer-encoding', 'cookie', 'proxy-authorization'}):
                raise ValueError('Invalid API key header')
        elif self.auth != 'none':
            raise ValueError('Username/token authentication requires an HTTPS receiver')
        if (not self.host or any(c.isspace() for c in self.host)
                or any(c in self.host for c in '/\\@?#%')):
            raise ValueError('Invalid destination host')
        if any('\r' in self.secrets.get(k, '') or '\n' in self.secrets.get(k, '')
               for k in ('password', 'token')):
            raise ValueError('Invalid credential')
        return self


def parse_input(data):
    try:
        return ProfileInput.model_validate(data)
    except (ValidationError, ValueError, TypeError):
        # Pydantic errors can contain the original secret input.
        raise RoxywiValidationError('Invalid connection profile; check destination, transport and credentials') from None


def require_credentials_for_identity_change(body, previous_settings, previous_credentials):
    """Hidden credentials may only be reused for the same destination identity."""
    changed = any(previous_settings.get(key) != getattr(body, key) for key in IDENTITY_FIELDS)
    retained = any(previous_credentials.get(key) and key not in body.secrets and key not in body.clear_secrets
                   for key in AUTHENTICATION_FIELDS)
    if changed and retained:
        raise RoxywiValidationError('Re-enter or clear saved authentication credentials before changing the destination identity')


def merge_credentials(body, previous):
    values = dict(previous)
    for key in body.clear_secrets:
        values.pop(key, None)
    values.update(body.secrets)
    if body.transport not in {'tcp_tls', 'https'} and any(values.get(k) for k in (
        'ca_pem', 'client_cert_pem', 'client_key_pem',
    )):
        raise RoxywiValidationError('TLS credentials require a TLS transport; explicitly clear them first')
    if bool(values.get('client_cert_pem')) != bool(values.get('client_key_pem')):
        raise RoxywiValidationError('Provide both client certificate and private key')
    if body.auth == 'basic' and not values.get('password'):
        raise RoxywiValidationError('A password is required')
    if body.auth in {'bearer', 'api_key'} and not values.get('token'):
        raise RoxywiValidationError('A token is required')
    if body.auth == 'none' and (values.get('password') or values.get('token')):
        raise RoxywiValidationError('Explicitly clear credentials before disabling authentication')
    if body.auth == 'basic' and values.get('token') or body.auth in {'bearer', 'api_key'} and values.get('password'):
        raise RoxywiValidationError('Explicitly clear credentials for the previous authentication method')
    from app.modules.integrations.connection_transport import tls_context
    if body.transport in {'tcp_tls', 'https'}:
        try:
            tls_context(values)  # Validate certificate/key pairing before saving.
        except (OSError, ValueError):
            raise RoxywiValidationError('Invalid CA, client certificate or private key') from None
    return values
