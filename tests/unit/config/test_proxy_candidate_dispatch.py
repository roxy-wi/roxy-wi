"""Proxy validation and saves use the same managed configuration transaction."""

import json
import shlex
from types import SimpleNamespace

import pytest

from app.modules.config import config, candidate
from app.modules.service import common


@pytest.fixture(params=['nginx', 'apache', 'keepalived'])
def proxy(request, monkeypatch):
    service = request.param
    root = '/etc/apache2' if service == 'apache' else f'/etc/{service}'
    settings = dict(main=f'{root}/main.conf', root=root, container='proxy', service_unit='',
                    container_runtime=dict(engine='podman', owner='proxy', unit='proxy.service'))
    monkeypatch.setattr(common, 'proxy_runtime_settings', lambda *_: dict(settings))
    monkeypatch.setattr(config.server_sql, 'get_server_by_ip', lambda _: SimpleNamespace(server_id=11))
    monkeypatch.setattr(config.sql, 'get_setting', lambda key: {
        'tmp_config_path': '/tmp', 'keepalived_config_path': settings['main']}[key])
    monkeypatch.setattr(config.service_sql, 'select_service_setting',
                        lambda *_: pytest.fail('Runtime settings were already resolved'))
    monkeypatch.setattr(common, 'is_not_allowed_to_restart', lambda *_: False)
    monkeypatch.setattr(config.service_action, 'get_action_command', lambda *_: 'sudo systemctl reload proxy')
    return service, settings


@pytest.mark.parametrize('action', ['save', 'reload', 'restart'])
def test_proxy_save_keeps_runtime_and_revision_in_shared_transaction(proxy, action):
    service, settings = proxy
    command = config._generate_command(service, 11, action, settings['main'], '/tmp/upload.conf',
                                       '192.0.2.11', expected_sha256='a' * 64)
    spec = json.loads(shlex.split(command)[-1])
    assert spec['service'] == service and spec['action'] == action
    assert spec['target'] == settings['main'] and spec['candidate'] == '/tmp/upload.conf'
    assert spec['container_runtime'] == settings['container_runtime'] and spec['container'] == 'proxy'
    assert spec['expected_sha256'] == 'a' * 64
    assert bool(spec['action_command']) is (action != 'save')


@pytest.mark.parametrize('flow', ['candidate', 'active'])
@pytest.mark.parametrize('valid', [False, True])
def test_proxy_validation_propagates_shared_validator_result(proxy, flow, valid, monkeypatch):
    service, settings = proxy
    calls = []
    uploads = []
    monkeypatch.setattr(config, 'upload', lambda *args: uploads.append(args))
    monkeypatch.setattr(config.subprocess, 'run', lambda *_args, **_kwargs: None)

    def ssh(_address, command, **options):
        calls.append((json.loads(shlex.split(command)[-1]), options))
        return json.dumps({'status': 'ok'} if valid else {'status': 'failed', 'code': 'validation_failed'})

    monkeypatch.setattr(config.server_mod, 'ssh_command', ssh)

    def validate():
        if flow == 'candidate':
            return config.validate_candidate_config('192.0.2.11', 'incoming.conf', service, settings['main'])
        return common.check_service_config('192.0.2.11', 11, service)

    if valid:
        validate()
    else:
        with pytest.raises(candidate.CandidateApplyError):
            validate()
    assert len(calls) == 1
    spec, options = calls[0]
    assert spec['service'] == service and spec['action'] == ('test' if flow == 'candidate' else 'check')
    assert spec['container_runtime'] == settings['container_runtime']
    assert options['rc'] == 1 and options['timeout'] == candidate.REMOTE_TIMEOUT
    assert len(uploads) == (1 if flow == 'candidate' else 0)
