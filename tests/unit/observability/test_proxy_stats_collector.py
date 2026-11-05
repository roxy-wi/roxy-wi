"""Parser coverage for stock NGINX and Apache status variants and invalid data."""

import pytest

from app.modules.service.stats import proxy_stats as stats
from tests.fixtures.proxy_stats import APACHE, APACHE_BASIC, NGINX


def test_nginx_counters_are_named_and_numeric():
    assert stats.parse_nginx(NGINX.decode()) == {
        'active': 3, 'accepts': 10, 'handled': 9, 'requests': 20,
        'reading': 0, 'writing': 1, 'waiting': 2,
    }


def test_apache_extended_and_basic_fields():
    result = stats.parse_apache(APACHE.decode())
    assert result['version'] == '2.4.62'
    assert result['requests'] == 20
    assert result['total_kbytes'] == 100
    assert result['cpu_load'] == .025
    assert result['scoreboard'] == '_W_K_....'
    assert result['graceful'] is None
    basic = stats.parse_apache(APACHE_BASIC.decode())
    assert basic['version'] is None
    assert basic['busy'] == 1 and basic['idle'] == 2
    assert basic['requests'] is None and basic['average_bps'] is None


def test_apache_version_excludes_platform_and_module_banners():
    body = APACHE.decode().replace('Apache/2.4.62', 'Apache/2.4.62 (Unix) OpenSSL/3.0.7 mod_wsgi/4.9.4')
    assert stats.parse_apache(body)['version'] == '2.4.62'


@pytest.mark.parametrize('body', ['', '<html>Access denied</html>', 'Active connections: 3',
                                  NGINX.decode().replace('10 9 20', '10 9 -20'),
                                  NGINX.decode() + 'garbage'])
def test_nginx_rejects_non_status_response(body):
    with pytest.raises(stats.StatsError, match='invalid_response'):
        stats.parse_nginx(body)


@pytest.mark.parametrize('body', ['', '<html>Server Status</html>',
    APACHE.decode().replace('BusyWorkers: 2', 'BusyWorkers: -2'),
    APACHE.decode().replace('CPULoad: .025', 'CPULoad: nan'),
    APACHE.decode().replace('CPULoad: .025', 'CPULoad: inf'),
    APACHE.decode().replace('Scoreboard: _W_K_....', 'Scoreboard: <script>'),
    APACHE.decode() + 'BusyWorkers: 3\n',
    APACHE.decode().replace('Apache/2.4.62', ''),
    APACHE.decode().replace('Apache/2.4.62', 'a' * 513),
])
def test_apache_rejects_missing_invalid_or_duplicate_fields(body):
    with pytest.raises(stats.StatsError, match='invalid_response'):
        stats.parse_apache(body)


def test_apache_accepts_new_fields_without_exposing_them():
    result = stats.parse_apache(APACHE.decode() + 'FutureField: arbitrary <html>\n')
    assert 'FutureField' not in result
