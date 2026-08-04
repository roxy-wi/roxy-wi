from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.service import nginx


NGINX_CONFIG = r"""
# configuration file /etc/nginx/nginx.conf:
events {}

http {
    upstream api_pool {
        server 10.0.0.11:8080 max_fails=3;
        server unix:/run/api.sock backup;
    }

    upstream orphan_pool {
        server 10.0.0.50:9000;
    }

    server {
        listen 443 ssl;
        listen [::]:443 ssl;
        server_name example.test www.example.test;

        location /api/ {
            proxy_pass http://api_pool/v1/;
        }

        location ~ ^/image/[0-9]{1,3}$ {
            proxy_pass http://missing_pool;
        }

        location /external/ {
            proxy_pass https://service.example.net:8443/root/;
        }

        location /php/ {
            fastcgi_pass unix:/run/php/php-fpm.sock;
        }
    }
}

stream {
    upstream tcp_pool {
        server 10.0.0.70:5432;
    }

    server {
        listen 9000;
        proxy_pass tcp_pool;
    }
}
"""


def _node(graph, node_id):
    return next(node for node in graph['nodes'] if node['id'] == node_id)


def _nodes_of_type(graph, node_type):
    return [node for node in graph['nodes'] if node['type'] == node_type]


def test_dependency_graph_preserves_nginx_routing_hierarchy():
    graph = nginx.build_dependency_graph(NGINX_CONFIG)

    assert graph['counts'] == {
        'virtual_server': 2,
        'location': 4,
        'upstream': 4,
        'server': 6,
    }
    virtual_servers = _nodes_of_type(graph, 'virtual_server')
    http_server = next(node for node in virtual_servers if node['protocol'] == 'http')
    stream_server = next(node for node in virtual_servers if node['protocol'] == 'stream')
    assert http_server['server_names'] == ['example.test', 'www.example.test']
    assert http_server['addresses'] == ['443', '[::]:443']
    assert stream_server['addresses'] == ['9000']

    assert _node(graph, 'upstream:http:api_pool')['defined'] is True
    assert _node(graph, 'upstream:http:missing_pool')['defined'] is False
    assert _node(graph, 'server:upstream:http:api_pool:2')['address'] == 'unix:/run/api.sock'

    edge_pairs = {(edge['source'], edge['target']) for edge in graph['edges']}
    assert ('upstream:http:api_pool', 'server:upstream:http:api_pool:1') in edge_pairs
    assert (stream_server['id'], 'upstream:stream:tcp_pool') in edge_pairs
    api_location = next(node for node in _nodes_of_type(graph, 'location') if node['expression'] == '/api/')
    assert (http_server['id'], api_location['id']) in edge_pairs
    assert (api_location['id'], 'upstream:http:api_pool') in edge_pairs


def test_dependency_graph_handles_regex_locations_and_direct_targets():
    graph = nginx.build_dependency_graph(NGINX_CONFIG)

    expressions = {node['expression'] for node in _nodes_of_type(graph, 'location')}
    assert '~ ^/image/[0-9]{1,3}$' in expressions

    direct_targets = {
        node['address']
        for node in _nodes_of_type(graph, 'server')
        if node.get('source') == 'direct'
    }
    assert direct_targets == {
        'https://service.example.net:8443/root/',
        'unix:/run/php/php-fpm.sock',
    }
    proxy_edge = next(edge for edge in graph['edges'] if edge.get('target_address') == 'http://api_pool/v1/')
    assert proxy_edge['type'] == 'proxy_pass'
    assert proxy_edge['target'] == 'upstream:http:api_pool'


def test_dependency_graph_handles_an_empty_configuration():
    graph = nginx.build_dependency_graph('events {}\nhttp {}\n')

    assert graph == {
        'nodes': [],
        'edges': [],
        'counts': {'virtual_server': 0, 'location': 0, 'upstream': 0, 'server': 0},
    }


def test_dependency_graph_ignores_nginx_t_diagnostics():
    graph = nginx.build_dependency_graph(
        'nginx: the configuration file /etc/nginx/nginx.conf syntax is ok\n'
        'nginx: configuration file /etc/nginx/nginx.conf test is successful\n'
        'events {}\nhttp { server { listen 80; } }\n'
    )

    assert graph['counts']['virtual_server'] == 1
    assert _nodes_of_type(graph, 'virtual_server')[0]['addresses'] == ['80']


def test_show_map_reads_complete_native_nginx_configuration(monkeypatch):
    commands = []
    monkeypatch.setattr(nginx.server_sql, 'get_server_by_ip', lambda server_ip: SimpleNamespace(server_id=7))
    monkeypatch.setattr(nginx.service_sql, 'select_service_setting', lambda *args: '0')
    monkeypatch.setattr(
        nginx.server_mod,
        'ssh_command',
        lambda server_ip, command, **kwargs: commands.append((server_ip, command, kwargs)) or NGINX_CONFIG,
    )

    graph = nginx.show_map('192.0.2.20', 3)

    assert graph['service'] == 'nginx'
    assert graph['server'] == '192.0.2.20'
    assert commands == [('192.0.2.20', 'sudo nginx -T 2>&1', {'timeout': 20, 'rc': True})]


def test_show_map_reads_nginx_configuration_from_configured_container(monkeypatch):
    commands = []
    monkeypatch.setattr(nginx.server_sql, 'get_server_by_ip', lambda server_ip: SimpleNamespace(server_id=8))
    monkeypatch.setattr(nginx.service_sql, 'select_service_setting', lambda *args: '1')
    monkeypatch.setattr(nginx.sql, 'get_setting', lambda setting, **kwargs: 'nginx-prod; touch /tmp/pwned')
    monkeypatch.setattr(
        nginx.server_mod,
        'ssh_command',
        lambda server_ip, command, **kwargs: commands.append((server_ip, command, kwargs)) or NGINX_CONFIG,
    )

    nginx.show_map('192.0.2.21', 4)

    assert commands == [(
        '192.0.2.21',
        "sudo docker exec 'nginx-prod; touch /tmp/pwned' nginx -T 2>&1",
        {'timeout': 20, 'rc': True},
    )]


def test_show_map_rejects_empty_nginx_output(monkeypatch):
    monkeypatch.setattr(nginx.server_sql, 'get_server_by_ip', lambda server_ip: SimpleNamespace(server_id=9))
    monkeypatch.setattr(nginx.service_sql, 'select_service_setting', lambda *args: '0')
    monkeypatch.setattr(nginx.server_mod, 'ssh_command', lambda *args, **kwargs: '')

    with pytest.raises(RuntimeError, match='empty configuration'):
        nginx.show_map('192.0.2.22', 5)


def test_nginx_map_is_exposed_by_the_shared_config_interface():
    project_root = Path(__file__).resolve().parents[2]
    template = (project_root / 'app' / 'templates' / 'config.html').read_text(encoding='utf-8')
    script = (project_root / 'app' / 'static' / 'js' / 'haproxy-map.js').read_text(encoding='utf-8')

    assert "service == 'haproxy' or service == 'nginx'" in template
    assert "url: '/config/map/' + encodeURIComponent(dependencyMapService)" in script
    assert "label: 'NGINX'" in script
    assert "{type: 'upstream', label: 'Upstream'}" in script
