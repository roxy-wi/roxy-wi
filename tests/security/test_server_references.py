from types import SimpleNamespace

import pytest
from flask import g
from flask import request

from app.modules.common.common_classes import SupportClass
from app.modules.roxywi import common as roxywi_common


@pytest.mark.security
def test_server_reference_uses_ip_lookup_for_strings_and_id_lookup_for_integers(app, monkeypatch):
    calls = []

    def by_ip(value):
        calls.append(('ip', value))
        return SimpleNamespace(server_id=11, ip=value, group_id=1)

    def by_id(value):
        calls.append(('id', value))
        return SimpleNamespace(server_id=value, ip='192.0.2.11', group_id=1)

    monkeypatch.setattr('app.modules.common.common_classes.server_sql.get_server_by_ip', by_ip)
    monkeypatch.setattr('app.modules.common.common_classes.server_sql.get_server', by_id)

    with app.test_request_context('/'):
        g.user_params = {'group_id': 1, 'role': 2, 'user_id': 1}
        undecorated = SupportClass.return_server_ip_or_id.__wrapped__
        assert undecorated(SupportClass(), '192.0.2.10') == 11
        assert undecorated(SupportClass(), 12) == 12

    assert calls == [('ip', '192.0.2.10'), ('id', 12)]


@pytest.mark.security
def test_runtime_server_ip_argument_uses_id_lookup_when_route_converter_returns_int(app, monkeypatch):
    calls = []

    def by_id(value):
        calls.append(('id', value))
        return SimpleNamespace(server_id=value, ip='192.0.2.11', group_id=7)

    def by_ip(value):
        calls.append(('ip', value))
        raise AssertionError('An integer route value must not be treated as an IP address')

    monkeypatch.setattr(roxywi_common.server_sql, 'get_server', by_id)
    monkeypatch.setattr(roxywi_common.server_sql, 'get_server_by_ip', by_ip)

    with app.test_request_context('/runtimeapi/backends/1'):
        g.user_params = {'group_id': 7}
        request.view_args = {'server_ip': 1}
        roxywi_common.require_request_server_access()

    assert calls == [('id', 1)]


@pytest.mark.security
def test_runtime_ip_argument_still_uses_ip_lookup(app, monkeypatch):
    calls = []

    def by_ip(value):
        calls.append(('ip', value))
        return SimpleNamespace(server_id=1, ip=value, group_id=7)

    monkeypatch.setattr(roxywi_common.server_sql, 'get_server_by_ip', by_ip)

    with app.test_request_context('/runtimeapi/backends/192.0.2.11'):
        g.user_params = {'group_id': 7}
        request.view_args = {'server_ip': '192.0.2.11'}
        roxywi_common.require_request_server_access()

    assert calls == [('ip', '192.0.2.11')]
