"""Fixed Linux probe; only sanitized VRRP states leave the managed host.

This module uses the standard library because its source runs through SSH.
Keepalived's default USR1 dump works without optional JSON/SNMP/DBus builds.
"""
import ctypes
import errno
import os
from pathlib import Path
import re
import select
import signal
import stat
import struct
import subprocess
import time
from typing import List, Optional, Tuple


def parse_instances(text: str) -> List[dict]:
    """Extract every instance; never accept a truncated or ambiguous dump."""
    instances = []
    for block in re.split(r'^\s*VRRP Instance\s*=\s*', text, flags=re.M)[1:]:
        name, _, details = block.partition('\n')
        states = re.findall(r'^\s*State\s*=\s*(\S+)\s*$', details, re.M)
        if len(states) != 1 or states[0] not in ('MASTER', 'BACKUP', 'FAULT', 'INIT'):
            raise ValueError('Incomplete or unsupported VRRP state')
        instances.append(dict(name=name.strip(), state=states[0]))
    if not instances or len(instances) > 1024:
        raise ValueError('Keepalived did not report its VRRP instances')
    return instances


def native_state() -> Tuple[bool, int]:
    """A failed query is unknown; only a loaded, stopped unit is DOWN."""
    result = subprocess.run(
        ['systemctl', 'show', 'keepalived.service', '--property=LoadState,ActiveState,MainPID'],
        check=True, capture_output=True, text=True, timeout=5,
    )
    properties = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if properties.get('LoadState') != 'loaded':
        raise ValueError('Keepalived unit is not loaded')
    pid = int(properties.get('MainPID', '0'))
    if properties.get('ActiveState') in ('inactive', 'failed') and pid == 0:
        return False, 0
    if properties.get('ActiveState') != 'active' or pid <= 0:
        raise ValueError('Keepalived unit is transitioning')
    return True, pid


def process_identity(pid: int) -> str:
    """Check executable and start time before signalling or accepting a dump."""
    process = Path('/proc', str(pid))
    if Path(os.readlink(process / 'exe')).name != 'keepalived':
        raise ValueError('Keepalived process identity changed')
    return (process / 'stat').read_text().rsplit(')', 1)[1].split()[19]


def read_dump(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'r') as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1048576:
            raise ValueError('Unsupported Keepalived dump')
        text = stream.read(1048577)
        if len(text) > 1048576:
            raise ValueError('Keepalived dump exceeded its size limit')
        return text


def signal_dump(pid: int, identity: str) -> None:
    """Pin the process on supported kernels; recheck identity on older hosts."""
    descriptor = None
    if hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'):
        try:
            descriptor = os.pidfd_open(pid)
        except OSError as error:
            if error.errno != errno.ENOSYS:
                raise
    try:
        if process_identity(pid) != identity:
            raise ValueError('Keepalived process changed before the signal')
        if descriptor is not None:
            signal.pidfd_send_signal(descriptor, signal.SIGUSR1)
        else:
            os.kill(pid, signal.SIGUSR1)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def fresh_dump(pid: int) -> List[dict]:
    """Wait for a fresh close-write event instead of reading an old/partial file."""
    import fcntl

    # One lock per process across all Roxy-WI callers/controllers. /run is root
    # owned; the file must remain present so waiters always lock the same inode.
    descriptor = os.open(f'/run/roxy-wi-keepalived-{pid}.lock',
                         os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as lock:
        deadline = time.monotonic() + 10
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Keepalived probe is busy')
                time.sleep(0.1)
        identity = process_identity(pid)
        # Also works with systemd PrivateTmp and container mount namespaces.
        path = Path('/proc', str(pid), 'root/tmp/keepalived.data')
        libc = ctypes.CDLL(None, use_errno=True)
        watcher = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if watcher < 0:
            raise OSError(ctypes.get_errno(), 'Cannot watch Keepalived dump')
        try:
            if libc.inotify_add_watch(watcher, os.fsencode(path.parent), 0x8) < 0:
                raise OSError(ctypes.get_errno(), 'Cannot watch Keepalived dump directory')
            signal_dump(pid, identity)
            while time.monotonic() < deadline:
                if not select.select([watcher], [], [], 0.1)[0]:
                    continue
                events = os.read(watcher, 65536)
                offset = 0
                while offset < len(events):
                    _, mask, _, size = struct.unpack_from('iIII', events, offset)
                    filename = events[offset + 16:offset + 16 + size].split(b'\0', 1)[0]
                    offset += 16 + size
                    if mask & 0x8 and filename == b'keepalived.data':
                        metadata = path.lstat()
                        try:
                            instances = parse_instances(read_dump(path))
                        finally:
                            # The dump may contain auth_pass. Remove only the
                            # exact fresh file we read, not a later writer's dump.
                            try:
                                current = path.lstat()
                                if (current.st_ino, current.st_size, current.st_mtime_ns) == (
                                        metadata.st_ino, metadata.st_size, metadata.st_mtime_ns):
                                    path.unlink()
                            except FileNotFoundError:
                                pass  # Another dump reader already removed it.
                        if process_identity(pid) != identity:
                            raise ValueError('Keepalived restarted during the probe')
                        return instances
            raise TimeoutError('Keepalived did not produce a fresh state dump')
        finally:
            os.close(watcher)


def collect(container: Optional[dict] = None) -> dict:
    """Observe a systemd service or an already inspected rootful container."""
    if container is None:
        running, pid = native_state()
    else:
        state = container['State']
        running, pid = state['Running'], int(state.get('Pid', 0))
        if state.get('Restarting') or state.get('Paused'):
            raise ValueError('Keepalived container is transitioning')
        if running and (pid <= 0 or container.get('HostConfig', {}).get('NetworkMode') != 'host'):
            raise ValueError('Keepalived requires a rootful host-network container')
    if not running:
        return dict(service='DOWN', instances=[])
    instances = fresh_dump(pid)
    if container is None and native_state() != (True, pid):
        raise ValueError('Keepalived restarted during the probe')
    return dict(service='UP', instances=instances)
