"""Bounded, non-PTY SSH execution using Roxy-WI's existing credentials."""
import select
import shlex
import time


class RemoteError(RuntimeError):
    pass


class Remote:
    def __init__(self, server):
        self.server = server

    def run(self, argv, *, data=None, timeout=45, allowed=(0,)):
        from app.modules.server.ssh import ssh_connect

        with ssh_connect(self.server.ip, connect_timeout=8, banner_timeout=15) as connection:
            channel = connection.ssh.get_transport().open_session(timeout=8)
            channel.settimeout(timeout)
            try:
                channel.exec_command(shlex.join(['sudo', '-n', '--', *argv]))
                if data is not None:
                    channel.sendall(data.encode('utf-8'))
                channel.shutdown_write()
                output, errors = bytearray(), bytearray()
                deadline = time.monotonic() + timeout
                while True:
                    if channel.recv_ready():
                        output.extend(channel.recv(65536))
                    if channel.recv_stderr_ready():
                        errors.extend(channel.recv_stderr(65536))
                    if len(output) + len(errors) > 2 * 1024 * 1024:
                        raise RemoteError('Remote output exceeded the size limit')
                    if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                        break
                    if time.monotonic() >= deadline:
                        raise RemoteError('Remote operation timed out; inspect cluster state before retrying')
                    select.select([channel], [], [], 0.1)
                code = channel.recv_exit_status()
                if code not in allowed:
                    # stderr may contain resource passwords or complete CIB fragments.
                    raise RemoteError(f'Cluster command failed (exit {code}); inspect the node journal')
                return output.decode('utf-8', errors='replace')
            finally:
                channel.close()
