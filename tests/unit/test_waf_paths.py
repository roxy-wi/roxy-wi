import pytest

from app.modules.common import common
from app.modules.roxywi.exception import RoxywiValidationError


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('directory', ['/etc/proxy', '/srv/custom proxy/', '/srv/custom/../proxy//'])
def test_waf_rule_paths_use_remote_posix_directories(monkeypatch, service, directory):
    settings = {'haproxy_dir': '/unexpected/haproxy', 'nginx_dir': '/unexpected/nginx',
                f'{service}_dir': directory}
    monkeypatch.setattr(common.sql, 'get_setting', settings.__getitem__)
    expected = {'/etc/proxy': '/etc/proxy', '/srv/custom proxy/': '/srv/custom proxy',
                '/srv/custom/../proxy//': '/srv/proxy'}[directory]
    assert common.resolve_waf_config_path(service, 'REQUEST-920-test.conf') == f'{expected}/waf/rules/REQUEST-920-test.conf'


@pytest.mark.parametrize('filename', [None, 1, '', '../other.conf', '/etc/other.conf', r'..\other.conf',
                                    'nested/rule.conf', 'rule.conf\n', 'rule.conf\x00', 'rule.cfg'])
def test_invalid_waf_filenames_are_rejected_before_settings(monkeypatch, filename):
    monkeypatch.setattr(common.sql, 'get_setting', lambda *a: pytest.fail('Invalid filename reached settings'))
    with pytest.raises(RoxywiValidationError):
        common.resolve_waf_config_path('haproxy', filename)


@pytest.mark.parametrize('directory', [None, '', 'etc/haproxy', r'C:\haproxy', '/etc/proxy\n', '/etc/proxy\x00'])
def test_invalid_waf_directories_are_rejected(monkeypatch, directory):
    monkeypatch.setattr(common.sql, 'get_setting', lambda *a: directory)
    with pytest.raises(RoxywiValidationError):
        common.resolve_waf_config_path('haproxy', 'test.conf')


def test_unsupported_waf_service_is_rejected_before_settings(monkeypatch):
    monkeypatch.setattr(common.sql, 'get_setting', lambda *a: pytest.fail('Unsupported service reached settings'))
    with pytest.raises(RoxywiValidationError):
        common.resolve_waf_config_path('apache', 'test.conf')
