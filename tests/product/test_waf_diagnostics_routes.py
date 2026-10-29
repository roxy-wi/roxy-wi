"""WAF diagnostic responses through authenticated product routes."""
import json
import shlex

import pytest

import app.modules.service.common as service_common
from app.modules.config import config
from app.modules.db.db_model import UserGroups, Waf, WafNginx
from app.modules.roxywi import auth, waf


LOCALES = ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh']


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_status_details_are_localized_and_keep_mode_and_apply_controls(product_client, product, waf_modes, app, service, locale):
    product_client.set_cookie('lang', locale)
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_diagnostics
    assert messages.keys() == app.jinja_env.get_template('languages/en.html').module.waf_diagnostics.keys()
    response = product_client.get(f'/waf/overview/{service}/{product.server.ip}')
    assert response.status_code == 200
    assert '<details data-waf-diagnostics' in response.text
    assert messages['summary_' + service] in response.text
    assert 'scope_nginx' not in messages
    if service == 'haproxy':
        assert 'scope_haproxy' not in messages
        assert 'SPOE' not in response.text
    assert messages['registered'] not in response.text
    assert f'<dt>{messages["installation"]}</dt>' not in response.text
    assert 'data-confirmed-mode="On"' in response.text
    assert 'data-waf-apply-button' in response.text
    assert 'installWaf(' not in response.text


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('failure', ['ssh', 'empty', 'malformed', 'unexpected', 'secret'])
def test_unknown_results_never_show_stopped_or_uninstalled(product_client, product, waf_modes, service, failure):
    if failure == 'ssh':
        waf_modes.diagnostic_error = OSError('sensitive-command-output')
    else:
        waf_modes.diagnostics[service] = {
            'empty': None, 'malformed': 'not-json', 'unexpected': {'status': 'ok'},
            'secret': {**waf_modes.diagnostics[service], 'error': 'sensitive-command-output'},
        }[failure]
    response = product_client.get(f'/waf/overview/{service}/{product.server.ip}')
    assert response.status_code == 200
    assert 'data-process="unknown"' in response.text
    assert 'connection' in response.text
    assert 'serverDown' not in response.text and 'serverUp' not in response.text
    assert 'installWaf(' not in response.text and 'sensitive-command-output' not in response.text
    assert 'data-waf-apply-button' in response.text


@pytest.mark.parametrize('values,hint,tone', [
    ({'process': 'stopped', 'check': 'not_checked'}, 'stopped', 'serverDown'),
    ({'process': 'missing', 'check': 'not_checked', 'error': 'process_unavailable'}, 'missing', 'serverDown'),
    ({'check': 'invalid', 'module': 'unknown'}, 'invalid', 'serverWarn'),
    ({'module': 'disabled'}, 'module_disabled', 'serverWarn'),
    ({'module': 'mixed'}, 'module_mixed', 'serverWarn'),
    ({'module': 'not_configured'}, 'module_not_configured', 'serverWarn'),
    ({'error': 'config_unavailable', 'check': 'not_checked'}, 'config_unavailable', 'serverWarn'),
])
def test_details_explain_failure_and_remedy(product_client, product, waf_modes, app, values, hint, tone):
    waf_modes.diagnostics['nginx'].update(values)
    response = product_client.get(f'/waf/overview/nginx/{product.server.ip}')
    assert response.status_code == 200
    assert app.jinja_env.get_template('languages/en.html').module.waf_diagnostics[hint + '_hint'] in response.text
    badge = {'serverDown': 'stopped', 'serverWarn': 'unavailable'}[tone]
    assert 'rw-status-badge rw-status-' + badge in response.text


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_unregistered_waf_does_not_trigger_diagnostics(product_client, product, waf_modes, monkeypatch, service):
    (Waf if service == 'haproxy' else WafNginx).delete().execute()
    def unexpected(*args, **kwargs):
        pytest.fail('Unregistered WAF must not be probed')
    monkeypatch.setattr(waf.server_mod, 'ssh_command', unexpected)
    response = product_client.get(f'/waf/overview/{service}/{product.server.ip}')
    assert response.status_code == 200 and 'installWaf(' in response.text
    assert 'data-waf-diagnostics' not in response.text


@pytest.mark.parametrize('rejection', ['service_permission', 'other_group'])
def test_diagnostics_preserve_access_checks(product_client, product, waf_modes, monkeypatch, rejection):
    ip = product.server.ip
    if rejection == 'service_permission':
        monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: False)
    else:
        UserGroups.update(user_role_id=2).where(UserGroups.user_id == product.admin.user_id).execute()
        ip = product.other.ip
    def unexpected(*args, **kwargs):
        pytest.fail('Rejected diagnostics must not reach SSH')
    monkeypatch.setattr(waf.server_mod, 'ssh_command', unexpected)
    assert product_client.get(f'/waf/overview/nginx/{ip}').status_code == 403


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('dockerized', ['0', '1'])
def test_diagnostics_share_paths_and_runtime_settings_with_apply(product_client, product, waf_modes, monkeypatch, service, dockerized):
    settings = {'nginx_config_path': '/srv/custom/nginx.conf', 'nginx_container_name': 'custom-nginx',
                'waf_container_name': 'custom-waf'}
    original = config.sql.get_setting
    monkeypatch.setattr(config.sql, 'get_setting', lambda name, *a, **kw: settings[name] if name in settings else original(name, *a, **kw))
    original_setting = config.service_sql.select_service_setting
    monkeypatch.setattr(config.service_sql, 'select_service_setting',
                        lambda server_id, service, key: dockerized if key == 'dockerized'
                        else original_setting(server_id, service, key))
    captured = []
    original_ssh = waf.server_mod.ssh_command
    def ssh(ip, command, **kwargs):
        if kwargs.get('timeout') != 90:
            return original_ssh(ip, command, **kwargs)
        captured.append(json.loads(shlex.split(command)[-1]))
        return json.dumps(waf_modes.diagnostics[service])
    monkeypatch.setattr(waf.server_mod, 'ssh_command', ssh)
    with product_client:
        response = product_client.get(f'/waf/overview/{service}/{product.server.ip}')
        assert response.status_code == 200 and 'rw-status-badge rw-status-running' in response.text
        expected = service_common.waf_runtime_settings(service, product.server.server_id)
    spec = captured[0]
    assert {key: spec[key] for key in ('main', 'container', 'service_unit')} == expected
    assert spec['container'] == (settings[('nginx' if service == 'nginx' else 'waf') + '_container_name'] if dockerized == '1' else '')
    assert spec['target'] == f'/srv/{service} custom/waf/modsecurity.conf'
