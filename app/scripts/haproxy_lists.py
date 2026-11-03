"""Bounded list-file operations, executed over the existing SSH transport.

The controller supplies discovered configuration files and a managed root.
Writes compare revisions under the same remote lock as configuration changes.
This module also supplies atomic local writes; importing it has no side effects.
"""

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Optional

LIMIT = 256 * 1024


def digest(content: Optional[str]) -> str:
    """Distinguish a missing file from an existing empty file."""
    return hashlib.sha256(('missing' if content is None else 'file:' + content).encode()).hexdigest()


def read_file(path: Path, *, limit: int = LIMIT) -> Optional[str]:
    if not path.exists():
        return None
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError('file_too_large')
    return value.decode('utf-8')


def write_file(path: Path, content: str, *, mode: int = 0o644) -> None:
    """Atomically replace a file while retaining its existing ownership/mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = path.stat() if path.exists() else None
    descriptor, temporary = tempfile.mkstemp(prefix='.roxywi-list-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(metadata.st_mode) if metadata else mode)
        if metadata and hasattr(os, 'chown'):
            os.chown(temporary, metadata.st_uid, metadata.st_gid)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def list_path(root: Path, color: str, name: str) -> Path:
    if color not in ('black', 'white') or Path(name).name != name or not name.endswith('.lst'):
        raise ValueError('invalid_path')
    path = root / color / name
    if path.is_symlink() or path.parent.is_symlink() or root not in path.resolve().parents:
        raise ValueError('invalid_path')
    return path


def inspect_files(data: dict) -> dict:
    root = Path(data['root']).resolve()
    configs = {}
    total = 0
    for filename in data['files']:
        path = Path(filename).resolve()
        if str(path) != str(Path(data['main']).resolve()) and root not in path.parents:
            raise ValueError('invalid_path')
        content = read_file(path, limit=1024 * 1024)
        if content is None:
            raise ValueError('configuration_changed')
        total += len(content.encode())
        if total > 1024 * 1024:
            raise ValueError('file_too_large')
        configs[str(path)] = content
    names = []
    for color in ('black', 'white'):
        directory = root / color
        if directory.is_symlink():
            raise ValueError('invalid_path')
        if directory.exists():
            names.extend({'color': color, 'name': path.name} for path in directory.glob('*.lst')
                         if path.is_file() and not path.is_symlink())
    result = {'files': names, 'configs': configs, 'runtime_root': str(root)}
    if data.get('container'):
        # Embedded connector is provided by the controller, including rootless Podman.
        record = module.container_state(data['runtime'], data['container'])
        matches = [mount for mount in record.get('Mounts', []) if mount.get('Type') == 'bind'
                   and mount.get('RW') and (root == Path(mount['Source']).resolve()
                   or Path(mount['Source']).resolve() in root.parents)]
        if not matches:
            raise ValueError('persistent_mount_required')
        mount = max(matches, key=lambda item: len(item['Source']))
        result['runtime_root'] = str(Path(mount['Destination']) / root.relative_to(Path(mount['Source']).resolve()))
        if data.get('name'):
            runtime_path = Path(result['runtime_root']) / data['color'] / data['name']
            candidates = [item for item in record['Mounts'] if Path(item['Destination']) == runtime_path
                          or Path(item['Destination']) in runtime_path.parents]
            mounted = max(candidates, key=lambda item: len(item['Destination']))
            source = Path(mounted['Source']).resolve()
            actual = source / runtime_path.relative_to(Path(mounted['Destination']))
            if (not mounted.get('RW') or mounted.get('Type') != 'bind' or not source.is_dir()
                    or actual != root / data['color'] / data['name']):
                raise ValueError('persistent_mount_required')
    if data.get('name'):
        path = list_path(root, data['color'], data['name'])
        result['content'] = read_file(path)
    return result


def change_file(data: dict) -> dict:
    path = list_path(Path(data['root']).resolve(), data['color'], data['name'])
    for filename, expected in data.get('expected_configs', {}).items():
        if digest(read_file(Path(filename), limit=1024 * 1024)) != expected:
            return {'error': 'changed'}
    if digest(read_file(path)) != data['expected']:
        return {'error': 'changed'}
    if data['operation'] == 'delete':
        if path.exists():
            path.unlink()
    else:
        content = data['content']
        if len(content.encode()) > LIMIT:
            raise ValueError('file_too_large')
        write_file(path, content)
    return {'status': 'ok'}


def main() -> None:
    import fcntl

    data = json.load(sys.stdin)
    with open('/var/lock/roxywi-haproxy-config.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            result = inspect_files(data) if data['operation'] == 'inspect' else change_file(data)
        except (ValueError, OSError, UnicodeError) as exc:
            # Never return file contents or command output in an error.
            result = {'error': str(exc) if isinstance(exc, ValueError) and str(exc) in {
                'invalid_path', 'file_too_large', 'configuration_changed', 'persistent_mount_required'
            } else 'file_operation_failed'}
        print(json.dumps(result))


if __name__ == '__main__':
    main()
