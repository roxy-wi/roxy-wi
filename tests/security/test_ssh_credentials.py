from types import SimpleNamespace

import pytest

from app.modules.roxywi.exception import RoxywiResourceNotFound
from app.modules.server import ssh


def _server():
    return SimpleNamespace(group_id=7, port=2222)


def _credential():
    return SimpleNamespace(
        id=9,
        group_id=7,
        name='test-credential',
        username='deploy',
        password='',
        passphrase='',
        private_key=None,
        key_enabled=0,
    )


@pytest.mark.security
def test_ssh_settings_accept_executed_peewee_result(monkeypatch):
    calls = []
    monkeypatch.setattr(ssh.server_sql, 'get_server_by_ip', lambda server_ip: _server())
    monkeypatch.setattr(
        ssh.cred_sql,
        'select_ssh',
        lambda **kwargs: calls.append(kwargs) or iter([_credential()]),
    )

    settings = ssh.return_ssh_keys_path('10.0.0.173')

    assert calls == [{'serv': '10.0.0.173'}]
    assert settings == {
        'enabled': 0,
        'user': 'deploy',
        'password': '',
        'key': None,
        'passphrase': '',
        'port': 2222,
    }


@pytest.mark.security
def test_ssh_settings_report_missing_credentials(monkeypatch):
    monkeypatch.setattr(ssh.server_sql, 'get_server_by_ip', lambda server_ip: _server())
    monkeypatch.setattr(ssh.cred_sql, 'select_ssh', lambda **kwargs: iter(()))

    with pytest.raises(RoxywiResourceNotFound):
        ssh.return_ssh_keys_path('10.0.0.173')


@pytest.mark.security
def test_explicit_credential_lookup_is_scoped_to_server_group(monkeypatch):
    calls = []
    monkeypatch.setattr(ssh.server_sql, 'get_server_by_ip', lambda server_ip: _server())
    monkeypatch.setattr(
        ssh.cred_sql,
        'select_ssh',
        lambda **kwargs: calls.append(kwargs) or iter([_credential()]),
    )

    ssh.return_ssh_keys_path('10.0.0.173', cred_id=9)

    assert calls == [{'group': 7, 'cred_id': 9, 'not_shared': True}]
