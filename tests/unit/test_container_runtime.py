from pathlib import Path
from contextlib import nullcontext

import yaml
import app as app_module

from app.modules.db.settings import DatabaseSettings
from app.modules.db.db_model import Setting
from app.modules.db import sql
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi import logger


def _config(tmp_path: Path, content: str) -> GetConfigVar:
    config_path = tmp_path / 'roxy-wi.cfg'
    config_path.write_text(content, encoding='utf-8')
    config = GetConfigVar()
    config.path_config = str(config_path)
    config.config.read(config_path)
    return config


def test_cfg_values_are_used_when_environment_is_absent(tmp_path, monkeypatch):
    monkeypatch.delenv('ROXYWI_LIB_PATH', raising=False)
    monkeypatch.delenv('ROXYWI_MAIN_LIB_PATH', raising=False)
    config = _config(tmp_path, '[main]\nlib_path = /cfg/lib\n')

    assert config.get_config_var('main', 'lib_path') == '/cfg/lib'


def test_environment_has_priority_over_cfg_even_when_empty(tmp_path, monkeypatch):
    config = _config(tmp_path, '[rabbitmq]\nrabbitmq_password = from-cfg\n')
    monkeypatch.setenv('ROXYWI_RABBITMQ_PASSWORD', '')

    assert config.get_config_var('rabbitmq', 'rabbitmq_password') == ''


def test_sqlite_database_settings_remain_supported(tmp_path, monkeypatch):
    database_path = tmp_path / 'from-env.db'
    monkeypatch.setenv('ROXYWI_DATABASE_ENGINE', 'sqlite')
    monkeypatch.setenv('ROXYWI_DB_PATH', str(database_path))
    config = _config(tmp_path, '[main]\nlib_path = /cfg/lib\n[mysql]\nenable = 1\n')

    settings = DatabaseSettings.load(config)

    assert settings.engine == 'sqlite'
    assert settings.sqlite_path == str(database_path)


def test_mysql_database_settings_use_env_then_cfg(tmp_path, monkeypatch):
    monkeypatch.delenv('ROXYWI_DATABASE_ENGINE', raising=False)
    monkeypatch.delenv('ROXYWI_MYSQL_ENABLE', raising=False)
    monkeypatch.setenv('ROXYWI_MYSQL_HOST', 'mysql-from-env')
    config = _config(
        tmp_path,
        '[main]\nlib_path = /cfg/lib\n'
        '[mysql]\nenable = 1\nmysql_host = mysql-from-cfg\nmysql_port = 3307\n'
        'mysql_db = cfg-db\nmysql_user = cfg-user\nmysql_password = cfg-password\n',
    )

    settings = DatabaseSettings.load(config)

    assert settings.engine == 'mysql'
    assert settings.mysql_host == 'mysql-from-env'
    assert settings.mysql_port == 3307
    assert settings.mysql_database == 'cfg-db'


def test_health_endpoints_report_initialized_schema(client):
    assert client.get('/health/live').get_json() == {'status': 'ok'}
    response = client.get('/health/ready')
    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok', 'database': 'ok'}


def test_application_setting_precedence_is_env_then_database_then_cfg(tmp_path, monkeypatch):
    parameter = 'container_precedence_test'
    environment_name = 'ROXYWI_CONTAINER_PRECEDENCE_TEST'
    config = _config(tmp_path, f'[main]\n{parameter} = from-cfg\n')
    monkeypatch.setattr(sql, '_config', config)
    monkeypatch.delenv(environment_name, raising=False)
    Setting.delete().where((Setting.param == parameter) & (Setting.group_id == 8765)).execute()
    Setting.create(
        param=parameter,
        value='from-database',
        section='main',
        desc='test',
        group_id=8765,
    )

    try:
        assert sql.get_setting(parameter, group_id=8765) == 'from-database'
        monkeypatch.setenv(environment_name, 'from-env')
        assert sql.get_setting(parameter, group_id=8765) == 'from-env'
        monkeypatch.delenv(environment_name)
        Setting.update(value=None).where(
            (Setting.param == parameter) & (Setting.group_id == 8765)
        ).execute()
        assert sql.get_setting(parameter, group_id=8765) == 'from-cfg'
    finally:
        Setting.delete().where((Setting.param == parameter) & (Setting.group_id == 8765)).execute()


def test_compose_manifests_are_parseable_and_use_no_shared_cache():
    project_root = Path(__file__).resolve().parents[2]
    for compose_file in ('docker-compose.yml', 'docker-compose.sqlite.yml'):
        document = yaml.safe_load(
            (project_root / 'docker' / compose_file).read_text(encoding='utf-8')
        )
        assert {'web', 'migrate', 'scheduler', 'service-events', 'operations'} <= set(document['services'])
        assert document['x-roxy-wi']['environment']['ROXYWI_CACHE_TYPE'] == 'NullCache'
        assert 'redis' not in document['services']


def test_helm_chart_uses_incidentrelay_directory_layout():
    project_root = Path(__file__).resolve().parents[2]
    chart_path = project_root / 'helm' / 'roxy-wi'
    chart = yaml.safe_load((chart_path / 'Chart.yaml').read_text(encoding='utf-8'))
    values = yaml.safe_load((chart_path / 'values.yaml').read_text(encoding='utf-8'))

    assert chart['name'] == 'roxy-wi'
    assert values['config']['cache']['type'] == 'NullCache'
    assert values['config']['main']['fullpath'] == '/var/www/haproxy-wi'
    assert values['config']['ansible']['private_data_dir'] == '/var/lib/roxy-wi/ansible'
    assert values['config']['ansible']['roles_path'] == '/var/lib/roxy-wi/ansible/roles'
    assert values['config']['ansible']['collections_path'] == '/var/lib/roxy-wi/ansible/collections'
    assert 'redis' not in values
    assert {
        'deployment-web.yaml',
        'deployment-scheduler.yaml',
        'deployment-service-events.yaml',
        'deployment-operations.yaml',
        'job-migrate.yaml',
        'service.yaml',
        'ingress.yaml',
    } <= {path.name for path in (chart_path / 'templates').iterdir()}


def test_default_package_config_uses_shared_paths_and_no_cache():
    project_root = Path(__file__).resolve().parents[2]
    config = GetConfigVar()
    config.path_config = str(project_root / 'roxy-wi.cfg')
    config.config.read(config.path_config)

    assert config.get_config_var('main', 'fullpath', use_environment=False) == '/var/www/haproxy-wi'
    assert config.get_config_var('main', 'lib_path', use_environment=False) == '/var/lib/roxy-wi'
    assert config.get_config_var('ansible', 'private_data_dir', use_environment=False) == '/var/lib/roxy-wi/ansible'
    assert config.get_config_var('ansible', 'roles_path', use_environment=False) == '/var/lib/roxy-wi/ansible/roles'
    assert config.get_config_var('ansible', 'collections_path', use_environment=False) == '/var/lib/roxy-wi/ansible/collections'
    assert config.get_config_var('cache', 'type', use_environment=False) == 'NullCache'


def test_standalone_container_workers_log_to_console(monkeypatch):
    sentinel = object()
    captured = {}

    def setup_logger(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(logger, '_logger', None)
    monkeypatch.setattr(logger, 'setup_logger', setup_logger)
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_MODE', 'compose')
    monkeypatch.setenv('ROXYWI_LOG_CONSOLE', '1')
    monkeypatch.setenv('ROXYWI_LOG_FILE_ENABLED', '0')

    assert logger.get_logger() is sentinel
    assert captured['console_logging'] is True
    assert captured['file_logging'] is False


def test_existing_database_is_migrated_before_model_indexes_are_created(monkeypatch):
    calls = []

    class ExistingDatabase:
        @staticmethod
        def connection_context():
            return nullcontext()

        @staticmethod
        def get_tables():
            return ['user', 'servers', 'settings', 'migrations']

    monkeypatch.setattr(app_module.BaseModel._meta, 'database', ExistingDatabase())
    monkeypatch.setattr(app_module, 'migrate', lambda: calls.append('migrate') or True)
    monkeypatch.setattr(app_module, 'create_tables', lambda: calls.append('create_tables'))
    monkeypatch.setattr(app_module, 'default_values', lambda: calls.append('default_values'))
    monkeypatch.setattr(
        app_module,
        'mark_all_migrations_applied',
        lambda: calls.append('mark_all_migrations_applied'),
    )

    app_module.initialize_database()

    assert calls == ['migrate', 'create_tables', 'default_values']
