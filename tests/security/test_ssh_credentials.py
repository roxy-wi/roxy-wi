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


@pytest.mark.parametrize('fail_publish', [False, True])
def test_private_key_cache_is_private_and_never_published_partially(tmp_path, monkeypatch, fail_publish):
    import os
    from pathlib import Path
    import stat
    from types import SimpleNamespace
    from app.modules.server import ssh
    keys = tmp_path / 'keys'; keys.mkdir()
    destination = keys / 'cache-test_Default.pem'
    destination.write_text('old-complete-key\n'); destination.chmod(0o600)
    monkeypatch.setattr(ssh.get_config, 'get_config_var', lambda *_args: str(tmp_path))
    monkeypatch.setattr(ssh.group_sql, 'get_group', lambda _id: SimpleNamespace(name='Default'))
    monkeypatch.setattr(ssh.cred_sql, 'get_ssh', lambda _id: SimpleNamespace(private_key='new-complete-key'))
    monkeypatch.setattr(ssh, 'decrypt_password', lambda value: value)
    publish = os.replace
    calls = []
    def replace(source, target):
        calls.append(target)
        assert destination.read_text() == 'old-complete-key\n'
        assert Path(source).read_text() == 'new-complete-key\n'
        assert stat.S_IMODE(Path(source).stat().st_mode) == 0o600
        if fail_publish: raise OSError('simulated publication failure')
        publish(source, target)
    monkeypatch.setattr(ssh.os, 'replace', replace)
    credential = SimpleNamespace(id=9, group_id=1, name='cache-test')
    if fail_publish:
        with pytest.raises(OSError): ssh._return_correct_ssh_file(credential)
        assert destination.read_text() == 'old-complete-key\n'
    else:
        assert ssh._return_correct_ssh_file(credential) == str(destination)
        assert destination.read_text() == 'new-complete-key\n'
    assert len(calls) == 1 and stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert not list(keys.glob('.ssh-key-*'))
