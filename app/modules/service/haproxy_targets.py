"""Shared HAProxy target discovery and locks for config and list changes."""

from contextlib import ExitStack, contextmanager
import hashlib
from pathlib import Path

from app.modules.common.file_lock import file_lock
from app.modules.db import server as server_sql
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi import common


def linked_servers(server) -> list:
    """Return the selected server followed by its accessible direct replicas."""
    nodes = {server.ip: server}
    for ip, _hostname in server_sql.is_master(server.ip):
        if ip:
            nodes[ip] = common.require_server_access(ip)
    return [server, *[nodes[ip] for ip in sorted(nodes) if ip != server.ip]]


@contextmanager
def lock_servers(nodes: list, *, blocking: bool = True):
    """Keep the existing lock identities and acquire them in a stable order."""
    directory = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'stats-maxconn-locks'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ExitStack() as stack:
        for node in sorted(nodes, key=lambda item: item.ip):
            path = directory / (hashlib.sha256(node.ip.encode()).hexdigest() + '.lock')
            stack.enter_context(file_lock(path, blocking=blocking))
        yield
