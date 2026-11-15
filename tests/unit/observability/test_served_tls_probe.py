from types import SimpleNamespace

from app.modules.service import served_tls, proxy_assessments, network_probe, published_endpoints
from tests.unit.observability.test_network_probe import endpoint


def test_post_deployment_comparison_uses_real_tls_without_http(tmp_path, monkeypatch):
    left = tmp_path / 'left'; right = tmp_path / 'right'; left.mkdir(); right.mkdir()
    with endpoint(left, tls=True) as (left_port, left_http, left_ca), \
            endpoint(right, tls=True) as (right_port, right_http, right_ca):
        found = published_endpoints.parse('haproxy', 'frontend tls\n bind *:443 ssl crt /cert.pem\n')
        found.update(binding=None, running_sources_verified=True)
        targets = {str(ident):dict(address='192.0.2.'+str(ident), settings={}) for ident in (1, 2)}
        monkeypatch.setattr(served_tls.inventory, 'discover', lambda *_: found)
        monkeypatch.setattr(proxy_assessments, 'authorize', lambda ident, *_args, **_kw: SimpleNamespace(
            server_id=ident, ip='192.0.2.'+str(ident), group_id=1))
        monkeypatch.setattr(proxy_assessments, 'identity', lambda server, _: {'ip':server.ip})
        def rpc(server, operation, data, **kwargs):
            assert operation == 'probe' and not data['http']
            return proxy_assessments.certificate_result(network_probe.probe(dict(data,
                port=left_port if server.server_id == 1 else right_port, ca_pem=left_ca+right_ca)))
        monkeypatch.setattr(proxy_assessments, 'rpc', rpc)
        expected = network_probe.probe(dict(ip='127.0.0.1', port=left_port, domain='example.test',
                                          tls=True, http=False, ca_pem=left_ca))['fingerprint']
        report = served_tls.verify(targets, dict(domains=['example.test'], fingerprint=expected), 1, 1)
        assert all(item['tls'] == 'verified' for item in report['endpoints'])
        assert report['state'] == 'mismatch' and not report['peer_consistent']
        assert left_http == [] and right_http == []
