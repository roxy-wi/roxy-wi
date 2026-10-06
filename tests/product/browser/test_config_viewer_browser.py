"""Viewer interactions with real routes/templates; only remote SSH is replaced."""
import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from app.modules.config import config as config_mod, common as config_common, haproxy_files
from app.modules.db.db_model import ServiceSetting, ConfigVersion, Setting
from app.modules.db import add as add_sql
from app.modules.roxywi.class_models import HaproxyGlobalRequest, NginxUpstreamRequest
from app.modules.config.path_tokens import encode_file_path


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]

TEXT = ('# Example configuration\n\nglobal\n    daemon\n\n'
        'frontend public\n    bind :80\n    default_backend web\n\n'
        'backend web\n    server one 192.0.2.12:80 check\n'
        '    # <script>window.viewerInjection = true</script>\n')


@pytest.fixture
def remote_config(monkeypatch, product):
    ServiceSetting.create(server_id=11, service='haproxy', setting='multiple_config_files', value='1')
    monkeypatch.setattr(haproxy_files, 'discover_sources', lambda *a, **kw: {
        'state': 'ready', 'code': 'ready', 'sources': [{'path': '/etc/haproxy/conf.d', 'runtime_path': '/etc/haproxy/conf.d', 'kind': 'directory'}],
        'files': ['/etc/haproxy/haproxy.cfg', '/etc/haproxy/conf.d/site92.cfg'], 'mode': 'systemd', 'verified_running': True})
    def download(server, path, **kwargs):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(TEXT, encoding='utf-8', newline='')
    monkeypatch.setattr(config_mod, 'get_config', download)
    monkeypatch.setattr(config_mod, 'list_config_files', lambda server, service: ['/etc/haproxy/haproxy.cfg', '/etc/haproxy/conf.d/site92.cfg'])


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_single_file_mode_opens_main_without_a_picker(logged_in, product_url, product, monkeypatch, locale):
    main = '/etc/haproxy/haproxy.cfg'
    token = encode_file_path(main)
    downloads = []

    def download(server, local, **kwargs):
        downloads.append((server, kwargs.get('config_file_name')))
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_text(TEXT, encoding='utf-8')

    monkeypatch.setattr(config_mod, 'get_config', download)
    monkeypatch.setattr(haproxy_files, 'discover_sources', lambda *a, **kw: pytest.fail('Single-file mode must not inspect startup'))
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + '/config/haproxy/192.0.2.11/show-files')
    expect(page.locator('.cv-path')).to_have_text(main)
    expect(page).to_have_url(product_url + '/config/haproxy/192.0.2.11/show/' + token)
    expect(page.locator('#ajax-config_file_name')).to_have_text('')
    expect(page.locator('#ajax-config_file_name select')).to_have_count(0)
    expect(page.locator('.haproxy-sources-panel')).to_have_count(0)
    assert downloads == [('192.0.2.11', main)]

    page.locator('#edit_link').click()
    expect(page.locator('#saveconfig input[name="file_path"]')).to_have_value(main)
    expect(page.locator('#editor_config_file_name')).to_have_value(token)
    expect(page.locator('.config-editor-file-picker')).to_have_count(0)

    # The Open button follows the same direct flow when choosing a server.
    page.goto(product_url + '/config/haproxy/')
    page.evaluate('''() => {
        $('#serv').val('192.0.2.11').selectmenu('refresh');
    }''')
    page.locator('a[onclick="showConfigFiles()"]').click()
    expect(page.locator('.cv-path')).to_have_text(main)
    expect(page.locator('#ajax-config_file_name')).to_have_text('')


def test_extra_file_picker_and_form_keep_the_selected_file(logged_in, product_url, product, remote_config):
    extra = '/etc/haproxy/conf.d/site92.cfg'
    add_sql.insert_or_update_new_section(11, 'global', 'global', HaproxyGlobalRequest(daemon=True))
    add_sql.insert_or_update_new_section(11, 'global', 'global', HaproxyGlobalRequest(daemon=False), config_path=extra)
    page = logged_in
    page.goto(product_url + '/config/haproxy/192.0.2.11/show/' + encode_file_path(extra))
    expect(page.locator('.cv-path')).to_have_text(extra)
    expect(page.locator('#config_file_name')).to_have_value(encode_file_path(extra))
    page.locator('.cv-section').filter(has=page.locator('.cv-title', has_text='global')).locator('summary').click()
    page.locator('.cv-section[open] .cv-edit-section').click()
    expect(page.locator('#edit-section')).to_be_visible()
    expect(page.locator('#global-daemon')).not_to_be_checked()
    page.locator('.ui-dialog-titlebar-close:visible').click()
    page.locator('#config-add-section').click()
    expect(page).to_have_url(re.compile(r'/add/haproxy\?.*#listen'))
    for kind in ('listen', 'frontend', 'backend', 'userlist', 'peers'):
        expect(page.locator(f'#{kind}-config-target')).to_have_value(extra)


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_new_haproxy_file_keeps_extension_and_name(logged_in, product_url, remote_config, locale):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + '/config/haproxy/192.0.2.11/show')
    expect(page.locator('#config_file_name option')).to_have_count(3)
    page.evaluate("addNewConfig('192.0.2.11', 'haproxy')")
    page.locator('#new_config_name').fill('conf.d/fresh92.cfg')
    page.locator('.ui-dialog:visible .ui-dialog-buttonpane button').first.click()
    expect(page).to_have_url(re.compile('/edit/' + encode_file_path('/etc/haproxy/conf.d/fresh92.cfg') + '/new$'))
    expect(page.locator('#saveconfig input[name="file_path"]')).to_have_value('/etc/haproxy/conf.d/fresh92.cfg')


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
    add_sql.insert_or_update_new_section(product.server.server_id, 'global', 'global', HaproxyGlobalRequest(daemon=True))
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
    page.goto(product_url + f'/config/{service}/192.0.2.11/show/' + encode_file_path(remote))
    viewer = page.locator('#config-viewer')
    expect(viewer.locator('.cv-path')).to_have_text(remote)
    viewer.locator('[data-cv-mode="raw"]').click()
    expect(viewer.locator('.cv-raw .cv-line')).to_have_count(len(text.splitlines()))
    assert viewer.locator('.cv-raw .cv-text').all_text_contents() == text.splitlines()


@pytest.mark.parametrize('service,root', [('haproxy', '/etc/haproxy'), ('nginx', '/etc/nginx'),
                                        ('apache', '/etc/apache2'), ('keepalived', '/etc/keepalived')])
def test_unicode_file_links_picker_editor_and_creation(logged_in, product_url, product, monkeypatch, service, root):
    setattr(product.server, service, 1)
    product.server.save()
    extension = '.cfg' if service == 'haproxy' else '.conf'
    remote = root + '/сайт 92' + extension
    token = encode_file_path(remote)
    Setting.update(value=remote).where(Setting.param == service + '_config_path', Setting.group_id == 1).execute()
    Setting.update(value=root).where(Setting.param == service + '_dir', Setting.group_id == 1).execute()
    def download(server, local, **kwargs):
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_text('# file with a Unicode name\n', encoding='utf-8')
    monkeypatch.setattr(config_mod, 'get_config', download)
    monkeypatch.setattr(config_mod.server_mod, 'get_remote_files', lambda *a: remote + '\x00')
    page = logged_in
    page.goto(product_url + f'/config/{service}/192.0.2.11/show/' + token)
    expect(page.locator('.cv-path')).to_have_text(remote)
    assert page.evaluate('(path) => encodeConfigPath(path)', remote) == token
    assert page.evaluate('(token) => decodeConfigPath(token)', token) == remote
    if service != 'keepalived':
        expect(page.locator('#config_file_name')).to_have_value(token)
    if service == 'nginx':
        expect(page.locator('#edit_link')).to_have_attribute('data-nginx-edit', 'сайт 92')
    page.locator('#edit_link').click()
    expect(page).to_have_url(product_url + f'/config/{service}/192.0.2.11/edit/' + token)
    expect(page.locator('#saveconfig input[name="file_path"]')).to_have_value(remote)
    expect(page.locator('#editor_config_file_name')).to_have_value(token)

    if service in ('nginx', 'apache'):
        page.goto(product_url + f'/config/{service}/192.0.2.11/show-files')
        page.wait_for_function('typeof addNewConfig === "function"')
        page.evaluate('(service) => addNewConfig("192.0.2.11", service)', service)
        page.locator('#new_config_name').fill('conf.d/новый 92')
        page.locator('.ui-dialog:visible .ui-dialog-buttonpane button').first.click()
        created = root + '/conf.d/новый 92.conf'
        expect(page).to_have_url(product_url + f'/config/{service}/192.0.2.11/edit/' + encode_file_path(created) + '/new')
        expect(page.locator('#saveconfig input[name="file_path"]')).to_have_value(created)


def test_nginx_form_editor_keeps_92_in_section_name(logged_in, product_url, product, monkeypatch):
    remote = '/etc/nginx/conf.d/upstream_app92.conf'
    body = NginxUpstreamRequest(name='app92', balance='round_robin', backend_servers=[
        {'server': '192.0.2.12', 'port': 80, 'max_fails': 3, 'fail_timeout': 10}])
    add_sql.insert_new_section(11, 'upstream', 'app92', body, service='nginx')
    def download(server, local, **kwargs):
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_text('upstream app92 {\n server 192.0.2.12:80;\n}\n', encoding='utf-8')
    monkeypatch.setattr(config_mod, 'get_config', download)
    monkeypatch.setattr(config_mod.server_mod, 'get_remote_files', lambda *a: remote + '\x00')
    page = logged_in
    page.goto(product_url + '/config/nginx/192.0.2.11/show/' + encode_file_path(remote))
    expect(page.locator('#edit_link')).to_have_attribute('data-nginx-edit', 'upstream_app92')
    with page.expect_response(lambda response: '/section/upstream/app92' in response.url) as response:
        page.locator('#edit_link').click()
    assert response.value.status == 200
    expect(page.locator('#add-upstream input[name="name"]')).to_have_value('app92')
