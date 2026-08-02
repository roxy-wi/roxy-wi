from pathlib import Path

import pytest

from app import create_db
from app.modules.db import group


@pytest.mark.security
def test_service_passwords_are_random_and_support_rabbitmq_override(monkeypatch):
    first_password = create_db._new_service_password()
    second_password = create_db._new_service_password()

    assert len(first_password) >= 32
    assert first_password != second_password
    assert first_password not in {'password', 'roxy-wi123'}

    monkeypatch.setenv('ROXYWI_RABBITMQ_PASSWORD', 'ConfiguredRabbitPassword!')
    assert create_db._new_service_password('ROXYWI_RABBITMQ_PASSWORD') == 'ConfiguredRabbitPassword!'


@pytest.mark.security
def test_short_configured_service_password_is_rejected(monkeypatch):
    monkeypatch.setenv('ROXYWI_RABBITMQ_PASSWORD', 'too-short')

    with pytest.raises(RuntimeError, match='at least 12 characters'):
        create_db._new_service_password('ROXYWI_RABBITMQ_PASSWORD')


@pytest.mark.security
def test_new_group_gets_distinct_random_stats_passwords(monkeypatch):
    captured_settings = []

    class InsertQuery:
        def execute(self):
            return len(captured_settings)

    class SettingRecorder:
        @staticmethod
        def insert_many(settings):
            captured_settings.extend(settings)
            return InsertQuery()

    monkeypatch.setattr(group, 'Setting', SettingRecorder)

    group.add_setting_for_new_group(42)

    passwords = {
        setting['param']: setting['value']
        for setting in captured_settings
        if setting['param'].endswith('_stats_password')
    }
    assert set(passwords) == {
        'haproxy_stats_password', 'nginx_stats_password', 'apache_stats_password'
    }
    assert len(set(passwords.values())) == 3
    assert all(len(password) >= 32 for password in passwords.values())
    assert 'password' not in passwords.values()


@pytest.mark.security
def test_bootstrap_sources_do_not_contain_known_default_passwords():
    project_root = Path(__file__).resolve().parents[2]
    source = '\n'.join(
        (project_root / relative_path).read_text(encoding='utf-8')
        for relative_path in ('app/create_db.py', 'app/modules/db/group.py')
    )

    assert "'value': 'password'" not in source
    assert 'roxy-wi123' not in source


@pytest.mark.security
def test_lets_encrypt_ui_does_not_evaluate_api_data_as_code():
    project_root = Path(__file__).resolve().parents[2]
    source = (project_root / 'app/static/js/ssl.js').read_text(encoding='utf-8')

    assert "eval(data['domains'])" not in source
    assert "domains.join(', ')" in source
