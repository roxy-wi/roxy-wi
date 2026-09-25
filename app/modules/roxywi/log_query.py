"""Bounded log queries and signed, stateless cursors for the internal viewer."""
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytz
from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer

from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi.log_store import store_path

MAX_FILES = 128
MAX_BYTES = 4 * 1024 * 1024
CHUNK_BYTES = 256 * 1024
MAX_LINE = 64 * 1024
MAX_ROWS = 1000
PROCESS_ROLES = ('web', 'scheduler', 'operations', 'service-events')
MONTHS = {name: number for number, name in enumerate(
    ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'), 1
)}


def iso_time(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Dates must include a timezone')
    return result.astimezone(timezone.utc)


class LogQuery:
    def __init__(self, values, now=None):
        now = now or datetime.now(timezone.utc)
        self.limit = int(values.get('limit', 100))
        if not 1 <= self.limit <= MAX_ROWS:
            raise ValueError('The row limit must be between 1 and 1000')
        self.relative = int(values.get('relative', 0))
        if self.relative:
            if not 60 <= self.relative <= 31 * 86400:
                raise ValueError('Relative range must be between 1 minute and 31 days')
            self.end, self.start = now, now - timedelta(seconds=self.relative)
        else:
            self.start, self.end = iso_time(values.get('from')), iso_time(values.get('to'))
        if self.start >= self.end or self.end - self.start > timedelta(days=31):
            raise ValueError('Choose an increasing time range of at most 31 days')
        self.include, self.exclude = values.get('search', ''), values.get('exclude', '')
        self.process = values.get('process', '')
        if self.process and self.process not in PROCESS_ROLES:
            raise ValueError('Unknown application process')
        if len(self.include) > 256 or len(self.exclude) > 256:
            raise ValueError('Search text must be at most 256 characters')
        try:
            self.tz = pytz.timezone(values.get('timezone', 'UTC'))
        except pytz.UnknownTimeZoneError as exc:
            raise ValueError('Unknown log timezone') from exc

    def signature(self, source, scope):
        parts = [source, scope, self.limit, self.include, self.exclude, self.process, str(self.tz), self.relative]
        if not self.relative:
            parts += [self.start.isoformat(), self.end.isoformat()]
        return hashlib.sha256(json.dumps(parts).encode()).hexdigest()

    def entry(self, line, group_id=None):
        record = None
        if line.startswith('{'):
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                record = None
        if not isinstance(record, dict):
            record = None
        # A group admin never receives unattributed system/background records.
        if group_id is not None and (record is None or str(record.get('group_id')) != str(group_id)):
            return None, False
        if self.process and (record is None or record.get('process_role') != self.process):
            return None, False
        if self.include or self.exclude:
            # Match displayed Unicode fields as well as the original JSON escapes.
            searchable = line if record is None else line + '\n' + json.dumps(record, ensure_ascii=False)
            if self.include and self.include not in searchable or self.exclude and self.exclude in searchable:
                return None, False
        timestamp = parse_timestamp(line, record, self.end, self.tz)
        if timestamp is None:
            return None, True
        if not self.start <= timestamp <= self.end:
            return None, False
        return {'text': line, 'timestamp': timestamp.isoformat()}, False


def parse_timestamp(line, record, reference, tz):
    """Common JSON, RFC3339 syslog, nginx and Apache timestamps.

    Yearless syslog uses the year nearest to the query's end. Lines without a
    timestamp are reported as unparsed instead of pretending the filter worked.
    """
    try:
        if record and record.get('timestamp'):
            value = datetime.fromisoformat(str(record['timestamp']).replace('Z', '+00:00'))
            # Roxy-WI historically emitted naive UTC in structured records.
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        match = re.search(r'\b(\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:\d\d)?)', line[:100])
        if match:
            value = datetime.fromisoformat(match[1].replace('Z', '+00:00').replace(',', '.'))
        else:
            match = re.search(r'\[(\d\d)/(\w{3})/(\d{4}):(\d\d:\d\d:\d\d) ([+-]\d{4})\]', line[:300])
            if match:
                date = f'{match[3]}-{MONTHS[match[2]]:02}-{match[1]} {match[4]} {match[5]}'
                return datetime.strptime(date, '%Y-%m-%d %H:%M:%S %z').astimezone(timezone.utc)
            match = re.match(r'(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d)', line)
            if match:
                value = datetime.strptime(match[1], '%Y/%m/%d %H:%M:%S')
            else:
                match = re.match(r'\[?([A-Za-z]{3} )?([A-Za-z]{3})\s+(\d{1,2}) (\d\d:\d\d:\d\d(?:\.\d+)?)(?: (\d{4})\])?', line)
                if not match:
                    return None
                local_end = reference.astimezone(tz)
                year = int(match[5]) if match[5] else local_end.year
                date = f'{year}-{MONTHS[match[2]]:02}-{int(match[3]):02}T{match[4]}'
                value = datetime.fromisoformat(date)
                if not match[5]:
                    candidates = []
                    for delta in (-1, 0, 1):
                        try:
                            candidates.append(value.replace(year=year + delta))
                        except ValueError:
                            continue  # February 29 has no equivalent in every year.
                    value = min(candidates, key=lambda item: abs(item - local_end.replace(tzinfo=None)))
        if value.tzinfo is None:
            value = tz.localize(value, is_dst=None)
        return value.astimezone(timezone.utc)
    except (ValueError, KeyError, TypeError, OverflowError, pytz.InvalidTimeError):
        return None


def sources():
    result = []
    if store_path() is not None:
        result.append(('runtime', 'Roxy-WI (all processes)'))
    root = Path(GetConfigVar().get_config_var('main', 'log_path', '/var/log/roxy-wi'))
    if root.is_dir():
        result += [(p.name, p.name) for p in sorted(root.glob('*.log')) if p.is_file() and not p.is_symlink()]
    return result


def source_files(source):
    if source == 'runtime':
        root = store_path()
        if root is None:
            raise ValueError('The log journal is disabled')
        candidates = root.glob('rwi-*.log')
    else:
        if source not in dict(sources()):
            raise ValueError('Unknown log source')
        root = Path(GetConfigVar().get_config_var('main', 'log_path', '/var/log/roxy-wi'))
        candidates = root.glob(source + '*')
    paths = []
    for path in candidates:
        try:
            info = path.lstat()
            if stat.S_ISREG(info.st_mode) and not path.name.endswith('.gz'):
                paths.append((path, info))
        except FileNotFoundError:
            continue  # Rotation between listing and stat.
    paths.sort(key=lambda item: item[1].st_mtime, reverse=True)
    return paths[:MAX_FILES], len(paths) > MAX_FILES


def _identity(info):
    return f'{info.st_dev}:{info.st_ino}'


def _anchor(stream, offset):
    stream.seek(max(0, offset - 64))
    return hashlib.sha256(stream.read(min(offset, 64))).hexdigest()


def read_logs(source, query, cursor=None, scope=None, group_id=None):
    signer = URLSafeTimedSerializer(current_app.secret_key, salt='internal-log-cursor-v1')
    signature = query.signature(source, scope)
    previous = None
    if cursor:
        if len(cursor) > 40000:
            raise ValueError('Invalid log cursor')
        try:
            previous = signer.loads(cursor, max_age=86400)
            if previous['query'] != signature:
                raise ValueError('The log query changed; reload the view')
        except (BadData, KeyError, TypeError) as exc:
            raise ValueError('The log cursor expired; reload the view') from exc
    files, limited = source_files(source)
    positions, entries = {}, []
    unparsed, budget, more, reset = 0, MAX_BYTES, False, False
    old = previous['files'] if previous else {}
    available = {_identity(info) for _, info in files}
    # Follow old segments before newer ones. Initial queries keep the newest tail.
    for path, listed in (reversed(files) if previous else files):
        if budget <= 0:
            limited = True
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
        except FileNotFoundError:
            continue
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or _identity(info) != _identity(listed):
                continue
            identity = _identity(info)
            position = old.get(identity)
            dropping = False
            if position:
                offset = position['offset']
                dropping = position.get('dropping', False)
                if offset > info.st_size or _anchor(stream, offset) != position['anchor']:
                    offset, reset = 0, True
                    dropping = False
            elif previous:
                offset = 0
            else:
                offset = max(0, info.st_size - min(CHUNK_BYTES, budget))
                if offset:
                    limited = True
                    stream.seek(offset - 1)
                    dropping = stream.read(1) != b'\n'
            stream.seek(offset)
            read_limit = min(budget, CHUNK_BYTES)
            full = budget <= 0 or previous and len(entries) >= query.limit
            data = b'' if full else stream.read(read_limit)
            budget -= len(data)
            base, index = offset, 0
            if dropping:
                newline = data.find(b'\n')
                index = len(data) if newline < 0 else newline + 1
                offset = base + index
                dropping = newline < 0
            while index < len(data) and not (previous and len(entries) >= query.limit):
                newline = data.find(b'\n', index)
                if newline < 0:
                    if len(data) - index > MAX_LINE:
                        # Continue skipping this oversized line until its newline;
                        # never reinterpret its suffix as a separate log record.
                        dropping, limited, offset = True, True, base + len(data)
                    break  # An ordinary partial write remains behind the cursor.
                raw = data[index:newline]
                index = newline + 1
                offset = base + index
                if len(raw) > MAX_LINE:
                    limited = True
                    continue
                entry, unknown = query.entry(raw.decode('utf-8', errors='replace').rstrip('\r'), group_id)
                unparsed += int(unknown)
                if entry is not None:
                    entries.append(entry)
            positions[identity] = {'offset': offset, 'anchor': _anchor(stream, offset), 'size': info.st_size, 'dropping': dropping}
            if offset < info.st_size and (len(data) == read_limit or previous and len(entries) >= query.limit):
                more = True
    for identity, position in old.items():
        if identity not in available and position['offset'] < position['size']:
            reset = True
    if previous:
        # Preserve positions for sources not visited because the response filled.
        for identity, position in old.items():
            if identity not in positions and identity in available:
                positions[identity] = position
    entries.sort(key=lambda entry: entry['timestamp'])
    if not previous:
        entries = entries[-query.limit:]
    payload = {'query': signature, 'files': positions}
    return dict(entries=entries, cursor=signer.dumps(payload), limited=limited, reset=reset,
                more=more, unparsed=unparsed, start=query.start.isoformat(), end=query.end.isoformat())
