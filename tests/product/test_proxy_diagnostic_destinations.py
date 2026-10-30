"""A selected frontend must never borrow another listener's HTTP response."""
import copy

import pytest

from app.modules.service import proxy_assessments as diagnostic, published_endpoints as inventory
from tests.product.test_proxy_diagnostics import diagnostic_host, queue, finish


def test_other_listener_dns_response_does_not_establish_selected_frontend_health(
        product_client, diagnostic_host, monkeypatch):
    parsed = inventory.parse('haproxy', '''defaults
 mode http
frontend first
 bind 192.0.2.11:443
 default_backend pool
frontend second
 bind 192.0.2.12:443
 default_backend pool
backend pool
 server app 192.0.2.88:8080
''')
    def discover(server, service):
        return dict(copy.deepcopy(parsed), binding=None, running_sources_verified=True)
    def rpc(server, operation, data, binding=None):
        diagnostic_host.calls.append((operation, dict(data)))
        if operation == 'resolve':
            return [data['host']] if data['host'] == '192.0.2.88' else ['192.0.2.11']
        return dict(ip=data['ip'], port=data['port'], tcp='refused',
                    tls='not-requested', http='not-requested')
    monkeypatch.setattr(inventory, 'discover', discover)
    monkeypatch.setattr(diagnostic, 'interfaces', lambda _: ['192.0.2.11', '192.0.2.12'])
    monkeypatch.setattr(diagnostic, 'rpc', rpc)
    report = finish(queue(product_client, frontend_id='frontend:second'))
    assert report['selected_frontend'] == 'frontend:second'
    assert not any(kind == 'controller-probe' for kind, _ in diagnostic_host.calls)
    vip = next(stage for stage in report['stages'] if stage['key'] == 'vip')
    assert vip['details']['probes'] == []
    assert vip['details']['unmatched'] == ['192.0.2.11']
    assert next(stage for stage in report['stages'] if stage['key'] == 'http')['state'] != 'observed'
    assert 'selected proxy listener responds' not in report['summary']


@pytest.mark.parametrize('binding,expected', [
    ({'host': '192.0.2.12', 'port': 443}, {'192.0.2.12'}),
    ({'host': '*', 'port': 443}, {'192.0.2.11', '192.0.2.12', '2001:db8::11'}),
    ({'host': '0.0.0.0', 'port': 443}, {'192.0.2.11', '192.0.2.12'}),
    ({'host': '::', 'port': 443}, {'2001:db8::11'}),
    ({'host': '::', 'port': 443, 'address_family': 'v6only'}, {'2001:db8::11'}),
    ({'host': '::', 'port': 443, 'address_family': 'v4v6'}, {'192.0.2.11', '192.0.2.12', '2001:db8::11'}),
    ({'host': '::ffff:192.0.2.12', 'port': 443}, {'192.0.2.12'}),
    ({'host': 'listener.example.test', 'port': 443}, set()),
])
def test_selected_bind_controls_family_and_address_scope(binding, expected):
    front = {'listeners': [binding, {'host': '*', 'port': 8443}]}
    host_addresses = ['192.0.2.11', '192.0.2.12', '2001:db8::11', '127.0.0.1', '169.254.169.254']
    assert diagnostic.listener_destinations(front, 443, host_addresses) == expected


def test_literal_nonlocal_vip_remains_a_configured_destination():
    front = {'listeners': [{'host': '192.0.2.100', 'port': 443}]}
    assert diagnostic.listener_destinations(front, 443, ['192.0.2.11']) == {'192.0.2.100'}


@pytest.mark.parametrize('route,unresolved', [
    ('use_backend pool', 0),
    ('default_backend pool\n use_backend %[req.hdr(SecretRouteToken)]', 1),
    ('default_backend pool\n use_backend missing if unknown_acl', 1),
])
def test_listen_dependency_and_routing_uncertainty_reach_the_report(
        product_client, diagnostic_host, monkeypatch, route, unresolved):
    parsed = inventory.parse('haproxy', f'''defaults
 mode http
listen public
 bind *:443
 {route}
backend pool
 server app 192.0.2.88:8080
''')
    monkeypatch.setattr(inventory, 'discover', lambda *_: dict(
        copy.deepcopy(parsed), binding=None, running_sources_verified=True))
    original = diagnostic.rpc
    def rpc(server, operation, data, binding=None):
        result = original(server, operation, data, binding)
        if operation == 'probe':result['tcp'] = 'connected'
        return result
    monkeypatch.setattr(diagnostic, 'rpc', rpc)
    report = finish(queue(product_client, frontend_id='listen:public'))
    backend = next(stage for stage in report['stages'] if stage['key'] == 'backends')
    assert [target['host'] for target in backend['details']['targets']] == ['192.0.2.88']
    assert backend['details']['not_probed'] == unresolved
    assert backend['details']['unresolved_routes'] == unresolved
    assert backend['state'] == ('warning' if unresolved else 'observed')
    configuration = next(stage for stage in report['stages'] if stage['key'] == 'configuration')
    assert configuration['details']['partial'] is bool(unresolved)
    if unresolved:
        assert backend['details']['unresolved_route_evidence']
        assert 'SecretRouteToken' not in str(report)
