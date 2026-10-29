"""Numeric installation targets must reach ID lookup, preserving IP routes."""
import pytest


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache', 'keepalived'])
@pytest.mark.parametrize('target,expected', [('42', 42), ('192.0.2.42', '192.0.2.42'), ('2001:db8::42', '2001:db8::42')])
def test_installation_target_reaches_the_correct_lookup_type(app, service, target, expected):
    adapter = app.url_map.bind('localhost')
    endpoint, values = adapter.match(f'/install/{service}/{target}', method='POST')
    assert endpoint in ('install.install_id', 'install.install_ip')
    assert values == {'service': service, 'server_id': expected}
    assert type(values['server_id']) is type(expected)
