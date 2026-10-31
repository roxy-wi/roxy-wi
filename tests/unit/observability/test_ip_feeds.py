import ipaddress
import socket
import pytest
from app.modules.connectors import ip_feeds
from tests.unit.observability.test_network_probe import endpoint


def settings(**values):
    return ip_feeds.HttpsSettings(url='https://example.test/ips.txt',**values).model_dump()


def test_strict_feed_normalization_handles_ipv4_ipv6_comments_duplicates_and_host_bits():
    assert ip_feeds.normalize('# approved\n192.0.2.9/24 # network\n192.0.2.0/24\n2001:db8::1\n',settings())=='192.0.2.0/24\n2001:db8::1/128\n'


@pytest.mark.parametrize('text',['',' # empty\n','0.0.0.0/0','::/0','192.0.2.1,192.0.2.2','example.com','192.0.2.1;shutdown sessions server','192.0.2.1 192.0.2.2','127.0.0.1','fe80::/64'])
def test_invalid_empty_broad_or_special_lists_never_become_candidates(text):
    with pytest.raises(ValueError):ip_feeds.normalize(text,settings())


def test_entry_limit_and_unknown_connector_are_enforced():
    with pytest.raises(ValueError):ip_feeds.normalize('192.0.2.1\n192.0.2.2\n',settings(max_entries=1))
    with pytest.raises(ValueError):ip_feeds.provider('shell')


@pytest.mark.parametrize('url',['http://example.test/feed','https://user:secret@example.test/feed','https://example.test/#fragment','https://example.test/\r\nInjected:yes','file:///etc/shadow'])
def test_unsafe_source_url_is_rejected(url):
    with pytest.raises(ValueError):ip_feeds.HttpsSettings(url=url)


@pytest.mark.parametrize('address',['127.0.0.1','169.254.169.254','100.100.100.200','10.0.0.1'])
def test_nonpublic_dns_never_opens_an_unapproved_source_connection(monkeypatch,address):
    monkeypatch.setattr(ip_feeds.network_probe,'resolve',lambda _:[address])
    monkeypatch.setattr(ip_feeds.network_probe,'connect',lambda *_:pytest.fail('Unapproved source opened a socket'))
    with pytest.raises(ValueError):ip_feeds.HttpsIpFeed.fetch(settings())


def test_real_private_https_source_is_pinned_and_validates_original_domain_ca_without_credentials(tmp_path,monkeypatch):
    try:address=socket.gethostbyname(socket.gethostname())
    except OSError:pytest.skip('No isolated host interface')
    if ipaddress.ip_address(address).is_loopback or not ipaddress.ip_address(address).is_private:pytest.skip('Requires an isolated private host interface')
    with endpoint(tmp_path,tls=True,bind=address,feed=b'# approved\n192.0.2.1\n192.0.2.0/24\n') as (port,requests,ca):
        answers=[]
        monkeypatch.setattr(ip_feeds.network_probe,'resolve',lambda host:answers.append(host) or [address])
        data=ip_feeds.HttpsSettings(url='https://example.test:'+str(port)+'/feed',allow_private=True,ca_pem=ca).model_dump()
        assert ip_feeds.HttpsIpFeed.fetch(data)=='192.0.2.0/24\n192.0.2.1/32\n'
        assert answers==['example.test'] and len(requests)==1
        assert requests[0]['headers']['Host']=='example.test:'+str(port)
        assert 'Authorization' not in requests[0]['headers'] and 'Cookie' not in requests[0]['headers']
        data['ca_pem']=''
        with pytest.raises(Exception):ip_feeds.HttpsIpFeed.fetch(data)
        assert len(requests)==1 # invalid trust never sends an HTTP GET


def test_https_feed_redirect_is_never_followed(tmp_path,monkeypatch):
    try:address=socket.gethostbyname(socket.gethostname())
    except OSError:pytest.skip('No isolated host interface')
    if ipaddress.ip_address(address).is_loopback or not ipaddress.ip_address(address).is_private:pytest.skip('Requires an isolated private host interface')
    with endpoint(tmp_path,tls=True,bind=address,feed_status=302) as (port,requests,ca):
        monkeypatch.setattr(ip_feeds.network_probe,'resolve',lambda _:[address])
        data=ip_feeds.HttpsSettings(url='https://example.test:'+str(port)+'/redirect',allow_private=True,ca_pem=ca).model_dump()
        with pytest.raises(ValueError,match='without redirects'):ip_feeds.HttpsIpFeed.fetch(data)
        assert len(requests)==1
