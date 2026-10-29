from types import SimpleNamespace
import pytest
from app.modules.service import served_tls, proxy_assessments, network_probe, published_endpoints
from tests.unit.observability.test_network_probe import endpoint


def test_comparison_detects_two_real_tls_certificates_without_sending_http(tmp_path,monkeypatch):
    left=tmp_path/'left';right=tmp_path/'right';left.mkdir();right.mkdir()
    with endpoint(left,tls=True) as (left_port,left_http,left_ca), endpoint(right,tls=True) as (right_port,right_http,right_ca):
        found=published_endpoints.parse('haproxy','frontend tls\n bind *:443 ssl crt /cert.pem\n acl site hdr(host) -i example.test\n')
        found['binding']=None
        targets=[(SimpleNamespace(server_id=ident,hostname='node'+str(ident),group_id=1),'haproxy',found['frontends'][0],found) for ident in (1,2)]
        monkeypatch.setattr(served_tls.inventory,'discover',lambda *_:found)
        monkeypatch.setattr(proxy_assessments,'interfaces',lambda _:[])
        monkeypatch.setattr(network_probe,'resolve',lambda _:(_ for _ in ()).throw(ValueError('No public DNS in isolated test')))
        def rpc(server,operation,data,**kwargs):
            assert operation=='probe' and not data['http']
            request=dict(data,port=left_port if server.server_id==1 else right_port)
            return proxy_assessments.certificate_result(network_probe.probe(request))
        monkeypatch.setattr(proxy_assessments,'rpc',rpc)
        report=served_tls.inspect(dict(domain='example.test',port=443,ca_pem=left_ca+right_ca,warning_days=1),targets,None)
        proxy=[item for item in report['endpoints'] if item.get('server_id')]
        assert all(item['tls']=='verified' and item['certificate']['domains']==['example.test'] for item in proxy)
        assert report['state']=='mismatch' and not report['peer_consistent']
        assert left_http==[] and right_http==[]
