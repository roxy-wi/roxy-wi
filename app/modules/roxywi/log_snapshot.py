"""Time-filtered snapshots of managed service and package-only system logs."""
import re
import shlex
import subprocess
from pathlib import PurePosixPath

from app.modules.db import sql
from app.modules.server import ssh as ssh_mod
from app.modules.roxywi.log_query import MAX_BYTES


def filter_snapshot(data, query):
    limited = len(data) >= MAX_BYTES
    if limited:
        data = data.partition(b'\n')[2]  # tail -c can begin inside a record.
    entries, unparsed = [], 0
    for line in data.decode('utf-8', errors='replace').splitlines():
        entry, unknown = query.entry(line)
        unparsed += int(unknown)
        if entry is not None:
            entries.append(entry)
    return dict(entries=entries[-query.limit:], limited=limited, unparsed=unparsed,
                start=query.start.isoformat(), end=query.end.isoformat())


def remote_source(service, server, filename, waf):
    if service not in {'nginx', 'apache', 'haproxy', 'keepalived'}:
        raise ValueError('Unknown service')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+', server) or '..' in server:
        raise ValueError('Invalid managed server address')
    if not filename or filename in {'.', '..'} or any(char in filename for char in '/\\\0\r\n'):
        if not (waf and service == 'haproxy'):
            raise ValueError('Select a log file')
    host = server
    if waf and service == 'haproxy':
        path = '/var/log/waf.log'
    elif str(sql.get_setting('syslog_server_enable')) == '1':
        path = f'/var/log/{server}/syslog.log'
        host = sql.get_setting('syslog_server')
        if not host:
            raise ValueError('The syslog server is not configured')
    else:
        path = str(PurePosixPath(sql.get_setting(f'{service}_path_logs')) / filename)
    if not PurePosixPath(path).is_absolute():
        raise ValueError('The log directory must be an absolute path')
    return host, path


def remote_snapshot(service, server, filename, waf, query):
    host, path = remote_source(service, server, filename, waf)
    # Fixed command and bounded output. No shell regexes or user-supplied dates.
    command = f'sudo -n tail -c {MAX_BYTES} -- {shlex.quote(path)}'
    with ssh_mod.ssh_connect(host, connect_timeout=5, banner_timeout=10) as connection:
        stdin, stdout, stderr = connection.ssh.exec_command(command, timeout=10)
        stdin.close()
        try:
            data = stdout.read(MAX_BYTES + 1)
            error = stderr.read(4096)
            if stdout.channel.recv_exit_status() != 0 or error:
                raise OSError('Cannot read the remote log; check the file and SSH/sudo permissions')
        finally:
            stdout.close()
            stderr.close()
    return filter_snapshot(data, query)


def package_snapshot(source, query):
    if source == 'fail2ban.log':
        path = '/var/log/fail2ban.log'
    elif source in {'roxy-wi.error.log', 'roxy-wi.access.log'}:
        path = str(PurePosixPath(sql.get_setting('apache_log_path')) / source)
    else:
        raise ValueError('Unknown log source')
    result = subprocess.run(['sudo', '-n', 'tail', '-c', str(MAX_BYTES), '--', path],
                            capture_output=True, timeout=10, check=False)
    if result.returncode:
        raise OSError('Cannot read the log; check the file and sudo permissions')
    return filter_snapshot(result.stdout, query)
