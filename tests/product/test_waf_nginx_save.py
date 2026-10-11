import json
from pathlib import Path
import shlex
import shutil
from types import SimpleNamespace

import pytest

from app.modules.config import config, candidate as transaction
from app.modules.db.db_model import Setting, WafRules


@pytest.fixture
def editor(product, monkeypatch):
    root = product.root / 'nginx'
    (root / 'waf/rules').mkdir(parents=True)
    target = root / 'waf/rules/test.conf'
    target.write_text('# original\n')
    (root / 'nginx.conf').write_text('# main\n')
    rule = WafRules.create(serv=product.server.ip, service='nginx', rule_name='Test', rule_file='test.conf', en=1)
    for key, value in {'nginx_dir': '/srv/nginx custom', 'nginx_config_path': '/srv/nginx custom/nginx.conf',
                       'tmp_config_path': str(product.root)}.items():
        Setting.update(value=value).where(Setting.param == key, Setting.group_id == 1).execute()
    state = SimpleNamespace(rule=rule, root=root, target=target, uploads={}, calls=[], action_results=[], lost=False)

    def upload(server, remote, local):
        staged = product.root / Path(remote).name
        shutil.copyfile(local, staged)
        state.uploads[remote] = staged

    def run(arguments, **kwargs):
        if arguments[0] == 'dos2unix':
            return SimpleNamespace(returncode=0)
        state.calls.append((arguments, target.read_text()))
        if arguments[0] == 'nginx':
            status = int('invalid' in target.read_text())
        else:
            status = state.action_results.pop(0) if state.action_results else 0
        return SimpleNamespace(returncode=status, stdout=b'')

    def ssh(server, command, **kwargs):
        tokens = shlex.split(command)
        if tokens[:3] == ['sudo', 'rm', '-f']:
            state.uploads[tokens[-1]].unlink(missing_ok=True)
            return ''
        assert kwargs['rc'] == 1 and kwargs['timeout'] == transaction.REMOTE_TIMEOUT
        spec = json.loads(tokens[-1])
        assert spec['target'] == '/srv/nginx custom/waf/rules/test.conf'
        assert spec['main'] == '/srv/nginx custom/nginx.conf'
        spec.update(target=str(target), candidate=str(state.uploads[spec['candidate']]), main=str(root / 'nginx.conf'))
        result = transaction.execute(spec)
        if state.lost:
            state.lost = False
            raise OSError('synthetic lost SSH response')
        return json.dumps(result)

    monkeypatch.setattr(config, 'upload', upload)
    monkeypatch.setattr(config.server_mod, 'ssh_command', ssh)
    monkeypatch.setattr(transaction.subprocess, 'run', run)
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


def test_lost_response_is_not_success_and_repeat_save_is_safe(product_client, product, editor):
    editor.lost = True
    url = f'/waf/nginx/{product.server.ip}/rule/{editor.rule.id}/save'
    payload = {'action': 'save', 'config': '# updated\n'}
    assert product_client.post(url, json=payload).status_code == 500
    assert editor.target.read_text() == '# updated\n'
    assert product_client.post(url, json=payload).status_code == 200
    assert editor.target.read_text() == '# updated\n'
    assert not list(editor.target.parent.glob('.roxywi-*'))
