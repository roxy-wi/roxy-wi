import uuid
import configparser
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.modules.db.db_model import Cred
from app.modules.roxywi import common as roxywi_common
from app.modules.server import ssh


def _write_secret_config(path, secret):
    path.write_text(f'[main]\nsecret_phrase = {secret}\n', encoding='utf-8')


@pytest.mark.security
def test_existing_config_secret_is_read_at_credential_operation_time(monkeypatch, tmp_path):
    secret = Fernet.generate_key().decode('ascii')
    config_path = tmp_path / 'roxy-wi.cfg'
    _write_secret_config(config_path, secret)
    monkeypatch.delenv('ROXYWI_SECRET_PHRASE', raising=False)
    monkeypatch.setenv('ROXYWI_CONFIG_FILE', str(config_path))

    encrypted = ssh.crypt_password('existing-installation-password')

    assert ssh.decrypt_password(encrypted.decode('ascii')) == 'existing-installation-password'


@pytest.mark.security
def test_environment_placeholder_reports_that_it_overrides_valid_config(monkeypatch, tmp_path):
    config_path = tmp_path / 'roxy-wi.cfg'
    _write_secret_config(config_path, Fernet.generate_key().decode('ascii'))
    monkeypatch.setenv('ROXYWI_CONFIG_FILE', str(config_path))
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE', 'CHANGE_ME')

    with pytest.raises(RuntimeError, match='from ROXYWI_SECRET_PHRASE is set to CHANGE_ME'):
        ssh.crypt_password('password')


@pytest.mark.security
def test_config_placeholder_error_names_the_config_file(monkeypatch, tmp_path):
    config_path = tmp_path / 'roxy-wi.cfg'
    _write_secret_config(config_path, 'CHANGE_ME')
    monkeypatch.delenv('ROXYWI_SECRET_PHRASE', raising=False)
    monkeypatch.setenv('ROXYWI_CONFIG_FILE', str(config_path))

    with pytest.raises(RuntimeError) as exc_info:
        ssh.crypt_password('password')

    assert str(config_path) in str(exc_info.value)


@pytest.mark.security
def test_any_valid_non_placeholder_key_is_accepted(monkeypatch, tmp_path):
    config_path = tmp_path / 'roxy-wi.cfg'
    valid_key = '_B8avTpFFL19M8P9VyTiX42NyeyUaneV26kyftB2E_4='
    _write_secret_config(config_path, valid_key)
    monkeypatch.delenv('ROXYWI_SECRET_PHRASE', raising=False)
    monkeypatch.setenv('ROXYWI_CONFIG_FILE', str(config_path))

    encrypted = ssh.crypt_password('password')

    assert ssh.decrypt_password(encrypted.decode('ascii')) == 'password'


@pytest.mark.security
def test_default_config_uses_change_me_placeholder():
    config = configparser.ConfigParser()
    config.read(Path(__file__).resolve().parents[2] / 'roxy-wi.cfg')

    assert config.get('main', 'secret_phrase') == 'CHANGE_ME'


@pytest.mark.security
def test_damaged_credential_does_not_break_admin_credential_list(monkeypatch):
    credential = Cred.create(
        name=f'damaged-{uuid.uuid4().hex}',
        username='root',
        password='not-fernet-ciphertext',
        passphrase='not-fernet-ciphertext',
        group_id=1,
    )
    warnings = []
    monkeypatch.setattr(ssh.logger, 'warning', lambda message, **kwargs: warnings.append((message, kwargs)))

    try:
        result = ssh.get_creds(group_id=1, cred_id=credential.id, not_shared=True)
    finally:
        credential.delete_instance()

    assert len(result) == 1
    assert result[0]['password'] == ''
    assert result[0]['passphrase'] == ''
    assert {warning[1]['credential_field'] for warning in warnings} == {'password', 'passphrase'}


@pytest.mark.security
def test_admin_credential_list_does_not_hide_invalid_application_key(monkeypatch):
    credential = Cred.create(
        name=f'invalid-key-{uuid.uuid4().hex}',
        username='root',
        password='encrypted-value',
        group_id=1,
    )
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE', 'CHANGE_ME')

    try:
        with pytest.raises(RuntimeError, match='from ROXYWI_SECRET_PHRASE'):
            ssh.get_creds(group_id=1, cred_id=credential.id, not_shared=True)
    finally:
        credential.delete_instance()


@pytest.mark.security
def test_background_logging_does_not_require_request_context(monkeypatch):
    logged_events = []
    monkeypatch.setattr(
        roxywi_common.logger,
        'log',
        lambda level, message, **kwargs: logged_events.append((level, message, kwargs)),
    )

    roxywi_common.logging('10.0.0.173', 'error: Backend health check failed', service='HAProxy')

    assert logged_events == [(
        roxywi_common.logger.ERROR,
        'Backend health check failed',
        {
            'server_ip': '10.0.0.173',
            'service': 'HAProxy',
            'execution_context': 'background',
        },
    )]
