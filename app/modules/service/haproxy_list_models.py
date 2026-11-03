"""Validated requests and IP-list contents shared by the UI and legacy API."""

from ipaddress import ip_address, ip_network
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_CONTENT = 256 * 1024


class ListIdentity(BaseModel):
    color: Literal['black', 'white']
    name: str = Field(min_length=1, max_length=124, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')

    @field_validator('name')
    @classmethod
    def filename(cls, value: str) -> str:
        """Keep dotted names intact and reject ambiguous path components."""
        if '..' in value:
            raise ValueError('Parent path components are not allowed')
        return value if value.endswith('.lst') else value + '.lst'


class ListContent(BaseModel):
    content: str = Field(default='', max_length=MAX_CONTENT)

    @field_validator('content')
    @classmethod
    def ip_entries(cls, value: str) -> str:
        """Validate each line, preserving comments and reporting its line number."""
        if len(value.encode('utf-8')) > MAX_CONTENT:
            raise ValueError('List exceeds 256 KiB')
        lines = []
        for number, line in enumerate(value.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                lines.append(line)
                continue
            try:
                entry = ip_network(line, strict=False) if '/' in line else ip_address(line)
            except ValueError:
                raise ValueError(f'Line {number}: expected an IPv4/IPv6 address or CIDR network') from None
            if hasattr(entry, 'prefixlen') and entry.prefixlen == entry.max_prefixlen:
                entry = entry.network_address
            lines.append(str(entry))
        return '\n'.join(lines).rstrip() + '\n' if any(lines) else ''


class ListChange(ListIdentity, ListContent):
    revision: str = Field(min_length=64, max_length=64, pattern=r'^[a-f0-9]+$')
    operation: Literal['save', 'delete'] = 'save'
    apply_mode: Literal['runtime', 'reload', 'restart'] = 'runtime'


class RuntimeEntry(ListIdentity):
    entry: str
    acl_id: int = Field(ge=0)
    pointer: str | None = Field(default=None, pattern=r'^0x[0-9a-fA-F]+$')

    @field_validator('entry')
    @classmethod
    def single_entry(cls, value: str) -> str:
        values = entries(value)
        if len(values) != 1 or len(value.splitlines()) != 1:
            raise ValueError('Expected one IP address or CIDR network')
        return values[0]


def entries(content: str) -> list[str]:
    """Return the effective, unique entries without altering stored comments."""
    return sorted({line for line in ListContent(content=content).content.splitlines()
                   if line and not line.startswith('#')})
