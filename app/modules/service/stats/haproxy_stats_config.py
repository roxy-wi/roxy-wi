"""Shared safeguards and configuration persistence for HAProxy Stats changes."""

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
import hashlib
from pathlib import Path

from app.modules.common.file_lock import file_lock
from app.modules.config import config, common as config_common, deployment_policy
from app.modules.db import server as server_sql
from app.modules.db.db_model import Server
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi import common
from app.modules.roxywi.error_handler import safe_error_message
from app.modules.roxywi.exception import RoxywiPermissionError
from app.modules.service.stats.haproxy_stats import StatsError


class ChangeError(StatsError):
    incomplete_code: str
    settings_code: str

    def __init__(self, code: str, nodes: list[dict[str, str]]) -> None:
        super().__init__(code, 502)
        self.nodes = nodes


def targets(server: Server) -> list[Server]:
    """Keep the existing selected-node -> direct replicas propagation topology."""
    nodes = {server.ip: server}
    for ip, _hostname in server_sql.is_master(server.ip):
        if ip:
            nodes[ip] = common.require_server_access(ip)
    for node in nodes.values():
        if not node.haproxy:
            raise StatsError('unsupported_target', 409)
        try:
            deployment_policy.require_direct_deployment_for_server(node.ip, 'haproxy', action='save')
        except RoxywiPermissionError as exc:
            raise StatsError('maxconn_policy', 403) from exc
    return [server, *[nodes[ip] for ip in sorted(nodes) if ip != server.ip]]


def require_targets(server: Server, expected: list[str]) -> list[Server]:
    nodes = targets(server)
    if [node.ip for node in nodes] != expected:
        raise StatsError('target_changed', 409)
    return nodes


@contextmanager
def locked_targets(server: Server, expected: list[str]) -> Iterator[list[Server]]:
    nodes = require_targets(server, expected)
    # Retain the shared lock directory for compatibility with existing workers.
    lock_dir = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'stats-maxconn-locks'
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ExitStack() as locks:
        for node in sorted(nodes, key=lambda node: node.ip):
            locks.enter_context(file_lock(lock_dir / (hashlib.sha256(node.ip.encode()).hexdigest() + '.lock')))
        # Access and topology may have changed while waiting for a lock.
        yield require_targets(server, expected)


def check_process(snapshot: dict, pid: int, uptime: int) -> None:
    if snapshot['info']['Pid'] != pid or snapshot['info']['Uptime_sec'] < uptime:
        raise StatsError('target_changed', 409)


@contextmanager
def prepared_configs(
    nodes: list[Server], prepare: Callable[[Server, list[Path], dict | None], dict],
) -> Iterator[tuple[list[dict], list[Path]]]:
    """Prepare each node and clean up files not handed over to version storage."""
    entries, paths = [], []
    try:
        for node in nodes:
            entries.append(prepare(node, paths, entries[-1] if entries else None))
        yield entries, paths
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


def download_config(node: Server, remote_path: str, paths: list[Path]) -> dict:
    path = Path(config_common.generate_config_path('haproxy', node.ip))
    paths.append(path)
    config.get_config(node.ip, str(path), config_file_name=remote_path)
    content = path.read_bytes()
    return {
        'node': node,
        'path': path,
        'remote_path': remote_path,
        'content': content,
        'digest': hashlib.sha256(content).hexdigest(),
    }


def validate_candidates(
    server: Server, expected_targets: list[str], entries: list[dict], *,
    refresh: Callable[[dict], dict], invalid_code: str,
) -> None:
    """Validate every candidate and recheck runtime/topology before the first write."""
    try:
        for entry in entries:
            config.validate_candidate_config(entry['node'].ip, str(entry['path']), 'haproxy',
                                             config_file_name=entry['remote_path'])
    except Exception as exc:
        safe_error_message(exc)
        raise StatsError(invalid_code, 409) from exc
    for entry in entries:
        before = entry['snapshot']['info']
        check_process(refresh(entry), before['Pid'], before['Uptime_sec'])
    require_targets(server, expected_targets)


def save_config(entry: dict, paths: list[Path], *, action: str = 'save', message: str) -> None:
    # The save/version workflow takes ownership of this node's candidate file.
    paths.remove(entry['path'])
    config.upload_and_restart(entry['node'].ip, str(entry['path']), action, 'haproxy',
                              config_file_name=entry['remote_path'], expected_sha256=entry['digest'],
                              version_message=message)


def apply_changes(
    entries: list[dict], paths: list[Path], *,
    apply_runtime: Callable[[dict], str] | None,
    save_settings: Callable[[dict], None], error_type: type[ChangeError],
    action: str = 'save', report_settings: bool = False,
) -> list[dict[str, str]]:
    """Apply, persist and report each node, stopping at the first uncertain result."""
    results = [{'server': entry['node'].ip, 'runtime': 'pending', 'config': 'pending'} for entry in entries]
    if report_settings:
        for result in results:
            result['settings'] = 'pending'
    for entry, result in zip(entries, results):
        node, message = entry['node'], entry['message']
        try:
            result['runtime'] = 'unknown'
            if apply_runtime is not None:
                response = apply_runtime(entry)
                response = response.strip()
                if response:
                    result['runtime'] = 'failed'
                    raise StatsError('action_permissions' if response.startswith('Permission denied') else 'command_rejected')
                result['runtime'] = 'applied'
            result['config'] = 'unknown'
            save_config(entry, paths, action=action, message=message)
            # For deletion, runtime application is confirmed by the successful reload.
            result['config'] = 'saved'
            result['runtime'] = 'applied'
            try:
                save_settings(entry)
            except Exception as exc:
                raise error_type(error_type.settings_code, results) from exc
            if report_settings:
                result['settings'] = 'saved'
            common.logging(node.ip, entry.get('success_message', message), keep_history=1, service='haproxy')
        except Exception as exc:
            safe_error_message(exc)
            status = ', '.join(f'{key}={value}' for key, value in result.items() if key != 'server')
            common.logging(node.ip, f'{message}; {status}', keep_history=1, service='haproxy')
            # Neither retries nor rollback can safely undo an unconfirmed write.
            if isinstance(exc, error_type):
                raise
            raise error_type(error_type.incomplete_code, results) from exc
    return results
