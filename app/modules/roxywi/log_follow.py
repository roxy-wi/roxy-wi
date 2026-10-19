"""Stateless service-log following, shared safely by all web replicas."""
import base64
import json
import shlex
from contextlib import closing
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer

from app.modules.roxywi.log_snapshot import remote_source
from app.modules.server import ssh as ssh_mod
from app.scripts.log_reader import audit_record

MAX_RESPONSE = 6 * 1024 * 1024
READ_ERROR = 'Cannot follow the remote log; check Python 3, the file and SSH/sudo permissions'


@lru_cache(maxsize=1)
def reader_command():
    helper = Path(__file__).resolve().parents[2] / 'scripts' / 'log_reader.py'
    return 'sudo -n python3 -c ' + shlex.quote(helper.read_text(encoding='utf-8'))


def remote_read(host, path, position, limit, record_format='lines'):
    # Short-lived reads don't occupy a worker/SSH session while the browser is
    # paused or gone. Every poll resolves the current SSH credentials again.
    connection = ssh_mod.ssh_connect(host, connect_timeout=3, banner_timeout=3)
    # Also close the client if authentication fails during __enter__.
    with closing(connection.ssh), connection:
        stdin, stdout, stderr = connection.ssh.exec_command(reader_command(), timeout=6)
        try:
            stdin.write(json.dumps(dict(path=path, position=position, limit=limit, format=record_format)))
            stdin.flush()
            stdin.channel.shutdown_write()
            data = stdout.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                raise OSError(READ_ERROR)
            error = stderr.read(4096)
            if stdout.channel.recv_exit_status() != 0 or error:
                raise OSError(READ_ERROR)
            result = json.loads(data)
            if not isinstance(result, dict) or result.get('error'):
                raise OSError(READ_ERROR)
            return result
        except (ValueError, UnicodeError) as exc:
            raise OSError(READ_ERROR) from exc
        finally:
            stdin.close()
            stdout.close()
            stderr.close()


def filter_result(result, query, audit=False):
    data = base64.b64decode(result['data'], validate=True)
    entries, unparsed = [], 0
    if audit:
        records, index = [], 0
        while index < len(data):
            raw, end, skipped = audit_record(data, index)
            if skipped or end == index:
                raise ValueError('Invalid audit record from remote reader')
            index = end
            if raw is not None:
                records.append(raw)
    else:
        records = data.split(b'\n')[:-1]
    for raw in records:
        entry, unknown = query.entry(raw.decode('utf-8', errors='replace').rstrip('\r\n'))
        unparsed += int(unknown)
        if entry is not None:
            entries.append(entry)
    return dict(entries=entries, limited=result['limited'], reset=result['reset'],
                more=result['more'], unparsed=unparsed, start=query.start.isoformat(), end=query.end.isoformat())


def snapshot(service, server, filename, waf, query):
    """Read complete audit transactions with the same bounded SSH reader as Live."""
    host, path = remote_source(service, server, filename, waf)
    result = remote_read(host, path, None, query.limit, record_format='modsecurity')
    try:
        filtered = filter_result(result, query, audit=True)
        filtered['entries'] = filtered['entries'][-query.limit:]
        return filtered
    except (ValueError, KeyError, TypeError) as exc:
        raise OSError(READ_ERROR) from exc


def follow(service, server, filename, waf, query, cursor=None, scope=None):
    if not query.relative:
        raise ValueError('Live requires a relative time range')
    host, path = remote_source(service, server, filename, waf)
    signer = URLSafeTimedSerializer(current_app.secret_key, salt='service-log-cursor-v1')
    signature = query.signature([service, server, host, path, waf], scope)
    previous = None
    if cursor:
        if len(cursor) > 16000:
            raise ValueError('Invalid log cursor')
        try:
            previous = signer.loads(cursor, max_age=86400)
            if previous['query'] != signature:
                raise ValueError('The log query changed; reload the view')
        except (BadData, KeyError, TypeError) as exc:
            raise ValueError('The log cursor expired; reload the view') from exc
    audit = waf and filename == 'audit.log'
    options = {'record_format': 'modsecurity'} if audit else {}
    result = remote_read(host, path, previous['position'] if previous else None, query.limit, **options)
    # SSH takes time: records written during the read must not be consumed as
    # "future" entries simply because the query was constructed before connecting.
    query.end = datetime.now(timezone.utc)
    query.start = query.end - timedelta(seconds=query.relative)
    try:
        position = result['position']
        if not isinstance(position['files'], dict) or len(position['files']) > 16:
            raise ValueError('Invalid remote position')
        filtered = filter_result(result, query, audit=audit)
        if previous and len(filtered['entries']) > query.limit:
            raise ValueError('Remote reader exceeded its row limit')
        filtered['entries'] = filtered['entries'][-query.limit:]
        filtered['cursor'] = signer.dumps(dict(query=signature, position=position))
        return filtered
    except (ValueError, KeyError, TypeError) as exc:
        raise OSError(READ_ERROR) from exc
