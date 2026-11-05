"""Read-only, validated snapshots from NGINX OSS and Apache status endpoints."""

import re
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.modules.common.time import utc_iso, utc_now
from app.modules.db import sql
from app.modules.db.db_model import Server
from app.modules.service import managed_runtime
from app.modules.service.stats.haproxy_stats import StatsError


Counter = Annotated[int, Field(ge=0)]
Measurement = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class NginxStats(BaseModel):
    active: Counter
    accepts: Counter
    handled: Counter
    requests: Counter
    reading: Counter
    writing: Counter
    waiting: Counter


class ApacheStats(BaseModel):
    version: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    busy: Counter
    idle: Counter
    scoreboard: Annotated[str, Field(pattern=r'^[._SRWKDCLGI]+$', max_length=65536)]
    requests: Counter | None = None
    total_kbytes: Counter | None = None
    uptime: Counter | None = None
    cpu_load: Measurement | None = None
    average_rps: Measurement | None = None
    average_bps: Measurement | None = None
    bytes_per_request: Measurement | None = None
    graceful: Counter | None = None
    connections: Counter | None = None
    async_writing: Counter | None = None
    async_keepalive: Counter | None = None
    async_closing: Counter | None = None

    @field_validator('version')
    @classmethod
    def short_version(cls, value: str | None) -> str | None:
        """Keep the Apache version without platform and loaded-module banners."""
        return value.split(' ', 1)[0].removeprefix('Apache/') if value is not None else None


APACHE_FIELDS = {
    'ServerVersion': 'version',
    'BusyWorkers': 'busy', 'IdleWorkers': 'idle', 'Scoreboard': 'scoreboard',
    'Total Accesses': 'requests', 'Total kBytes': 'total_kbytes', 'Uptime': 'uptime',
    'CPULoad': 'cpu_load', 'ReqPerSec': 'average_rps', 'BytesPerSec': 'average_bps',
    'BytesPerReq': 'bytes_per_request', 'GracefulWorkers': 'graceful',
    'ConnsTotal': 'connections', 'ConnsAsyncWriting': 'async_writing',
    'ConnsAsyncKeepAlive': 'async_keepalive', 'ConnsAsyncClosing': 'async_closing',
}
NGINX_RESPONSE = re.compile(
    r'\s*Active connections:\s*(?P<active>\d+)\s+'
    r'server accepts handled requests\s+'
    r'(?P<accepts>\d+)\s+(?P<handled>\d+)\s+(?P<requests>\d+)\s+'
    r'Reading:\s*(?P<reading>\d+)\s+Writing:\s*(?P<writing>\d+)\s+'
    r'Waiting:\s*(?P<waiting>\d+)\s*'
)


def parse_nginx(text: str) -> dict:
    """Accept only the documented stub_status response, never an HTML error."""
    match = NGINX_RESPONSE.fullmatch(text)
    if match is None:
        raise StatsError('invalid_response')
    try:
        return NginxStats.model_validate(match.groupdict()).model_dump()
    except ValidationError as exc:
        raise StatsError('invalid_response') from exc


def parse_apache(text: str) -> dict:
    """Retain absent ExtendedStatus fields as null and ignore unknown fields."""
    fields = {}
    for line in text.splitlines():
        key, separator, value = line.partition(':')
        name = APACHE_FIELDS.get(key.strip())
        if separator and name:
            if name in fields:
                raise StatsError('invalid_response')
            fields[name] = value.strip()
    try:
        return ApacheStats.model_validate(fields).model_dump()
    except ValidationError as exc:
        raise StatsError('invalid_response') from exc


def collect_stats(server: Server, service: str) -> dict:
    """Use the registered server's group credentials and existing OCI transport."""
    if service not in ('nginx', 'apache'):
        raise ValueError('Unsupported HTTP statistics service')
    settings = {
        name: sql.get_setting(f'{service}_stats_{name}', group_id=int(server.group_id))
        for name in ('port', 'page', 'user', 'password')
    }
    path = settings['page']
    if service == 'apache':
        parts = urlsplit(path)
        query = [(key, value) for key, value in parse_qsl(parts.query) if key != 'auto']
        path = urlunsplit(('', '', parts.path, urlencode([*query, ('auto', '')]), ''))
    try:
        response = managed_runtime.statistics_response(
            str(server.ip), service, settings['port'], path, settings['user'], settings['password'],
        )
    except requests.Timeout as exc:
        raise StatsError('timeout', 504) from exc
    except requests.RequestException as exc:
        raise StatsError('unavailable') from exc
    if response.status_code in (401, 403):
        raise StatsError('stats_forbidden')
    if response.status_code == 404:
        raise StatsError('not_configured')
    if response.status_code != 200:
        raise StatsError('unavailable')
    if len(response.content) > 1024 * 1024:
        raise StatsError('invalid_response')
    try:
        text = response.content.decode('utf-8-sig')
        counters = parse_nginx(text) if service == 'nginx' else parse_apache(text)
    except UnicodeError as exc:
        raise StatsError('invalid_response') from exc
    version = counters.pop('version', None)
    return {'status': 'ok', 'service': service, 'observed_at': utc_iso(utc_now()),
            'info': {'version': version}, 'counters': counters}
