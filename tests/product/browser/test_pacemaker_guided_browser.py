import os
from urllib.parse import urlparse,parse_qs
from pathlib import Path
import pytest
from playwright.sync_api import expect
from app.modules.db.db_model import PacemakerChange,InstallationTasks
from app.modules.pacemaker import service
from app.modules.pacemaker.xml import configuration
from tests.product.test_pacemaker_guided import guided_cluster

pytestmark=[pytest.mark.browser,pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER')!='1',reason='Requires Chromium')]


def pick(page,label,value):
    control=page.locator('#pcmk-guided-form').get_by_label(label,exact=True).first
    control_id=control.get_attribute('id')
    page.locator('#'+control_id+'-button').click()
    page.get_by_role('option',name=value,exact=True).click()


@pytest.mark.parametrize('kind',['Fencing topology','Location and time rules','Groups and clones','Resource operations','Container bundle','Resource meta-attributes'])
def test_guided_forms_create_real_drafts_and_require_native_review(logged_in,product_url,product,guided_cluster,kind):
    page=logged_in;page.goto(product_url+'/pacemaker/wizard?cluster='+str(guided_cluster.cluster.id))
    expect(page.locator('#pcmk-cluster-button')).to_contain_text('guided-test')
    page.get_by_role('button',name='Read current configuration',exact=True).click()
    expect(page.locator('#pcmk-guided-form')).to_be_visible()
    pick(page,'Configuration task',kind)
    if kind=='Fencing topology':
        page.get_by_role('button',name='Add fencing level',exact=True).click();pick(page,'Device 1','fence-a · primitive')
    elif kind=='Location and time rules':
        page.locator('#pcmk-guided-form').get_by_label('Constraint ID',exact=True).fill('prefer-web');pick(page,'Resource','proxy · primitive');page.locator('#pcmk-guided-form').get_by_label('Comparison value',exact=True).fill('one')
    elif kind=='Groups and clones':
        page.locator('#pcmk-guided-form').get_by_label('Group / clone ID',exact=True).fill('web');pick(page,'Member 1','vip · primitive');page.get_by_role('button',name='Add member',exact=True).click();pick(page,'Member 2','proxy · primitive')
    elif kind=='Resource operations':pick(page,'Primitive','proxy · primitive')
    elif kind=='Container bundle':
        page.locator('#pcmk-guided-form').get_by_label('Bundle ID',exact=True).fill('web-bundle');page.locator('#pcmk-guided-form').get_by_label('Image',exact=True).fill('example.test/web:1')
    else:pick(page,'Resource / wrapper','proxy · primitive');page.locator('#pcmk-guided-form').get_by_label('resource-stickiness',exact=True).fill('100')
    with page.expect_response('**/guided') as created:page.get_by_role('button',name='Create reviewed draft',exact=True).click()
    assert created.value.status==201,created.value.text()
    page.wait_for_url('**/pacemaker/configuration?**');ident=int(parse_qs(urlparse(page.url).query)['change'][0])
    expect(page.locator('#pcmk-validate')).to_be_enabled();expect(page.locator('#pcmk-apply')).to_be_disabled()
    assert PacemakerChange.get_by_id(ident).status=='draft'
    assert not InstallationTasks.select().exists() and not guided_cluster.calls


def test_bundle_controls_and_existing_collection_layout_use_shared_components(logged_in,product_url,product,guided_cluster):
    page=logged_in;page.goto(product_url+'/pacemaker/wizard')
    expect(page.locator('#pcmk-cluster-button')).to_contain_text('guided-test');page.get_by_role('button',name='Read current configuration',exact=True).click();expect(page.locator('#pcmk-guided-form')).to_be_visible()
    pick(page,'Configuration task','Container bundle')
    page.get_by_role('button',name='Add port mapping',exact=True).click();page.get_by_role('button',name='Add storage mapping',exact=True).click()
    page.locator('#pcmk-guided-form').get_by_label('Host port',exact=True).fill('443');page.locator('#pcmk-guided-form').get_by_label('Container port',exact=True).fill('8443')
    page.locator('#pcmk-guided-form').get_by_label('Host source path',exact=True).fill('/srv/web');page.locator('#pcmk-guided-form').get_by_label('Container target path',exact=True).fill('/app')
    page.locator('#pcmk-guided-form').get_by_label('Bundle ID',exact=True).fill('web-bundle');page.locator('#pcmk-guided-form').get_by_label('Image',exact=True).fill('example.test/web:1')
    if os.environ.get('ROXYWI_CAPTURE_GUIDED_DOCS')=='1':
        page.wait_for_load_state('networkidle')
        folder=Path(__file__).resolve().parents[3]/'docs/screenshots/pacemaker-guided';folder.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(folder/'bundle.png'),full_page=True)
    page.set_viewport_size(dict(width=390,height=844));page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    assert page.locator('main').evaluate('(node)=>node.scrollWidth<=node.clientWidth+1')
    pick(page,'Configuration task','Groups and clones')
    page.locator('#pcmk-guided-form').get_by_label('Group / clone ID',exact=True).fill('clone-proxy');pick(page,'Collection kind','promotable')
    assert page.locator('#pcmk-guided-form').get_by_label('Group / clone ID',exact=True).input_value()=='clone-proxy'
    page.locator('#pcmk-guided-form').get_by_label('Group / clone ID',exact=True).fill('changed-clone-id')


def test_existing_operation_edits_keep_the_same_identity(logged_in,product_url,product,guided_cluster):
    page=logged_in;page.goto(product_url+'/pacemaker/wizard')
    expect(page.locator('#pcmk-cluster-button')).to_contain_text('guided-test')
    page.get_by_role('button',name='Read current configuration',exact=True).click();expect(page.locator('#pcmk-guided-form')).to_be_visible()
    pick(page,'Configuration task','Resource operations');pick(page,'Existing configuration','vip · start')
    expect(page.locator('#pcmk-guided-form').get_by_label('Operation ID (existing)',exact=True)).to_have_value('vip-start')
    page.locator('#pcmk-guided-form').get_by_label('Timeout',exact=True).fill('120s')
    page.get_by_role('button',name='Create reviewed draft',exact=True).click();page.wait_for_url('**/pacemaker/configuration?**')
    ident=int(parse_qs(urlparse(page.url).query)['change'][0])
    item=configuration(service.decrypt(PacemakerChange.get_by_id(ident).candidate)).find('./resources/primitive[@id="vip"]/operations/op')
    assert item.get('id')=='vip-start' and item.get('timeout')=='120s'


@pytest.mark.parametrize('kind', ['Fencing topology', 'Location and time rules', 'Groups and clones',
    'Resource operations', 'Container bundle', 'Resource meta-attributes'])
@pytest.mark.parametrize('width,theme', [(1440, 'light'), (390, 'dark')])
def test_guided_tasks_share_panel_layout_in_both_themes(logged_in, product_url, guided_cluster, kind, width, theme, tmp_path):
    page = logged_in
    page.set_viewport_size(dict(width=width, height=1000))
    page.add_init_script(f"localStorage.setItem('theme','{theme}')")
    page.goto(product_url + '/pacemaker/wizard')
    expect(page.locator('#pcmk-cluster-button')).to_contain_text('guided-test')
    page.get_by_role('button', name='Read current configuration', exact=True).click()
    expect(page.locator('#pcmk-guided-form')).to_be_visible()
    pick(page, 'Configuration task', kind)
    if kind == 'Fencing topology':
        page.get_by_role('button', name='Add fencing level', exact=True).click()
    elif kind == 'Container bundle':
        page.get_by_role('button', name='Add port mapping', exact=True).click()
        page.get_by_role('button', name='Add storage mapping', exact=True).click()
    elif kind == 'Resource meta-attributes':
        pick(page, 'Resource / wrapper', 'proxy · primitive')
    form = page.locator('#pcmk-guided-form')
    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
    for control in form.locator('input:visible, .ui-selectmenu-button:visible').all():
        bounds = control.bounding_box()
        parent = control.locator('..').bounding_box()
        assert bounds['width'] <= parent['width'] + 1
        assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1
    for panel in form.locator('[data-guided-panel]').all():
        expect(panel.locator(':scope > h4')).to_be_visible()
        assert not panel.evaluate("node => node.classList.contains('change-advanced-grid')")
    text_inputs = form.locator('input:visible')
    if text_inputs.count():
        assert text_inputs.first.evaluate('node => getComputedStyle(node).color') == form.evaluate('node => getComputedStyle(node).color')
    if kind == 'Container bundle':
        image = tmp_path / f'bundle-{theme}.png'
        page.locator('h2').click()
        page.screenshot(path=str(image), full_page=True, animations='disabled')
        if os.environ.get('ROXYWI_CAPTURE_GUIDED_DOCS') == '1':
            folder = Path(__file__).resolve().parents[3] / 'docs/screenshots/pacemaker-guided'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / ('bundle.png' if theme == 'light' else 'bundle-mobile-dark.png')).write_bytes(image.read_bytes())


@pytest.mark.parametrize('width', [1440, 390])
def test_guided_refresh_keeps_form_and_blocks_duplicates(logged_in, product_url, product_client, guided_cluster, width):
    page = logged_in
    page.set_viewport_size(dict(width=width, height=1000))
    page.goto(product_url + '/pacemaker/wizard')
    expect(page.locator('#pcmk-cluster-button')).to_contain_text('guided-test')
    load = page.get_by_role('button', name='Read current configuration', exact=True)
    load.click()
    form = page.locator('#pcmk-guided-form')
    expect(form).to_be_visible()
    pick(page, 'Configuration task', 'Container bundle')
    page.get_by_label('Bundle ID', exact=True).fill('unsaved-bundle')
    endpoint = product_url + '/pacemaker/api/' + str(guided_cluster.cluster.id) + '/guided'
    catalog = product_client.get('/pacemaker/api/' + str(guided_cluster.cluster.id) + '/guided').json
    before = form.bounding_box()
    held = []
    page.route(endpoint, lambda route: held.append(route))
    try:
        load.click()
        expect(form).to_have_attribute('aria-busy', 'true')
        expect(form).to_be_visible()
        expect(load).to_be_disabled()
        assert form.bounding_box() == before
        expect(page.get_by_label('Bundle ID', exact=True)).to_have_value('unsaved-bundle')
        expect(page.locator('#pcmk-guided-kind-button')).to_have_attribute('aria-disabled', 'true')
        load.dispatch_event('click')
        assert len(held) == 1
    finally:
        for route in held:
            route.fulfill(status=503, json={'error':'Synthetic cluster read failed'})
        page.unroute(endpoint)
    expect(page.locator('#pcmk-guided-status')).to_have_text('Synthetic cluster read failed')
    expect(form).to_have_attribute('aria-busy', 'false')
    expect(page.get_by_label('Bundle ID', exact=True)).to_have_value('unsaved-bundle')
    expect(load).to_be_enabled()
    page.route(endpoint, lambda route: route.fulfill(status=200, json=catalog))
    load.click()
    expect(page.locator('#pcmk-guided-status')).to_contain_text('Configuration loaded')
    expect(form).to_be_visible()
    expect(page.locator('#pcmk-guided-kind-button')).to_have_attribute('aria-disabled', 'false')
    assert not InstallationTasks.select().exists()


def test_guided_late_read_cannot_restore_a_reset_form(logged_in, product_url, product_client, guided_cluster):
    page = logged_in
    page.goto(product_url + '/pacemaker/wizard')
    expect(page.locator('#pcmk-cluster-button')).to_contain_text('guided-test')
    load = page.get_by_role('button', name='Read current configuration', exact=True)
    endpoint = product_url + '/pacemaker/api/' + str(guided_cluster.cluster.id) + '/guided'
    catalog = product_client.get('/pacemaker/api/' + str(guided_cluster.cluster.id) + '/guided').json
    held = []
    page.route(endpoint, lambda route: held.append(route))
    try:
        load.click()
        expect(page.locator('#pcmk-guided-form')).to_have_attribute('aria-busy', 'true')
        page.locator('#pcmk-cluster').dispatch_event('change')
        expect(page.locator('#pcmk-guided-status')).to_have_text('Read the cluster before creating a draft.')
        expect(load).to_be_enabled()
    finally:
        for route in held:
            route.fulfill(status=200, json=catalog)
        page.unroute(endpoint)
    expect(page.locator('#pcmk-guided-form')).to_be_hidden()
    expect(page.locator('#pcmk-guided-status')).to_have_text('Read the cluster before creating a draft.')
    load.click()
    expect(page.locator('#pcmk-guided-form')).to_be_visible()
    assert not InstallationTasks.select().exists()
