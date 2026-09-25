"""Read-only, bounded service-log reader sent over SSH; needs only Python 3.

Each invocation opens regular files, returns complete lines and byte positions,
then exits. Nothing is installed on the managed server. Cursor signing and
authorization belong to the web application, not this transport helper.
"""
import base64
import hashlib
import json
import os
import stat
import sys
from collections import deque

SNAPSHOT_BYTES = 4 * 1024 * 1024
FOLLOW_BYTES = 256 * 1024
MAX_LINE = 64 * 1024
MAX_FILES = 16
MAX_DIRECTORY_ENTRIES = 4096
MAX_INITIAL_RECORDS = 10000


def identity(info):
    return '{}:{}'.format(info.st_dev, info.st_ino)


def anchor(stream, offset):
    stream.seek(max(0, offset - 64))
    return hashlib.sha256(stream.read(min(offset, 64))).hexdigest()


def open_regular(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                         | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0))
    stream = os.fdopen(descriptor, 'rb')
    info = os.fstat(stream.fileno())
    if not stat.S_ISREG(info.st_mode):
        stream.close()
        raise ValueError('Not a regular log file')
    return stream, info


def candidates(path):
    """Keep the active file and recent uncompressed rotations, without globbing."""
    directory, name = os.path.split(path)
    files, limited = [], False
    try:
        active = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(active.st_mode):
            raise ValueError('Not a regular log file')
    except FileNotFoundError:
        active = None  # rename/create rotation can temporarily remove the path.
    with os.scandir(directory) as items:
        for number, item in enumerate(items):
            if number >= MAX_DIRECTORY_ENTRIES:
                limited = True
                break
            if not item.name.startswith((name + '.', name + '-')) or item.name.endswith(('.gz', '.xz', '.bz2', '.zst')):
                continue
            try:
                info = os.stat(item.path, follow_symlinks=False)
            except FileNotFoundError:
                continue  # Rotation between readdir and stat.
            if stat.S_ISREG(info.st_mode):
                files.append((item.path, info))
    # Hard links must not make one inode appear twice in the same response.
    files = list({identity(info): (filename, info) for filename, info in files
                  if active is None or identity(info) != identity(active)}.values())
    files.sort(key=lambda pair: (pair[1].st_mtime_ns, pair[0]), reverse=True)
    limited |= len(files) > MAX_FILES - 1
    files = files[:MAX_FILES - 1]
    if active is not None:
        files.append((path, active))
    return files, active, limited


def read_log(path, previous=None, limit=100):
    if not os.path.isabs(path) or '\0' in path or not 1 <= limit <= 1000:
        raise ValueError('Invalid log request')
    files, active, limited = candidates(path)
    if previous is None and active is None:
        raise FileNotFoundError('Log file does not exist')
    old = previous['files'] if previous is not None else {}
    active_id = identity(active) if active is not None else None
    available = {identity(info) for _, info in files}
    reset = any(key not in available and (key == previous.get('active') or pos['offset'] < pos['size'])
                for key, pos in old.items()) if previous else False
    # Drain rotations first. Stable inode order from the cursor takes precedence
    # over mtime: a writer may still append to a renamed file after rotation.
    old_order = {key: index for index, key in enumerate(old)}
    files.sort(key=lambda pair: (identity(pair[1]) == active_id,
                               old_order.get(identity(pair[1]), MAX_FILES), pair[1].st_mtime_ns))
    positions, chunks = {}, deque(maxlen=MAX_INITIAL_RECORDS)
    budget = SNAPSHOT_BYTES if previous is None else FOLLOW_BYTES
    remaining = None if previous is None else limit
    more = False
    for filename, listed in files:
        try:
            stream, info = open_regular(filename)
        except FileNotFoundError:
            # Keep the position: the next invocation will locate its new name.
            if identity(listed) in old:
                positions[identity(listed)] = old[identity(listed)]
            more = True
            continue
        with stream:
            key = identity(info)
            if key != identity(listed):
                if identity(listed) in old:
                    positions[identity(listed)] = old[identity(listed)]
                more = True
                continue
            position = old.get(key)
            # copytruncate creates a new inode containing the old file. Resume
            # that copy at the old offset instead of duplicating its history.
            if previous and position is None and key != active_id and active_id == previous.get('active'):
                original = old.get(previous.get('active'))
                if original and original['offset'] > 0 and info.st_size >= original['offset']:
                    if anchor(stream, original['offset']) == original['anchor']:
                        position = original
            dropping = False
            if position is not None:
                offset = position['offset']
                dropping = position['dropping']
                if offset > info.st_size or anchor(stream, offset) != position['anchor']:
                    offset, dropping, reset = 0, False, True
            elif previous is not None:
                offset = 0
            elif key != active_id:
                # A new view starts at the current file, not historical archives.
                offset = info.st_size
            else:
                offset = max(0, info.st_size - budget)
                if offset:
                    limited = True
                    stream.seek(offset - 1)
                    dropping = stream.read(1) != b'\n'
            prefix_offset = offset
            stream.seek(max(0, offset - 64))
            prefix = stream.read(min(offset, 64))
            prefix_anchor = hashlib.sha256(prefix).hexdigest()
            stream.seek(offset)
            count = min(budget, max(0, info.st_size - offset))
            data = stream.read(count) if remaining != 0 else b''
            budget -= len(data)
            base, index = offset, 0
            if dropping:
                newline = data.find(b'\n')
                index = len(data) if newline < 0 else newline + 1
                offset, dropping = base + index, newline < 0
            while index < len(data) and remaining != 0:
                newline = data.find(b'\n', index)
                if newline < 0:
                    if len(data) - index > MAX_LINE:
                        offset, dropping, limited = base + len(data), True, True
                    break  # Leave an incomplete ordinary record for the next poll.
                raw = data[index:newline + 1]
                index = newline + 1
                offset = base + index
                if len(raw) - 1 > MAX_LINE:
                    limited = True
                    continue
                if len(chunks) == chunks.maxlen:
                    limited = True
                chunks.append(raw)
                if remaining is not None:
                    remaining -= 1
            end_anchor = anchor(stream, offset)
            # A concurrent truncate/overwrite must not sign an old byte offset
            # with a new file's contents. Retry from the browser's last cursor.
            consumed = offset - base
            expected = data[consumed - 64:consumed] if consumed >= 64 else (prefix + data[:consumed])[-64:]
            if anchor(stream, prefix_offset) != prefix_anchor or end_anchor != hashlib.sha256(expected).hexdigest():
                raise OSError('Log changed during the read; retry')
            positions[key] = dict(offset=offset, size=info.st_size, anchor=end_anchor, dropping=dropping)
            # Do not busy-poll a partial line. Otherwise drain a bounded backlog
            # promptly, without consuming records omitted by the response limit.
            if offset < info.st_size and (remaining == 0 or count == 0 or base + len(data) < info.st_size or offset == base + len(data)):
                more = True
    if len(positions) > MAX_FILES:
        raise OSError('Rotation changed too many files; retry the read')
    return dict(data=base64.b64encode(b''.join(chunks)).decode('ascii'),
                position=dict(files=positions, active=active_id), limited=limited, reset=reset, more=more)


def main():
    try:
        request = json.loads(sys.stdin.buffer.read(40001))
        result = read_log(request['path'], request.get('position'), int(request.get('limit', 100)))
    except (OSError, ValueError, KeyError, TypeError):
        # Never return a path, log contents or a traceback from privileged code.
        print(json.dumps({'error': 'Cannot read the service log'}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
