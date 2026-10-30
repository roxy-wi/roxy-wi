"""Read-only diagnostics from the latest worker heartbeat, without remote probes."""
import re
from urllib.parse import urlsplit, urlunsplit

from app.modules.common.time import utc_iso, utc_now
from app.modules.db.db_model import Server, ServiceAssignment
from app.modules.db.service_event import worker_instances, worker_status
from app.modules.tools.common import _DISTRIBUTED_TOOLS, _INTERNAL_TOOLS


WORKER_SERVICES = {**_DISTRIBUTED_TOOLS, **_INTERNAL_TOOLS}
MAX_WORKERS = 100
MAX_ISSUES = 100
MAX_HISTORY = 20


def redact_error(value: str, *, max_length: int = 2000) -> str:
    # Heartbeats may contain exception text, never render arbitrary metadata.
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|$)',
                  '[redacted]', value[:20000], flags=re.S)

    def redact_url(match):
        try:
            parts = urlsplit(match.group())
            host = parts.netloc.rsplit('@', 1)[-1]
            return urlunsplit((parts.scheme, host, parts.path, '', ''))
        except ValueError:
            return '[redacted URL]'

    text = re.sub(r'\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s<>\"\']+', redact_url, text)
    text = re.sub(r'(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9+/=._~-]+', '[redacted authorization]', text)
    text = re.sub(
        r'''(?ix)(["']?(?:password|passwd|pwd|secret(?:_key)?|client_secret|api[_-]?(?:key|token)|access[_-]?token|refresh[_-]?token|token|authorization|cookie)["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\s,;]+)''',
        r'\1[redacted]', text,
    )
    return text[:max_length]


def error_reason(message: str) -> str:
    value = message.lower()
    if 'distributed keepalived checks require' in value:
        return 'keepalived'
    if 'connection refused' in value:
        return 'refused'
    if any(word in value for word in ('timed out', 'timeout')):
        return 'timeout'
    if any(word in value for word in ('nameresolutionerror', 'name or service not known', 'getaddrinfo failed')):
        return 'dns'
    if any(word in value for word in ('401 client error', '403 client error', 'authentication', 'access_refused')):
        return 'access'
    if any(word in value for word in ('sslerror', 'certificate verify failed')):
        return 'tls'
    return 'unknown_error'


def service_diagnostics(tool: str) -> dict:
    service = WORKER_SERVICES[tool]
    now = utc_now()
    instances = sorted(worker_instances(service, history_limit=MAX_HISTORY, now=now).values(),
                       key=lambda item: (item['current'].last_heartbeat, item['current'].worker_id), reverse=True)
    limited = len(instances) > MAX_WORKERS
    instances = instances[:MAX_WORKERS]
    # Resolve current issues first so historical errors cannot hide today's cause.
    rows = [item['current'] for item in instances]
    rows.extend(row for item in instances for row in item['parallel'])
    rows.extend(row for item in instances for row in item['history'])
    assignment_ids = set()
    for row in rows:
        metadata = row.metadata if isinstance(row.metadata, dict) else {}
        errors = metadata.get('assignment_errors', {})
        if isinstance(errors, dict):
            assignment_ids.update(list(errors)[:max(0, MAX_ISSUES - len(assignment_ids))])
    assignments = {row.assignment_id: row for row in ServiceAssignment.select(
        ServiceAssignment.assignment_id, ServiceAssignment.server_id, ServiceAssignment.service,
    ).where((ServiceAssignment.target_service == service) & ServiceAssignment.assignment_id.in_(assignment_ids))}
    server_ids = {row.server_id for row in assignments.values() if row.server_id is not None}
    servers = {row.server_id: row for row in Server.select(Server.server_id, Server.hostname, Server.ip)
               .where(Server.server_id.in_(server_ids))}
    runs = {}
    remaining_issues = MAX_ISSUES
    for row in rows:
        metadata = row.metadata if isinstance(row.metadata, dict) else {}
        errors = metadata.get('assignment_errors', {})
        issues = []
        if isinstance(errors, dict):
            limited = limited or len(errors) > remaining_issues
            for assignment_id, error in list(errors.items())[:remaining_issues]:
                if not isinstance(error, str) or not error:
                    continue
                assignment = assignments.get(assignment_id)
                server = servers.get(assignment.server_id) if assignment else None
                issues.append({
                    'assignment': assignment_id, 'reason': error_reason(error), 'error': redact_error(error),
                    'server': server.hostname if server else None, 'address': server.ip if server else None,
                    'server_id': server.server_id if server else None,
                    'service': assignment.service if assignment else None,
                })
                remaining_issues -= 1
        if isinstance(metadata.get('last_error'), str) and metadata['last_error']:
            error = metadata['last_error']
            if remaining_issues:
                issues.append({'reason': error_reason(error), 'error': redact_error(error)})
                remaining_issues -= 1
            else:
                limited = True
        status = worker_status(row, now)
        runs[id(row)] = {
            'id': row.worker_id, 'hostname': row.hostname, 'instance': row.instance_id,
            'version': row.version, 'status': status, 'reported_status': row.status,
            'started': utc_iso(row.started_at) if row.started_at else None,
            'heartbeat': utc_iso(row.last_heartbeat), 'expires': utc_iso(row.expires_at),
            'assignments': row.active_assignments, 'capacity': row.capacity,
            'reason': status,
            'issues': issues,
        }
    workers = []
    for item in instances:
        worker = runs[id(item['current'])]
        worker.update(status=item['status'], overlap_count=item['overlap_count'],
                      reason='overlap' if item['overlap_count'] else item['status'],
                      parallel=[runs[id(row)] for row in item['parallel']],
                      parallel_count=item['parallel_count'],
                      history=[runs[id(row)] for row in item['history']],
                      history_count=item['history_count'],
                      history_limited=item['history_count'] > len(item['history']))
        workers.append(worker)
        limited = limited or item['parallel_count'] > len(item['parallel'])
    return {'tool': tool, 'workers': workers, 'limited': limited, 'checked_at': utc_iso(now)}
