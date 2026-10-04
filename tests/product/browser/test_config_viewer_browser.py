"""Viewer interactions with real routes/templates; only remote SSH is replaced."""
import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from app.modules.config import config as config_mod, common as config_common
from app.modules.db.db_model import HaproxySection, ConfigVersion
from app.modules.roxywi.class_models import HaproxyGlobalRequest


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]

TEXT = ('# Example configuration\n\nglobal\n    daemon\n\n'
        'frontend public\n    bind :80\n    default_backend web\n\n'
        'backend web\n    server one 192.0.2.12:80 check\n'
        '    # <script>window.viewerInjection = true</script>\n')


@pytest.fixture
def remote_config(monkeypatch):
    def download(server, path, **kwargs):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(TEXT, encoding='utf-8', newline='')
    monkeypatch.setattr(config_mod, 'get_config', download)


def test_viewer_accordion_search_source_and_repeat_loading(logged_in, product_url, remote_config):
    page = logged_in
    page.goto(product_url + '/config/haproxy/192.0.2.11/show')
    viewer = page.locator('#config-viewer')
    expect(viewer.locator('.cv-section')).to_have_count(4)
    expect(viewer.locator('.cv-copy')).to_have_text('Copy file')
    viewer.locator('.cv-expand').click()
    expect(viewer.locator('details[open]')).to_have_count(4)
    expect(viewer.locator('.cv-line')).to_have_count(12)
    assert page.evaluate('window.viewerInjection') is None
    viewer.locator('.cv-search').fill('web')
    expect(viewer.locator('.cv-status')).to_contain_text('1/2')
    expect(viewer.locator('details:not([hidden])')).to_have_count(2)
    viewer.locator('.cv-next').click()
    expect(viewer.locator('.cv-status')).to_contain_text('2/2')
    expect(viewer.locator('mark.cv-current')).to_have_count(1)
    viewer.locator('[data-cv-mode="raw"]').click()
    expect(viewer.locator('.cv-raw .cv-line')).to_have_count(12)
    viewer.locator('.cv-search').fill('not in this config')
    expect(viewer.locator('.cv-empty')).to_be_visible()
    viewer.locator('.cv-search').fill('')
    expect(viewer.locator('.cv-empty')).to_be_hidden()
    viewer.locator('.cv-search').press('a')
    expect(viewer.locator('[data-cv-mode="raw"]')).to_have_attribute('aria-pressed', 'true')
    viewer.locator('.cv-search').fill('')
    viewer.locator('[data-cv-mode="raw"]').press('a')
    expect(viewer.locator('[data-cv-mode="sections"]')).to_have_attribute('aria-pressed', 'true')
    page.evaluate('showConfig()')
    expect(viewer.locator('[data-cv-mode="sections"]')).to_have_attribute('aria-pressed', 'true')
    viewer.locator('.cv-expand').click()
    expect(viewer.locator('details[open]')).to_have_count(4)
    page.set_viewport_size({'width': 600, 'height': 1000})
    assert viewer.evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')


def test_add_section_opens_form_and_manual_section_opens_text(logged_in, product_url, product, remote_config, monkeypatch):
    HaproxySection.create(server_id=product.server.server_id, type='global', name='global',
                          config=HaproxyGlobalRequest(daemon=True).model_dump(mode='json'))
    page = logged_in
    page.goto(product_url + '/config/haproxy/192.0.2.11/show')
    viewer = page.locator('#config-viewer')
    global_section = viewer.locator('details').filter(has=page.locator('summary .cv-title', has_text='global'))
    global_section.locator('summary').click()
    global_section.locator('.cv-edit-section').click()
    expect(page.locator('#edit-section')).to_be_visible()
    expect(page.locator('#edit-global')).to_be_visible()
    page.locator('.ui-dialog-titlebar-close:visible').click()
    manual = viewer.locator('details').filter(has=page.locator('summary .cv-title', has_text='backend web'))
    manual.locator('summary').click()
    manual.locator('.cv-edit-section').click()
    expect(page).to_have_url(re.compile(r'/config/section/haproxy/192\.0\.2\.11/backend%20web\?file_path=.*section_line=10'))
    expect(page.locator('#saveconfig input[name="file_path"]')).to_have_value('/etc/haproxy/haproxy.cfg')
    assert page.evaluate('myCodeMirror.getValue()') == TEXT[TEXT.rindex('backend web\n'):]
    uploads = []
    def upload(server, path, action, service, **kwargs):
        uploads.append((server, Path(path).read_text(encoding='utf-8'), action, kwargs['config_file_name']))
        return 'Configuration file is valid'
    monkeypatch.setattr(config_mod, 'master_slave_upload_and_restart', upload)
    page.evaluate('myCodeMirror.setValue("backend web\\n    server two 192.0.2.13:80 check\\n")')
    with page.expect_response(lambda response: '/section/haproxy/' in response.url and response.request.method == 'POST') as saved:
        page.locator('#saveconfig button[value="save"]').click()
    assert saved.value.status == 201
    assert uploads == [('192.0.2.11', TEXT[:TEXT.rindex('backend web\n')] + 'backend web\n    server two 192.0.2.13:80 check\n', 'save', '/etc/haproxy/haproxy.cfg')]


def test_late_viewer_response_cannot_replace_new_selection(logged_in, product_url, remote_config):
    page = logged_in
    page.goto(product_url + '/config/haproxy/192.0.2.11/show')
    expect(page.locator('#config-viewer')).to_be_visible()
    outcome = page.evaluate('''() => {
        const ajax = $.ajax;
        const requests = [];
        const current = document.querySelector('#ajax').innerHTML;
        $.ajax = options => { requests.push(options); return {abort() {}}; };
        try {
            ConfigViewer.load({service: 'haproxy', serv: '192.0.2.11'}, '/config/haproxy/192.0.2.11/show');
            ConfigViewer.load({service: 'haproxy', serv: '192.0.2.12'}, '/config/haproxy/192.0.2.12/show');
            requests[1].success({data: current});
            requests[0].success({data: '<div id="stale">stale response</div>'});
            requests[0].error({responseJSON: {error: 'stale failure'}}, 'error');
            return {stale: !!document.getElementById('stale'), viewer: !!document.getElementById('config-viewer'), path: location.pathname};
        } finally { $.ajax = ajax; ConfigViewer.cancel(); }
    }''')
    assert outcome == {'stale': False, 'viewer': True, 'path': '/config/haproxy/192.0.2.12/show'}


@pytest.mark.parametrize('locale,copy_label', [
    ('en', 'Copy file'), ('ru', 'Копировать файл'), ('es-ES', 'Copiar archivo'),
    ('fr', 'Copier le fichier'), ('pt-br', 'Copiar arquivo'), ('zh', '复制文件'),
])
def test_localized_controls_fit_and_copy_original_text(logged_in, product_url, remote_config, locale, copy_label):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + '/config/haproxy/192.0.2.11/show')
    viewer = page.locator('#config-viewer')
    expect(viewer.locator('.cv-copy')).to_have_text(copy_label)
    page.set_viewport_size({'width': 600, 'height': 1000})
    assert viewer.evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')
    page.evaluate('navigator.clipboard.writeText = async (text) => { window.copiedConfig = text; }')
    viewer.locator('.cv-copy').click()
    assert page.evaluate('window.copiedConfig') == TEXT


def test_saved_version_has_its_own_path_and_no_live_section_actions(logged_in, product_url, product):
    path = Path(config_common.generate_config_path('haproxy', product.server.ip))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEXT, encoding='utf-8', newline='')
    ConfigVersion.create(server_id=product.server.server_id, user_id=product.admin.user_id,
                         service='haproxy', local_path=str(path.resolve()), remote_path='/etc/haproxy/old.cfg',
                         diff='', date='2026-10-03 16:42:00')
    page = logged_in
    try:
        page.goto(product_url + '/config/versions/haproxy/192.0.2.11/' + path.name)
        viewer = page.locator('#config-viewer')
        expect(viewer.locator('.cv-version-note')).to_contain_text(path.name)
        expect(viewer.locator('.cv-path')).to_have_text('/etc/haproxy/old.cfg')
        expect(viewer.locator('.cv-edit-section')).to_have_count(0)
        expect(viewer.locator('#edit_link')).to_have_count(0)
        viewer.locator('.cv-expand').click()
        expect(viewer.locator('a[href*="/stats/"]')).to_have_count(0)
        expect(page.locator('#save_version')).to_be_visible()
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.parametrize('service,text', [
    ('nginx', 'events {\n worker_connections 1024;\n}\nhttp {\n server {\n listen 80;\n }\n}\n'),
    ('apache', 'Listen 80\n<VirtualHost *:80>\n ServerName example.test\n</VirtualHost>\n'),
    ('keepalived', 'global_defs {\n router_id LB\n}\nvrrp_instance VI_1 {\n state MASTER\n}\n'),
])
def test_other_services_render_source_and_correct_file(logged_in, product_url, product, monkeypatch, service, text):
    setattr(product.server, service, 1)
    product.server.save()
    def download(server, path, **kwargs):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding='utf-8', newline='')
    monkeypatch.setattr(config_mod, 'get_config', download)
    remote = {'nginx': '/etc/nginx/nginx.conf', 'apache': '/etc/apache2/apache2.conf', 'keepalived': '/etc/keepalived/keepalived.conf'}[service]
    monkeypatch.setattr(config_mod.server_mod, 'get_remote_files', lambda *args: remote)
    page = logged_in
    page.goto(product_url + f'/config/{service}/192.0.2.11/show/' + remote.replace('/', '92'))
    viewer = page.locator('#config-viewer')
    expect(viewer.locator('.cv-path')).to_have_text(remote)
    viewer.locator('[data-cv-mode="raw"]').click()
    expect(viewer.locator('.cv-raw .cv-line')).to_have_count(len(text.splitlines()))
    assert viewer.locator('.cv-raw .cv-text').all_text_contents() == text.splitlines()
