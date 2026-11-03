"""One read/validate/apply/persist workflow for managed HAProxy IP lists."""

from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from flask import g
from pydantic import ValidationError

from app.modules.common.execution_context import group_settings
from app.modules.common.file_lock import file_lock
from app.modules.config import deployment_policy, haproxy_files
from app.modules.config.runtime import escape_runtime_argument
from app.modules.config.viewer import haproxy_sections
from app.modules.connectors import containers
from app.modules.db import service as service_sql, sql
from app.modules.db.db_model import Server
from app.modules.pacemaker.remote import Remote
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi import common
from app.modules.roxywi.error_handler import safe_error_message
from app.modules.roxywi.exception import RoxywiPublicError, RoxywiPermissionError
from app.modules.server import server as server_mod
from app.modules.service import container_settings, action as service_action
from app.modules.service.haproxy_targets import linked_servers, lock_servers
from app.modules.service.ha_mutation import mutation
from app.modules.service.haproxy import haproxy_line_tokens
from app.modules.service.haproxy_list_models import ListChange, ListContent, ListIdentity, entries
from app.modules.service.managed_runtime import execute_runtime_command
from app.scripts import haproxy_lists as list_files


class ListError(RoxywiPublicError):
    def __init__(self, code: str, status: int = 409, *, nodes: list | None = None):
        super().__init__(code)
        self.code, self.status, self.nodes = code, status, nodes or []


def local_path(group: int, identity: ListIdentity) -> Path:
    """Resolve all catalog access through the same path and symlink checks."""
    root = Path(GetConfigVar().get_config_var('main', 'lib_path')).resolve() / 'lists' / str(int(group))
    if root.is_symlink() or root.parent.is_symlink():
        raise ListError('invalid_path')
    return list_files.list_path(root, identity.color, identity.name)


def authorize(address: str, group: int, *, write: bool = False) -> Server:
    node = common.require_server_access(str(address))
    if int(node.group_id) != int(group):
        raise RoxywiPermissionError('Server does not belong to the list group')
    if not node.enabled or node.type_ip or not node.haproxy:
        raise ListError('unsupported_target')
    if write:
        role = int(g.user_params['role'])
        if role > 3 or (node.protected and role > 2):
            raise RoxywiPermissionError('Proxy list update permission is required')
        deployment_policy.require_direct_deployment_for_server(node.ip, 'haproxy', action='save')
    return node


def targets(address: str, group: int, *, write: bool = False) -> list[Server]:
    node = authorize(address, group, write=write)
    return [node, *[authorize(target.ip, group, write=write) for target in linked_servers(node)[1:]]]


@contextmanager
def locked(address: str, group: int, identity: ListIdentity):
    nodes = targets(address, group, write=True)
    root = local_path(group, identity).parent.parent
    root.mkdir(parents=True, exist_ok=True)
    with mutation(server_ids=[node.server_id for node in nodes], group_id=group), ExitStack() as stack:
        # Catalog files are shared by the group, including unrelated HAProxy nodes.
        stack.enter_context(file_lock(root / '.lists.lock', blocking=False))
        stack.enter_context(lock_servers(nodes, blocking=False))
        current = targets(address, group, write=True)
        if [node.server_id for node in current] != [node.server_id for node in nodes]:
            raise ListError('changed')
        yield current


def remote(node: Server, operation: str, **data) -> dict:
    source = Path(list_files.__file__).read_text(encoding='utf-8')
    if service_sql.select_service_setting(node.server_id, 'haproxy', 'dockerized') == '1':
        data.update(container=container_settings.name(node.server_id, 'haproxy'),
                    runtime=container_settings.runtime(node.server_id, 'haproxy'))
        source = containers.embedded() + source
    data.update(operation=operation, root=sql.get_setting('haproxy_dir', group_id=node.group_id))
    result = json.loads(Remote(node).run(['python3', '-c', source], data=json.dumps(data), timeout=45))
    if result.get('error'):
        raise ListError(result['error'], 409 if result['error'] == 'changed' else 502)
    return result


def read_runtime(node: Server, command: str) -> str:
    reply = execute_runtime_command(node.ip, int(sql.get_setting('haproxy_sock_port', group_id=node.group_id)), command)
    if reply.strip().startswith('Permission denied'):
        raise ListError('runtime_permissions', 403)
    return reply


def runtime_files(reply: str) -> dict[str, str]:
    """Parse filenames including spaces; ignore unnamed inline ACL expressions."""
    result = {}
    for line in reply.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        match = re.match(r'^\s*(\d+)\s+\((.*?)\)\s', line)
        if not match:
            raise ListError('invalid_response', 502)
        if match[2]:
            result[match[2]] = match[1]
    return result


def runtime_entries(reply: str) -> str:
    values = []
    for line in reply.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        match = re.fullmatch(r'0x[0-9a-fA-F]+\s+(.+)', line.strip())
        if not match:
            raise ListError('invalid_response', 502)
        values.append(match[1])
    return ListContent(content='\n'.join(values)).content


def process(node: Server) -> dict:
    info = dict(line.split(':', 1) for line in read_runtime(node, 'show info').splitlines() if ':' in line)
    try:
        return {'pid': int(info['Pid']), 'uptime': int(info['Uptime_sec']), 'version': info['Version'].strip()}
    except (KeyError, ValueError):
        raise ListError('invalid_response', 502) from None


def usage(configs: dict, path: str) -> list[str]:
    """Report references in every discovered startup file, including inline ACLs."""
    result = []
    for filename, content in configs.items():
        lines = content.splitlines()
        for section in haproxy_sections(content):
            for number in range(section['start'], section['end']):
                tokens = haproxy_line_tokens(lines[number])
                # A basename/relative reference is conservatively considered in use.
                if any(token.removeprefix('opt@') in {path, PurePosixPath(path).name,
                       '/'.join(PurePosixPath(path).parts[-2:])} or path in token for token in tokens):
                    result.append(f'{section["title"] or "global"} ({PurePosixPath(filename).name}:{number + 1})')
    return result


def inspect_node(node: Server, identity: ListIdentity | None = None) -> dict:
    with group_settings(node.group_id):
        discovery = haproxy_files.discover_sources(node.ip, node.server_id)
        if discovery['state'] == 'error':
            raise ListError('configuration_unavailable', 502)
        parameters = {'files': discovery['files'], 'main': sql.get_setting('haproxy_config_path')}
        if identity:
            parameters.update(color=identity.color, name=identity.name)
        before = process(node)
        disk = remote(node, 'inspect', **parameters)
        acls = runtime_files(read_runtime(node, 'show acl'))
        maps = runtime_files(read_runtime(node, 'show map'))
        result = {'server': node.ip, 'files': disk['files'], 'runtime_root': disk['runtime_root'],
                  'parameters': parameters, 'configs': disk['configs'], 'process': before, 'acls': acls}
        if identity:
            path = str(PurePosixPath(disk['runtime_root']) / identity.color / identity.name)
            acl_id = acls.get(path)
            active = runtime_entries(read_runtime(node, f'show acl #{acl_id}')) if acl_id is not None else None
            result.update(content=disk['content'], runtime_content=active, acl_id=acl_id,
                          used=usage(disk['configs'], path), shared_map=path in maps)
        after = process(node)
        if before['pid'] != after['pid'] or after['uptime'] < before['uptime']:
            raise ListError('changed')
        return result


def revision(local: str | None, nodes: list[dict]) -> str:
    state = [{'server': node['server'], 'pid': node['process']['pid'], 'acl_id': node['acl_id'],
              'content': node['content'], 'runtime': entries(node['runtime_content'] or ''),
              'configs': node['configs'], 'shared_map': node['shared_map'], 'root': node['runtime_root']}
             for node in nodes]
    return hashlib.sha256(json.dumps([local, state], sort_keys=True).encode()).hexdigest()


def catalog(address: str, group: int) -> dict:
    nodes = targets(address, group)
    state = inspect_node(nodes[0])
    identities = {(item['color'], item['name']) for item in state['files']}
    for color in ('black', 'white'):
        directory = local_path(group, ListIdentity(color=color, name='catalog.lst')).parent
        identities.update((color, path.name) for path in directory.glob('*.lst') if path.is_file())
    for path in state['acls']:
        relative = PurePosixPath(path)
        if str(relative.parent.parent) == state['runtime_root'] and relative.parent.name in ('black', 'white'):
            identities.add((relative.parent.name, relative.name))
    items = []
    for color, name in sorted(identities):
        identity = ListIdentity(color=color, name=name)
        content = list_files.read_file(local_path(group, identity))
        path = str(PurePosixPath(state['runtime_root']) / color / name)
        count = sum(bool(line.strip()) and not line.lstrip().startswith('#') for line in (content or '').splitlines())
        items.append(dict(name=name, color=color, count=count if content is not None else None,
                          used=usage(state['configs'], path), state='loaded' if path in state['acls'] else 'unused'))
    return {'items': items, 'targets': [node.ip for node in nodes]}


def detail(address: str, group: int, identity: ListIdentity) -> dict:
    nodes = [inspect_node(node, identity) for node in targets(address, group)]
    content = list_files.read_file(local_path(group, identity))
    public = []
    for node in nodes:
        active = node['runtime_content']
        try:
            synced = (node['content'] is not None and content is not None
                      and ListContent(content=node['content']).content == ListContent(content=content).content
                      and (active is None or entries(active) == entries(content)))
        except ValidationError:
            # Existing malformed files must remain readable so the editor can repair them.
            synced = False
        public.append({key: node[key] for key in ('server', 'content', 'runtime_content', 'used', 'shared_map')}
                      | {'state': 'synced' if synced else 'different'})
    return {**identity.model_dump(), 'content': content, 'nodes': public, 'revision': revision(content, nodes)}


def prepare(node: Server, state: dict, content: str) -> str | None:
    if state['acl_id'] is None:
        if state['used']:
            raise ListError('reload_required')
        return None
    version_match = re.match(r'^(\d+)\.(\d+)', state['process']['version'])
    if not version_match or tuple(map(int, version_match.groups())) < (2, 4):
        raise ListError('runtime_version')
    acl = '#' + state['acl_id']
    match = re.fullmatch(r'New version created: (\d+)', read_runtime(node, 'prepare acl ' + acl).strip())
    if not match:
        raise ListError('command_rejected', 502)
    version = match[1]
    # Batch bounded single-line commands; ACL add does not support map-style payloads.
    batch = []
    for value in entries(content):
        command = f'add acl @{version} {acl} {escape_runtime_argument(value)}'
        if sum(map(len, batch)) + len(command) > 3500:
            if read_runtime(node, ';'.join(batch)).strip():
                raise ListError('command_rejected', 502)
            batch = []
        batch.append(command)
    if batch and read_runtime(node, ';'.join(batch)).strip():
        raise ListError('command_rejected', 502)
    prepared = runtime_entries(read_runtime(node, f'show acl @{version} {acl}'))
    if entries(prepared) != entries(content):
        raise ListError('command_rejected', 502)
    return version


def change(address: str, group: int, body: ListChange) -> dict:
    """Prepare all nodes first, stop on uncertainty, and report each confirmed step."""
    try:
        with locked(address, group, body) as nodes:
            path = local_path(group, body)
            local = list_files.read_file(path)
            states = [inspect_node(node, body) for node in nodes]
            if revision(local, states) != body.revision:
                raise ListError('changed')
            if body.operation == 'delete':
                # The catalog belongs to a group, so also protect references on unrelated nodes.
                checked = {node.server_id for node in nodes}
                others = Server.select().where(Server.group_id == str(group), Server.haproxy == 1,
                                                Server.enabled == 1, Server.type_ip == 0)
                inspections = states + [inspect_node(authorize(node.ip, group), body) for node in others
                                        if node.server_id not in checked]
                if any(state['used'] or state['acl_id'] is not None or state['shared_map'] for state in inspections):
                    raise ListError('list_in_use')
            if any(state['shared_map'] for state in states):
                raise ListError('shared_map')
            commands = ([service_action.get_action_command('haproxy', body.apply_mode, node.server_id) for node in nodes]
                        if body.operation == 'save' and body.apply_mode != 'runtime' else [None] * len(nodes))
            versions = [prepare(node, state, body.content) if body.operation == 'save' and body.apply_mode == 'runtime' else None
                        for node, state in zip(nodes, states)]
            # Preparing versions must not mask a reload or concurrent external ACL edit.
            refreshed = [inspect_node(node, body) for node in nodes]
            if (revision(local, refreshed) != body.revision
                    or any(new['process']['uptime'] < old['process']['uptime'] for old, new in zip(states, refreshed))):
                raise ListError('changed')
            results = [{'server': node.ip, 'file': 'pending', 'runtime': 'pending'} for node in nodes]
            for node, state, version, command, result in zip(nodes, states, versions, commands, results):
                try:
                    result['file'] = 'unknown'
                    remote(node, body.operation, **state['parameters'], content=body.content,
                           expected=list_files.digest(state['content']),
                           expected_configs={name: list_files.digest(value) for name, value in state['configs'].items()})
                    result['file'] = 'deleted' if body.operation == 'delete' else 'saved'
                    if version is not None:
                        result['runtime'] = 'unknown'
                        try:
                            reply = read_runtime(node, f'commit acl @{version} #{state["acl_id"]}').strip()
                        except ListError as exc:
                            if exc.code != 'runtime_permissions':
                                raise
                            reply = exc.code
                        if reply:
                            result['runtime'] = 'failed'
                            result['file'] = 'unknown'
                            remote(node, 'delete' if state['content'] is None else 'save',
                                   **state['parameters'], content=state['content'] or '',
                                   expected=list_files.digest(body.content),
                                   expected_configs={name: list_files.digest(value)
                                                     for name, value in state['configs'].items()})
                            result['file'] = 'restored'
                            raise ListError('command_rejected', 502)
                        current = inspect_node(node, body)
                        if (current['process']['pid'] != state['process']['pid']
                                or entries(current['runtime_content'] or '') != entries(body.content)):
                            raise ListError('changed')
                        result['runtime'] = 'applied'
                    elif command:
                        result['runtime'] = 'unknown'
                        server_mod.ssh_command(node.ip, command, rc=1, timeout=60, error_context='Cannot apply HAProxy list')
                        result['runtime'] = 'applied'
                    else:
                        result['runtime'] = 'unused'
                    common.logging(node.ip, f'HAProxy list {body.operation}: {body.color}/{body.name}',
                                   keep_history=1, service='haproxy')
                except Exception as exc:
                    safe_error_message(exc)
                    raise ListError('incomplete', 502, nodes=results) from exc
            try:
                if body.operation == 'delete':
                    path.unlink(missing_ok=True)
                else:
                    list_files.write_file(path, body.content, mode=0o600)
            except OSError as exc:
                safe_error_message(exc)
                raise ListError('catalog_save_failed', 502, nodes=results) from exc
            return {'status': 'Ok', 'nodes': results}
    except BlockingIOError:
        raise ListError('busy') from None


def change_entry(address: str, group: int, body, *, delete: bool = False) -> dict:
    """Compatibility adapter; filenames and runtime IDs must identify the same ACL."""
    node = authorize(address, group, write=True)
    state = inspect_node(node, body)
    if state['acl_id'] != str(body.acl_id):
        raise ListError('changed')
    if delete:
        output = read_runtime(node, f'show acl #{body.acl_id}')
        matching = [line.split(None, 1)[1] for line in output.splitlines()
                    if line.startswith(str(body.pointer) + ' ')]
        if not matching or entries(matching[0]) != [body.entry]:
            raise ListError('changed')
    snapshot = detail(address, group, ListIdentity(color=body.color, name=body.name))
    # Do not silently discard drift while adapting a legacy single-entry request.
    if any(item['state'] != 'synced' for item in snapshot['nodes']):
        raise ListError('changed')
    content = snapshot['content'] or ''
    lines = content.splitlines()
    if delete:
        lines = [line for line in lines if line.startswith('#') or entries(line) != [body.entry]]
    elif body.entry not in entries(content):
        lines.append(body.entry)
    return change(address, group, ListChange(color=body.color, name=body.name,
                  content='\n'.join(lines), revision=snapshot['revision']))
