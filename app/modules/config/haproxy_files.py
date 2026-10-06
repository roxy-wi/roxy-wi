"""HAProxy file identity and the ordered configuration sources passed with -f."""
import posixpath
import shlex
import json
from pathlib import Path
from uuid import uuid4

from flask import g, has_request_context

import app.modules.db.sql as sql
from app.modules.config.path_tokens import decode_file_path


def absolute_path(value: str) -> str:
    if not isinstance(value, str) or not value.startswith('/') or any(c in value for c in '\\\x00\r\n'):
        raise ValueError('Configuration paths must be absolute Unix paths')
    if '..' in value.split('/'):
        raise ValueError('Parent path components are not allowed')
    return posixpath.normpath(value)


def resolve_path(value: str | None = None) -> str:
    main = absolute_path(str(sql.get_setting('haproxy_config_path')))
    root = absolute_path(str(sql.get_setting('haproxy_dir')))
    if value in (None, '', 'undefined'):
        return main
    if not isinstance(value, str):
        raise ValueError('Invalid configuration file path')
    path = absolute_path(decode_file_path(value))
    if path != main and (not path.startswith(root.rstrip('/') + '/') or not path.endswith('.cfg')):
        raise ValueError('Select a .cfg file inside the HAProxy directory')
    return path


def multiple_files_enabled(server_id: int) -> bool:
    from app.modules.db.db_model import ServiceSetting
    try:
        return ServiceSetting.get((ServiceSetting.server_id == server_id) & (ServiceSetting.service == 'haproxy')
                                  & (ServiceSetting.setting == 'multiple_config_files')).value == '1'
    except ServiceSetting.DoesNotExist:
        return False


def discover_sources(server_ip: str, server_id: int = None, *, dockerized: bool = None) -> dict:
    from app.modules.db import server as server_sql, service as service_sql
    from app.modules.server import server as server_mod
    from app.modules.service.common import get_correct_service_name
    if server_id is None:
        server_id = server_sql.get_server_by_ip(server_ip).server_id
    if dockerized is None:
        dockerized = service_sql.select_service_setting(server_id, 'haproxy', 'dockerized') == '1'
    mode = 'docker' if dockerized else 'systemd'
    key = (server_ip, mode)
    cache = g.setdefault('haproxy_config_sources', {}) if has_request_context() else {}
    if key in cache:
        return cache[key]
    name = sql.get_setting('haproxy_container_name') if dockerized else get_correct_service_name('haproxy', server_id)
    script = Path(__file__).with_name('haproxy_discovery.py').read_text(encoding='utf-8')
    command = shlex.join(['sudo', '-n', 'python3', '-c', script, mode, name,
                          absolute_path(sql.get_setting('haproxy_dir')), resolve_path()])
    try:
        output = server_mod.ssh_command(server_ip, command, rc=1, timeout=45,
                                       error_context='Cannot inspect HAProxy startup settings')
        result = json.loads(output)
        if result.get('state') not in ('ready', 'single', 'error'):
            raise ValueError('Invalid discovery result')
        if (not isinstance(result.get('sources'), list) or not isinstance(result.get('files'), list)
                or not isinstance(result.get('code'), str) or not isinstance(result.get('verified_running'), bool)):
            raise ValueError('Incomplete discovery result')
        for source in result['sources']:
            if not isinstance(source, dict) or source.get('kind') not in ('file', 'directory'):
                raise ValueError('Invalid configuration source')
            absolute_path(source.get('path'))
            absolute_path(source.get('runtime_path'))
        for path in result['files']:
            resolve_path(path)
        if result['state'] != 'error' and not result['sources']:
            raise ValueError('No configuration sources returned')
        result['mode'] = mode
    except Exception as exc:
        message = str(exc).lower()
        code = 'connection_failed'
        if any(word in message for word in ('permission denied', 'password', 'not allowed', 'sudoers')):
            code = 'permission_denied'
        elif 'python3' in message and ('not found' in message or 'no such file' in message):
            code = 'tool_missing'
        elif isinstance(exc, (ValueError, TypeError, AttributeError)):
            code = 'inspection_failed'
        result = {'state': 'error', 'code': code, 'mode': mode, 'sources': [], 'files': [], 'verified_running': False}
    result['name'] = name
    example_main = next((item['runtime_path'] for item in result['sources'] if item['kind'] == 'file'),
                        '/usr/local/etc/haproxy/haproxy.cfg' if dockerized else resolve_path())
    example_dir = posixpath.join(posixpath.dirname(example_main), 'conf.d')
    result['example'] = shlex.join(['-f', example_main, '-f', example_dir])
    cache[key] = result
    return result


def config_sources(server_ip: str, server_id: int = None) -> list[str]:
    from app.modules.db import server as server_sql
    if server_id is None:
        server_id = server_sql.get_server_by_ip(server_ip).server_id
    if not multiple_files_enabled(server_id):
        return [resolve_path()]
    result = discover_sources(server_ip, server_id)
    if result['state'] == 'error':
        raise ValueError('Cannot determine HAProxy configuration sources (%s). Check the HAProxy service settings.' % result['code'])
    return [absolute_path(item['path']) for item in result['sources']]


def read_path_command(target: str, *, missing_ok: bool = False) -> str:
    script = '''set -eu
root=$(realpath -m -- "$1")
main=$(realpath -m -- "$2")
target=$(realpath -m -- "$3")
case "$target" in "$main"|"$root"/*.cfg) ;;
*) echo 'Selected configuration resolves outside the HAProxy directory' >&2; exit 1 ;; esac
if [ ! -e "$target" ] && [ "$4" = 1 ]; then printf '__ROXYWI_MISSING_CONFIG__'; exit 0; fi
test -f "$target"
printf '%s' "$target"'''
    return shlex.join(['sudo', 'sh', '-c', script, 'roxywi-read-config',
                       absolute_path(sql.get_setting('haproxy_dir')), resolve_path(), resolve_path(target), '1' if missing_ok else '0'])


def check_command(server_ip: str, server_id: int, container: str | None = None) -> str:
    sources = config_sources(server_ip, server_id)
    if container:
        return candidate_command(resolve_path(), '', 'check', sources=sources, container=container)
    args = ['haproxy', '-c']
    for source in sources:
        args.extend(['-f', source])
    args.insert(0, 'sudo')
    return shlex.join(args)


def candidate_command(target: str, candidate: str, action: str, *, sources: list[str], container: str = '', reload_command: str = '') -> str:
    """Serialize validation and replacement on the target, including across workers."""
    if action not in ('test', 'save', 'reload', 'restart', 'check'):
        raise ValueError('Unsupported configuration action')
    script = Path(__file__).with_name('haproxy_candidate.sh').read_text(encoding='utf-8')
    args = [resolve_path(target), candidate, action, container or '', reload_command,
            absolute_path(sql.get_setting('haproxy_dir')), resolve_path(), uuid4().hex, *sources]
    return shlex.join(['sudo', 'flock', '-w', '30', '/var/lock/roxywi-haproxy-config.lock',
                       'sh', '-c', script, 'roxywi-haproxy', *args])
