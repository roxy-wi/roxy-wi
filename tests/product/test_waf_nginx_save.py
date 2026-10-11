import json
from pathlib import Path
import shlex
import shutil
from types import SimpleNamespace

import pytest

from app.modules.config import config, candidate as transaction
from app.modules.db.db_model import Setting, WafRules


@pytest.fixture
def editor(product, monkeypatch, request):
    service = getattr(request, 'param', 'nginx')
    root = product.root / service
    (root / 'waf/rules').mkdir(parents=True)
    target = root / 'waf/rules/test.conf'
    target.write_text('# original\n')
    main = root / ('nginx.conf' if service == 'nginx' else 'waf/modsecurity.conf')
    main.write_text('# main\n')
    remote_main = f'/srv/{service} custom/' + ('nginx.conf' if service == 'nginx' else 'waf/modsecurity.conf')
    rule = WafRules.create(serv=product.server.ip, service=service, rule_name='Test', rule_file='test.conf', en=1)
    for key, value in {f'{service}_dir': f'/srv/{service} custom', f'{service}_config_path': remote_main,
                       'tmp_config_path': str(product.root)}.items():
        Setting.update(value=value).where(Setting.param == key, Setting.group_id == 1).execute()
    state = SimpleNamespace(rule=rule, root=root, target=target, uploads={}, calls=[], action_results=[], lost=False,
                            service=service, pid=1, clock=0)

    def upload(server, remote, local):
        staged = product.root / Path(remote).name
        shutil.copyfile(local, staged)
        state.uploads[remote] = staged

    def run(arguments, **kwargs):
        if arguments[0] == 'dos2unix':
            return SimpleNamespace(returncode=0)
        if arguments[:2] == ['systemctl', 'show']:
            return SimpleNamespace(returncode=0, stdout=b'loaded')
        state.calls.append((arguments, target.read_text()))
        if arguments[0] == 'nginx':
            status = int('invalid' in target.read_text())
        else:
            status = state.action_results.pop(0) if state.action_results else 0
            if not status:
                state.pid += 1
        return SimpleNamespace(returncode=status, stdout=b'')

    def ssh(server, command, **kwargs):
        tokens = shlex.split(command)
        if tokens[:3] == ['sudo', 'rm', '-f']:
            state.uploads[tokens[-1]].unlink(missing_ok=True)
            return ''
        assert kwargs['rc'] == 1 and kwargs['timeout'] == transaction.REMOTE_TIMEOUT
        spec = json.loads(tokens[-1])
        assert spec['target'] == f'/srv/{service} custom/waf/rules/test.conf'
        assert spec['main'] == remote_main
        spec.update(target=str(target), candidate=str(state.uploads[spec['candidate']]), main=str(main))
        result = transaction.execute(spec)
        if state.lost:
            state.lost = False
            raise OSError('synthetic lost SSH response')
        return json.dumps(result)

    monkeypatch.setattr(config, 'upload', upload)
    monkeypatch.setattr(config.server_mod, 'ssh_command', ssh)
    monkeypatch.setattr(transaction.subprocess, 'run', run)
    if service == 'haproxy':
        # The filesystem transaction is real. Process discovery and protocol I/O
        # are covered separately; this fixture models readiness after rule loading.
        monkeypatch.setattr(transaction._HaproxyWafValidator, 'process_id', lambda _: state.pid)
        monkeypatch.setattr(transaction._HaproxyWafValidator, 'listener_port', lambda *a: 12345)
        monkeypatch.setattr(transaction._HaproxyWafValidator, 'ready', lambda *a: 'invalid' not in target.read_text())

        def tick(seconds):
            state.clock += seconds

        monkeypatch.setattr(transaction, 'time', SimpleNamespace(monotonic=lambda: state.clock, sleep=tick))
    return state


@pytest.mark.parametrize('action', ['save', 'reload', 'restart'])
def test_real_save_transaction_checks_candidate_and_retries_after_failure(product_client, product, editor, action):
    url = f'/waf/nginx/{product.server.ip}/rule/{editor.rule.id}/save'
    response = product_client.post(url, json={'action': action, 'config': '# invalid rule\n'})
    assert response.status_code == 500 and response.json['status'] == 'failed'
    assert editor.target.read_text() == '# original\n'
    assert len(editor.calls) == 2 and all(args[0] == 'nginx' for args, _ in editor.calls)
    assert not list(product.root.glob('waf-save-*'))
    assert not list(editor.target.parent.glob('.roxywi-*'))
    response = product_client.post(url, json={'action': action, 'config': '# corrected rule\n'})
    assert response.status_code == 200 and response.json['status'] == 'ok'
    assert editor.target.read_text() == '# corrected rule\n'
    if action == 'save':
        assert len(editor.calls) == 4
    else:
        assert editor.calls[-1] == (['sh', '-c', f'sudo systemctl {action} nginx'], '# corrected rule\n')


def test_failed_reload_restores_old_file_and_recovers_before_reporting_error(product_client, product, editor):
    editor.action_results = [1, 0]
    response = product_client.post(f'/waf/nginx/{product.server.ip}/rule/{editor.rule.id}/save',
                                   json={'action': 'reload', 'config': '# updated\n'})
    assert response.status_code == 500
    assert 'previous file was restored' in response.json['error']
    assert editor.target.read_text() == '# original\n'
    assert [content for args, content in editor.calls if args[0] == 'sh'] == ['# updated\n', '# original\n']


@pytest.mark.parametrize('editor', ['haproxy', 'nginx'], indirect=True)
def test_lost_response_is_not_success_and_repeat_save_is_safe(product_client, product, editor):
    editor.lost = True
    url = f'/waf/{editor.service}/{product.server.ip}/rule/{editor.rule.id}/save'
    payload = {'action': 'save', 'config': '# updated\n'}
    assert product_client.post(url, json=payload).status_code == 500
    assert editor.target.read_text() == '# updated\n'
    assert product_client.post(url, json=payload).status_code == 200
    assert editor.target.read_text() == '# updated\n'
    assert not list(editor.target.parent.glob('.roxywi-*'))


@pytest.mark.parametrize('editor', ['haproxy'], indirect=True)
def test_haproxy_save_only_writes_file_without_restart(product_client, product, editor):
    response = product_client.post(f'/waf/haproxy/{product.server.ip}/rule/{editor.rule.id}/save',
                                   json={'action': 'save', 'config': '# invalid\n'})
    assert response.status_code == 200 and response.json['status'] == 'ok'
    assert editor.target.read_text() == '# invalid\n'
    assert not editor.calls


@pytest.mark.parametrize('editor', ['haproxy'], indirect=True)
def test_haproxy_failed_rule_recovers_and_retry_applies_new_rule(product_client, product, editor):
    url = f'/waf/haproxy/{product.server.ip}/rule/{editor.rule.id}/save'
    response = product_client.post(url, json={'action': 'restart', 'config': '# invalid\n'})
    assert response.status_code == 500
    assert 'previous file was restored' in response.json['error']
    assert editor.target.read_text() == '# original\n'
    assert editor.calls == [(['sh', '-c', 'sudo systemctl restart waf'], '# invalid\n'),
                            (['sh', '-c', 'sudo systemctl restart waf'], '# original\n')]
    response = product_client.post(url, json={'action': 'restart', 'config': '# corrected\n'})
    assert response.status_code == 200 and response.json['status'] == 'ok'
    assert editor.target.read_text() == '# corrected\n'
    assert not list(product.root.glob('waf-save-*'))
    assert all(not path.exists() for path in editor.uploads.values())
