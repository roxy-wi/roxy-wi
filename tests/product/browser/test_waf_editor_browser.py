from contextlib import contextmanager
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect

from app.modules.config import config
from app.modules.db.db_model import Setting, WafRules


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]
LOCALES = ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh']
TEXT = '# Правило WAF · règle · 规则\n'


@pytest.fixture
def waf_editor(product, monkeypatch):
    state = SimpleNamespace(fail=False, fail_read=False, uploads=[], commands=[])
    state.rules = {service: WafRules.create(serv=product.server.ip, service=service, rule_name='Test',
                                            rule_file='test.conf', en=1) for service in ('haproxy', 'nginx')}
    Setting.update(value=str(product.root) + '/').where(Setting.param == 'tmp_config_path', Setting.group_id == 1).execute()

    @contextmanager
    def connect(server):
        def download(remote, local):
            if state.fail_read:
                raise OSError('synthetic connection failure')
            Path(local).write_text(TEXT, encoding='utf-8')
        yield SimpleNamespace(get_sftp=download)

    def upload(server, remote, local):
        state.uploads.append(Path(local).read_text(encoding='utf-8'))

    def ssh(server, command, **kwargs):
        if command.startswith('sudo rm'):
            return ''
        state.commands.append(command)
        if state.fail:
            raise OSError('synthetic apply failure')
        return ''

    monkeypatch.setattr(config.mod_ssh, 'ssh_connect', connect)
    monkeypatch.setattr(config, 'upload', upload)
    monkeypatch.setattr(config.server_mod, 'ssh_command', ssh)
    monkeypatch.setattr(config.subprocess, 'run', lambda *a, **kw: None)
    return state


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('service,action', [('haproxy', 'restart'), ('nginx', 'reload')])
def test_waf_editor_preserves_changes_on_failure_and_retries(logged_in, product_url, product, waf_editor, locale, service, action):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    url = f'/waf/{service}/{product.server.ip}/rule/{waf_editor.rules[service].id}'
    page.goto(product_url + url)
    editor = page.locator('#saveconfig')
    expect(editor).to_be_visible()
    assert page.evaluate('myCodeMirror.getValue()') == TEXT
    assert not list(product.root.glob('waf-read-*'))
    changed = TEXT + '# changed\n'
    page.evaluate('(text) => myCodeMirror.setValue(text)', changed)
    waf_editor.fail = True
    with page.expect_response(lambda response: response.url.endswith(url + '/save')) as failed:
        editor.locator(f'button[value="{action}"]').click()
    assert failed.value.status == 500
    expect(page.locator('.toast-error')).to_contain_text(editor.get_attribute('data-save-error'))
    expect(page.locator('.toast-success')).to_have_count(0)
    expect(editor.locator(f'button[value="{action}"]')).to_be_enabled()
    assert page.evaluate('myCodeMirror.getValue()') == changed
    assert page.evaluate("!!($._data(window, 'events') || {}).beforeunload")
    assert not list(product.root.glob('waf-save-*'))

    waf_editor.fail = False
    with page.expect_response(lambda response: response.url.endswith(url + '/save')) as saved:
        editor.locator(f'button[value="{action}"]').click()
    assert saved.value.status == 200
    expect(page.locator('.toast-success')).to_contain_text(editor.get_attribute(f'data-{action}-success'))
    expect(page.locator('.toast-error')).to_have_count(0)
    assert not page.evaluate("!!($._data(window, 'events') || {}).beforeunload")
    assert waf_editor.uploads == [changed, changed]
    target = 'waf' if service == 'haproxy' else 'nginx'
    assert all(f'systemctl {action} {target}' in command for command in waf_editor.commands)


@pytest.mark.parametrize('locale', LOCALES)
def test_waf_read_failure_is_localized_and_has_no_editor(logged_in, product_url, product, waf_editor, app, locale):
    waf_editor.fail_read = True
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    response = page.goto(f'{product_url}/waf/nginx/{product.server.ip}/rule/{waf_editor.rules["nginx"].id}')
    assert response.status == 500
    message = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_editor['read_failed']
    expect(page.locator('h4')).to_contain_text(message)
    expect(page.locator('#saveconfig')).to_have_count(0)
    assert not list(product.root.glob('waf-read-*'))


def test_edits_during_save_remain_unsaved_and_double_submit_is_ignored(logged_in, product_url, product, waf_editor):
    page = logged_in
    url = f'/waf/nginx/{product.server.ip}/rule/{waf_editor.rules["nginx"].id}'
    page.goto(product_url + url)
    expect(page.locator('#saveconfig')).to_be_visible()
    pending = []
    page.route('**' + url + '/save', lambda route: pending.append(route))
    page.evaluate('myCodeMirror.setValue("# first")')
    page.locator('#saveconfig button[value="save"]').click()
    expect(page.locator('#saveconfig button[value="save"]')).to_be_disabled()
    page.evaluate('''() => {
        document.querySelector('#saveconfig').requestSubmit();
        myCodeMirror.setValue('# newer unsaved changes');
    }''')
    assert len(pending) == 1
    pending[0].fulfill(json={'status': 'ok', 'data': 'saved'})
    expect(page.locator('.toast-success')).to_be_visible()
    expect(page.locator('#saveconfig button[value="save"]')).to_be_enabled()
    assert page.evaluate('myCodeMirror.getValue()') == '# newer unsaved changes'
    assert page.evaluate("!!($._data(window, 'events') || {}).beforeunload")
