from pathlib import Path

from app.modules.service import haproxy


HAPROXY_CONFIG = """
global
    daemon

defaults
    mode http

frontend public_https
    bind *:443 ssl crt /etc/haproxy/certs/site.pem
    bind 127.0.0.1:8443
    use_backend api_pool if { path_beg /api }
    use_backend missing_pool if { path_beg /missing }
    default_backend web_pool

backend api_pool
    server api-1 10.0.0.11:8080 check
    server-template api 1-2 _api._tcp.example.test check

backend web_pool
    server web-1 [2001:db8::10]:80 check

backend orphan_pool
    server orphan-1 10.0.0.50:9000 check

listen prometheus
    bind 127.0.0.1:8404
    server exporter 127.0.0.1:9100
"""


def _node(graph, node_id):
    return next(node for node in graph['nodes'] if node['id'] == node_id)


def test_dependency_graph_preserves_frontend_backend_server_hierarchy():
    graph = haproxy.build_dependency_graph(HAPROXY_CONFIG)

    assert graph['counts'] == {
        'frontend': 1,
        'listen': 1,
        'backend': 4,
        'server': 5,
    }
    assert _node(graph, 'frontend:public_https')['addresses'] == ['*:443', '127.0.0.1:8443']
    assert _node(graph, 'backend:api_pool')['defined'] is True
    assert _node(graph, 'backend:missing_pool')['defined'] is False
    assert _node(graph, 'server:backend:web_pool:web-1')['address'] == '[2001:db8::10]:80'
    assert _node(graph, 'server:backend:api_pool:api [1-2]')['template'] is True

    edge_pairs = {(edge['source'], edge['target']) for edge in graph['edges']}
    assert ('frontend:public_https', 'backend:api_pool') in edge_pairs
    assert ('frontend:public_https', 'backend:web_pool') in edge_pairs
    assert ('backend:api_pool', 'server:backend:api_pool:api-1') in edge_pairs
    assert ('listen:prometheus', 'server:listen:prometheus:exporter') in edge_pairs


def test_dependency_graph_keeps_routing_conditions_and_ignores_comments():
    graph = haproxy.build_dependency_graph("""
frontend ingress
    bind :80 # public address
    use_backend blue if host_blue # route comment

backend blue
    server blue-1 192.0.2.10:8080 check # server comment
""")

    route = next(edge for edge in graph['edges'] if edge['type'] == 'use_backend')
    assert route['condition'] == 'if host_blue'
    assert route['label'] == 'if host_blue'
    assert _node(graph, 'server:backend:blue:blue-1')['address'] == '192.0.2.10:8080'


def test_show_map_removes_the_downloaded_temporary_config(monkeypatch):
    downloaded_paths = []

    def write_config(_server, config_path, service):
        assert service == 'haproxy'
        downloaded_paths.append(Path(config_path))
        Path(config_path).write_text(HAPROXY_CONFIG, encoding='utf-8')

    monkeypatch.setattr(haproxy.config_mod, 'get_config', write_config)

    graph = haproxy.show_map('192.0.2.20', 1)

    assert graph['server'] == '192.0.2.20'
    assert graph['counts']['frontend'] == 1
    assert downloaded_paths and not downloaded_paths[0].exists()


def test_dependency_graph_handles_an_empty_configuration():
    graph = haproxy.build_dependency_graph('global\n    daemon\n# no proxies yet\n')

    assert graph == {
        'nodes': [],
        'edges': [],
        'counts': {'frontend': 0, 'listen': 0, 'backend': 0, 'server': 0},
    }


def test_show_map_removes_temporary_config_when_download_fails(monkeypatch):
    downloaded_paths = []

    def fail_download(_server, config_path, service):
        assert service == 'haproxy'
        downloaded_paths.append(Path(config_path))
        raise RuntimeError('SSH failed')

    monkeypatch.setattr(haproxy.config_mod, 'get_config', fail_download)

    try:
        haproxy.show_map('192.0.2.20', 1)
    except RuntimeError as error:
        assert str(error) == 'SSH failed'
    else:
        raise AssertionError('show_map must propagate download errors')

    assert downloaded_paths and not downloaded_paths[0].exists()
