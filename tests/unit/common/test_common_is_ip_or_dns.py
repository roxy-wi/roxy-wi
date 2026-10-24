import pytest

from app.modules.common import common


@pytest.mark.parametrize('host', [
    'example.com',
    'my-host.example.org',
    'x.io',
    # top-level domains longer than six letters
    'lb1.corp.internal',
    'app.example.digital',
    'srv.example.network',
    # DNS names are case-insensitive past the first label too
    'web.Example.com',
    'WEB.EXAMPLE.COM',
    # internationalised names in punycode, including the TLD
    'xn--80ak6aa92e.com',
    'a.xn--p1ai',
])
def test_valid_hostnames_are_accepted(host):
    assert common.is_ip_or_dns(host) == host


@pytest.mark.parametrize('host', [
    '-web.example.com',
    'web-.example.com',
    'example',
    'example.c',
    'a..b.com',
    'exa mple.com',
    'web.example.123',
    'x;rm.example.com',
])
def test_invalid_hostnames_are_rejected(host):
    assert common.is_ip_or_dns(host) == ''


def test_ips_and_service_names_still_pass():
    assert common.is_ip_or_dns('192.168.0.10') == '192.168.0.10'
    assert common.is_ip_or_dns(' 10.0.0.1 ') == '10.0.0.1'
    assert common.is_ip_or_dns('roxy-wi-checker') == 'roxy-wi-checker'
    assert common.is_ip_or_dns('256.1.1.1') == ''
