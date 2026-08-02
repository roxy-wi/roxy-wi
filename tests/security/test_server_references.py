from types import SimpleNamespace

import pytest
from flask import g

from app.modules.common.common_classes import SupportClass


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
