"""Build an NGINX virtual server -> location -> upstream -> server graph."""

import ipaddress
import shlex

import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.db.sql as sql
import app.modules.server.server as server_mod


_PASS_DIRECTIVES = {'proxy_pass', 'fastcgi_pass', 'uwsgi_pass', 'scgi_pass', 'grpc_pass'}
_SCOPES = {'http', 'stream', 'mail'}


def _tokenize_config(config_text: str) -> list[str]:
    """Tokenize NGINX syntax without interpreting variables or regular expressions."""
    tokens = []
    current = []
    quote = None
    escaped = False
    comment = False

    def flush() -> None:
        if current:
            tokens.append(''.join(current))
            current.clear()

    for character in config_text:
        if comment:
            if character == '\n':
                comment = False
            continue
        if escaped:
            current.append(character)
            escaped = False
            continue
        if character == '\\':
            current.append(character)
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            else:
                current.append(character)
            continue
        if character in {'"', "'"}:
            quote = character
            continue
        if character == '#':
            flush()
            comment = True
            continue
        if character.isspace():
            flush()
            continue
        if character == ';':
            flush()
            tokens.append(character)
            continue
        # Block braces normally follow whitespace. Braces attached to a token
        # are kept intact so location regex quantifiers and ${variables} survive.
        if character in {'{', '}'} and not current:
            tokens.append(character)
            continue
        current.append(character)

    flush()
    return tokens


def _parse_config(config_text: str) -> list[dict]:
    # ``nginx -T`` writes successful syntax-check messages together with the
    # dumped configuration when stderr is redirected to stdout.
    config_text = '\n'.join(
        line for line in config_text.splitlines()
        if not line.lstrip().startswith('nginx:')
    )
    root = []
    stack = [root]
    pending = []

    for token in _tokenize_config(config_text):
        if token == ';':
            if pending:
                stack[-1].append({'name': pending[0].lower(), 'args': pending[1:], 'children': None})
                pending = []
        elif token == '{':
            if not pending:
                raise ValueError('NGINX block has no directive name')
            block = {'name': pending[0].lower(), 'args': pending[1:], 'children': []}
            stack[-1].append(block)
            stack.append(block['children'])
            pending = []
        elif token == '}':
            if pending:
                raise ValueError('NGINX directive is missing a semicolon')
            if len(stack) == 1:
                raise ValueError('NGINX configuration has an unmatched closing brace')
            stack.pop()
        else:
            pending.append(token)

    if len(stack) != 1:
        raise ValueError('NGINX configuration has an unclosed block')
    if pending:
        raise ValueError('NGINX directive is missing a semicolon')
    return root


def _directives(items: list[dict], name: str) -> list[dict]:
    return [item for item in items if item['children'] is None and item['name'] == name]


def _target_authority(target: str) -> str:
    value = target.strip()
    if '://' in value:
        value = value.split('://', 1)[1]
    if value.startswith('unix:'):
        return value
    return value.split('/', 1)[0]


def _target_host(authority: str) -> str:
    if authority.startswith('['):
        return authority[1:].split(']', 1)[0]
    if authority.count(':') == 1:
        host, port = authority.rsplit(':', 1)
        if port.isdigit() or '$' in port:
            return host
    return authority


def _is_direct_target(authority: str) -> bool:
    if authority.startswith('unix:') or '$' in authority:
        return True
    host = _target_host(authority)
    if host == 'localhost' or '.' in host or ':' in authority:
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def build_dependency_graph(config_text: str) -> dict:
    """Return a browser-friendly graph from the complete output of ``nginx -T``."""
    syntax = _parse_config(config_text)
    nodes = {}
    edges = []
    upstream_ids = {}
    virtual_server_number = 0
    location_number = 0

    def add_node(node_type: str, node_id: str, name: str, *, defined: bool = True, **data) -> str:
        node = nodes.setdefault(node_id, {
            'id': node_id,
            'type': node_type,
            'name': name,
            'defined': defined,
            'addresses': [],
        })
        node['defined'] = node.get('defined', False) or defined
        for key, value in data.items():
            if value not in (None, '', []):
                node[key] = value
        return node_id

    def add_edge(source: str, target: str, edge_type: str, label: str = '', **data) -> None:
        edge = {
            'id': f'edge:{len(edges) + 1}',
            'source': source,
            'target': target,
            'type': edge_type,
            'label': label,
        }
        edge.update({key: value for key, value in data.items() if value not in (None, '')})
        edges.append(edge)

    def visit_upstreams(items: list[dict], scope: str = 'main') -> None:
        for item in items:
            child_scope = item['name'] if item['name'] in _SCOPES else scope
            if item['children'] is None:
                continue
            if item['name'] == 'upstream' and item['args']:
                upstream_name = item['args'][0]
                upstream_id = f'upstream:{scope}:{upstream_name}'
                upstream_ids[(scope, upstream_name)] = add_node(
                    'upstream', upstream_id, upstream_name, display_name=upstream_name, protocol=scope
                )
                for index, directive in enumerate(_directives(item['children'], 'server'), start=1):
                    if not directive['args']:
                        continue
                    address = directive['args'][0]
                    server_id = f'server:{upstream_id}:{index}'
                    add_node(
                        'server', server_id, address, display_name=address, address=address,
                        parameters=' '.join(directive['args'][1:]), source='upstream'
                    )
                    add_edge(upstream_id, server_id, 'server', address)
                continue
            visit_upstreams(item['children'], child_scope)

    def add_pass_dependency(source_id: str, scope: str, directive: dict) -> None:
        if not directive['args']:
            return
        raw_target = directive['args'][0]
        authority = _target_authority(raw_target)
        upstream_id = upstream_ids.get((scope, authority))
        if upstream_id:
            target_id = upstream_id
        elif _is_direct_target(authority):
            target_id = f'server:direct:{scope}:{authority}'
            add_node(
                'server', target_id, authority, display_name=authority,
                address=raw_target, source='direct'
            )
        else:
            target_id = f'upstream:{scope}:{authority}'
            add_node(
                'upstream', target_id, authority, defined=False,
                display_name=authority, protocol=scope
            )
        add_edge(
            source_id, target_id, directive['name'], raw_target,
            directive=directive['name'], target_address=raw_target
        )

    def visit_dependencies(items: list[dict], source_id: str, scope: str) -> None:
        nonlocal location_number
        for item in items:
            if item['children'] is not None and item['name'] == 'location':
                location_number += 1
                expression = ' '.join(item['args']) or '/'
                location_id = f'location:{source_id}:{location_number}'
                add_node(
                    'location', location_id, expression, display_name=expression,
                    expression=expression, protocol=scope
                )
                add_edge(source_id, location_id, 'location', expression)
                visit_dependencies(item['children'], location_id, scope)
            elif item['children'] is not None:
                visit_dependencies(item['children'], source_id, scope)
            elif item['name'] in _PASS_DIRECTIVES:
                add_pass_dependency(source_id, scope, item)

    def visit_virtual_servers(items: list[dict], scope: str = 'main') -> None:
        nonlocal virtual_server_number
        for item in items:
            child_scope = item['name'] if item['name'] in _SCOPES else scope
            if item['children'] is None:
                continue
            if item['name'] == 'upstream':
                continue
            if item['name'] == 'server' and scope in _SCOPES:
                virtual_server_number += 1
                server_names = [
                    name
                    for directive in _directives(item['children'], 'server_name')
                    for name in directive['args']
                ]
                listen_directives = _directives(item['children'], 'listen')
                addresses = [directive['args'][0] for directive in listen_directives if directive['args']]
                display_name = ', '.join(server_names) if server_names else (
                    f'listen {", ".join(addresses)}' if addresses else f'{scope} server {virtual_server_number}'
                )
                virtual_id = f'virtual_server:{scope}:{virtual_server_number}'
                add_node(
                    'virtual_server', virtual_id, display_name, display_name=display_name,
                    addresses=addresses, server_names=server_names, protocol=scope
                )
                visit_dependencies(item['children'], virtual_id, scope)
                continue
            visit_virtual_servers(item['children'], child_scope)

    visit_upstreams(syntax)
    visit_virtual_servers(syntax)

    type_order = {'virtual_server': 0, 'location': 1, 'upstream': 2, 'server': 3}
    graph_nodes = sorted(
        nodes.values(),
        key=lambda node: (type_order.get(node['type'], 99), node.get('display_name', node['name']).lower()),
    )
    counts = {
        node_type: sum(1 for node in graph_nodes if node['type'] == node_type)
        for node_type in type_order
    }
    return {'nodes': graph_nodes, 'edges': edges, 'counts': counts}


def show_map(serv: str, group_id: int) -> dict:
    """Read the complete active NGINX configuration and build its dependency graph."""
    server = server_sql.get_server_by_ip(serv)
    is_dockerized = service_sql.select_service_setting(server.server_id, 'nginx', 'dockerized') == '1'
    if is_dockerized:
        container_name = sql.get_setting('nginx_container_name', group_id=group_id)
        if not container_name:
            raise RuntimeError('NGINX container name is not configured')
        command = f'sudo docker exec {shlex.quote(str(container_name))} nginx -T 2>&1'
    else:
        command = 'sudo nginx -T 2>&1'

    config_text = server_mod.ssh_command(serv, command, timeout=20, rc=True)
    if not config_text or not config_text.strip():
        raise RuntimeError('NGINX returned an empty configuration')

    graph = build_dependency_graph(config_text)
    graph['server'] = serv
    graph['service'] = 'nginx'
    return graph
