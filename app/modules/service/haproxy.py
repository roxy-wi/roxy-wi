import os
import shlex
import tempfile
import requests

from flask import request, g
from requests.exceptions import ConnectionError, Timeout

import app.modules.db.sql as sql
import app.modules.server.server as server_mod
import app.modules.config.config as config_mod
import app.modules.roxywi.common as roxywi_common


def stat_page_action(server_ip: str, group_id: int) -> bytes:
    haproxy_user = sql.get_setting('haproxy_stats_user', group_id=group_id)
    haproxy_pass = sql.get_setting('haproxy_stats_password', group_id=group_id)
    haproxy_pass = haproxy_pass.replace("'", "")
    stats_port = sql.get_setting('haproxy_stats_port', group_id=group_id)
    stats_page = sql.get_setting('haproxy_stats_page', group_id=group_id)
    url = f'http://{server_ip}:{stats_port}/{stats_page}'

    postdata = {
        'action': request.form.get('action'),
        's': request.form.get('s'),
        'b': request.form.get('b')
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 5.1; rv:20.0) Gecko/20100101 Firefox/20.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate'
    }

    try:
        data = requests.post(url, headers=headers, data=postdata, auth=(haproxy_user, haproxy_pass), timeout=5)
    except ConnectionError as e:
        if "Max retries exceeded" in str(e):
            raise Exception(f"error: Max retries exceeded with url: {url}")
        raise Exception(f"error: Cannot connect to {url} {e}")
    except Timeout as e:
        raise Exception(f"error: Timeout for {url}: {e}")
    except Exception as e:
        raise Exception(f"error: Cannot connect to {url}: {e}")
    return data.content


def _haproxy_line_tokens(line: str) -> list[str]:
    """Split one HAProxy directive while respecting quotes and comments."""
    try:
        return shlex.split(line, comments=True, posix=True)
    except ValueError:
        return line.split('#', 1)[0].split()


def build_dependency_graph(config_text: str) -> dict:
    """Build a browser-friendly frontend -> backend -> server graph."""
    nodes = {}
    edges = []
    current_type = ''
    current_name = ''
    current_id = ''

    def add_node(node_type: str, name: str, *, defined: bool = True, **data) -> str:
        node_id = f'{node_type}:{name}'
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

    def add_addresses(node_id: str, values: list[str]) -> None:
        for value in values:
            if value and value not in nodes[node_id]['addresses']:
                nodes[node_id]['addresses'].append(value)

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

    for raw_line in config_text.splitlines():
        tokens = _haproxy_line_tokens(raw_line.strip())
        if not tokens:
            continue

        directive = tokens[0].lower()
        if directive in {'frontend', 'backend', 'listen'} and len(tokens) > 1:
            current_type = directive
            current_name = tokens[1]
            current_id = add_node(current_type, current_name)
            if current_type in {'frontend', 'listen'} and len(tokens) > 2:
                add_addresses(current_id, [tokens[2]])
            continue

        if not current_id:
            continue

        if directive == 'bind' and current_type in {'frontend', 'listen'} and len(tokens) > 1:
            add_addresses(current_id, [address.strip() for address in tokens[1].split(',')])
            continue

        if (
            current_type == 'frontend'
            and directive in {'default_backend', 'use_backend'}
            and len(tokens) > 1
        ):
            backend_name = tokens[1]
            backend_id = add_node('backend', backend_name, defined=False)
            condition = ' '.join(tokens[2:])
            label = 'default' if directive == 'default_backend' else condition or 'rule'
            add_edge(
                current_id,
                backend_id,
                directive,
                label,
                condition=condition,
            )
            continue

        if (
            current_type in {'backend', 'listen'}
            and directive in {'server', 'server-template'}
            and len(tokens) > 2
        ):
            if directive == 'server-template' and len(tokens) > 3:
                server_name = f'{tokens[1]} [{tokens[2]}]'
                address = tokens[3]
            else:
                server_name = tokens[1]
                address = tokens[2]
            server_id = add_node(
                'server',
                f'{current_type}:{current_name}:{server_name}',
                display_name=server_name,
                address=address,
                template=directive == 'server-template',
            )
            add_edge(current_id, server_id, directive, address)

    type_order = {'frontend': 0, 'listen': 1, 'backend': 2, 'server': 3}
    graph_nodes = sorted(
        nodes.values(),
        key=lambda node: (type_order.get(node['type'], 99), node.get('display_name', node['name']).lower()),
    )
    counts = {
        node_type: sum(1 for node in graph_nodes if node['type'] == node_type)
        for node_type in type_order
    }

    return {
        'nodes': graph_nodes,
        'edges': edges,
        'counts': counts,
    }


def show_map(serv: str, group_id: int) -> dict:
    """Download the active HAProxy configuration and return its dependency graph."""
    del group_id  # Access is checked by the route; graph parsing is group-independent.
    descriptor, cfg = tempfile.mkstemp(prefix='roxy-wi-haproxy-map-', suffix='.cfg')
    os.close(descriptor)

    try:
        config_mod.get_config(serv, cfg, service='haproxy')
        with open(cfg, 'r', encoding='utf-8', errors='replace') as config_file:
            graph = build_dependency_graph(config_file.read())
        graph['server'] = serv
        return graph
    finally:
        try:
            os.remove(cfg)
        except FileNotFoundError:
            pass


def runtime_command(serv: str, enable: str, backend: str, save: str) -> str:
    server_state_file = sql.get_setting('server_state_file', group_id=g.user_params['group_id'])
    haproxy_sock = sql.get_setting('haproxy_sock', group_id=g.user_params['group_id'])
    cmd = f"echo {enable} {backend} |sudo socat stdio {haproxy_sock}"

    if save == "on":
        save_command = f'echo "show servers state" | sudo socat {haproxy_sock} stdio > {server_state_file}'
        cmd = cmd + ';' + save_command

    try:
        output = server_mod.ssh_command(serv, cmd, show_log="1")
    except Exception as e:
        return f'{e}'
    else:
        if enable != "show":
            roxywi_common.logging(serv, f'Has been {enable}ed {backend}', keep_history=1, service='haproxy')
            return f'<center><h3>You {enable} {backend} on HAProxy {serv}.</center> {output}'
        else:
            return output
