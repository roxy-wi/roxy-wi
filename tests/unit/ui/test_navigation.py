from pathlib import Path
from types import SimpleNamespace

from flask import g, render_template, request
import pytest


LANGUAGES = ('en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh')
ROOT = Path(__file__).resolve().parents[3]


def render_navigation(app, role, services=('1', '2', '3', '4', '5', '6')):
    def fake_url_for(endpoint, **values):
        if endpoint == 'static':
            return f"/static/{values['filename']}"
        if endpoint == 'change.index':
            return '/changes'
        if endpoint == 'admin.admin':
            return '/admin'
        if endpoint == 'udp.udp_listener':
            return '/udp'
        if endpoint == 'service.services':
            return f"/service/{values['service']}"
        return '/' + endpoint.replace('.', '/')

    with app.test_request_context('/overview'):
        request.url_rule = SimpleNamespace(endpoint='overview.index')
        g.user_params = {
            'role': role,
            'user_services': services,
        }
        language = app.jinja_env.get_template('languages/en.html').module
        return render_template(
            'include/main_menu.html',
            lang=language,
            oidc_available=True,
            url_for=fake_url_for,
        )


def test_navigation_template_and_catalogs_compile(app):
    assert app.jinja_env.get_template('include/main_menu.html')

    with app.app_context():
        catalogs = [
            app.jinja_env.get_template(f'languages/{language}.html').module.menu_links['navigation']
            for language in LANGUAGES
        ]

    expected_keys = {
        'label',
        'search',
        'operations',
        'administration',
        'collapse',
        'expand',
        'submenu',
        'no_results',
    }
    for catalog in catalogs:
        assert set(catalog) == expected_keys
        assert all(catalog.values())


def test_navigation_groups_existing_destinations_without_changing_access_guards():
    menu = (ROOT / 'app/templates/include/main_menu.html').read_text(encoding='utf-8')

    assert 'id="app-navigation"' in menu
    assert 'id="app-navigation-search"' in menu
    assert menu.count('id="hide_menu"') == 1
    for group in ('operations', 'services', 'monitoring', 'administration'):
        assert f'data-nav-group="{group}"' in menu

    for endpoint in (
        "url_for('overview.index')",
        "url_for('change.index')",
        "url_for('ha.ha_cluster', service='cluster')",
        "url_for('service.services', service='haproxy')",
        "url_for('service.services', service='nginx')",
        "url_for('service.services', service='apache')",
        "url_for('service.services', service='keepalived')",
        "url_for('udp.udp_listener', service='udp')",
        "url_for('smon.smon_main_dashboard')",
        "url_for('install.install_monitoring')",
        "url_for('admin.admin')",
    ):
        assert endpoint in menu

    assert "g.user_params['role'] <= 3" in menu
    assert "g.user_params['role'] <= 2" in menu
    assert "g.user_params['role'] <= 1" in menu
    for service_id in ('1', '2', '3', '4', '5', '6'):
        assert f"'{service_id}' in g.user_params['user_services']" in menu
    assert '{% if oidc_available %}' in menu


def test_navigation_uses_one_explicit_icon_per_item():
    menu = (ROOT / 'app/templates/include/main_menu.html').read_text(encoding='utf-8')
    styles = (ROOT / 'app/static/css/styles.css').read_text(encoding='utf-8')

    assert 'fa-file-signature nav-icon' in menu
    assert 'fa-code-branch nav-icon' not in menu
    for legacy_class in (
        'class="nav-link keepalived',
        'nav-service-link apache-menu',
        'class="nav-link balance',
        'nav-service-link stats',
        'nav-service-link hap-menu',
        'nav-service-link admin',
    ):
        assert legacy_class not in menu
    assert '.menu .nav-link > .nav-icon.svg-inline--fa' in styles
    assert 'margin-right: 0' in styles.split('.menu .nav-link > .nav-icon.svg-inline--fa', 1)[1].split('}', 1)[0]


def test_navigation_renders_role_specific_items(app):
    administrator_menu = render_navigation(app, role=1)
    guest_menu = render_navigation(app, role=4)

    assert administrator_menu.count('id="app-navigation"') == 1
    assert administrator_menu.count('id="hide_menu"') == 1
    assert 'href="/changes"' in administrator_menu
    assert 'id="admin-area"' in administrator_menu
    assert 'id="admin-area-oidc"' in administrator_menu
    assert 'UDP listeners' in administrator_menu

    assert 'href="/changes"' not in guest_menu
    assert 'id="admin-area"' not in guest_menu
    assert 'id="admin-area-oidc"' not in guest_menu
    assert 'UDP listeners' not in guest_menu
    assert 'HAProxy' in guest_menu
    assert 'NGINX' in guest_menu


@pytest.mark.parametrize('services,visible', [
    ('1 2 3', True), (('1', '2'), True), (['1'], True),
    ('11 2', False), (('11', '2'), False), ('', False),
])
def test_managed_acl_navigation_uses_exact_service_permissions(app, services, visible):
    menu = render_navigation(app, role=1, services=services)
    assert ('Managed ACL feeds' in menu) is visible
    assert ('Managed ACL feeds' in render_navigation(app, role=4, services=services)) is visible


def test_navigation_javascript_handles_state_search_and_active_routes():
    script = (ROOT / 'app/static/js/script.js').read_text(encoding='utf-8')

    for function_name in (
        'activateNavigationLink',
        'markCurrentNavigationLink',
        'setNavigationCollapsed',
        'initializeAppNavigation',
    ):
        assert f'function {function_name}(' in script

    assert "sessionStorage.setItem('hide_menu'" in script
    assert "localStorage.setItem('roxywi-nav-group-'" in script
    assert "event.key === '/'" in script
    assert "event.key === 'Escape'" in script
    assert "currentPath.indexOf(targetPath + '/') === 0" in script
    assert 'let score = targetPath.length' in script
    assert "link.classList.contains('head-submenu')" in script
    assert "link.setAttribute('aria-current', 'page')" in script
    assert "$('.top-menu').hide" not in script
    assert 'margin-left", "207px"' not in script


def test_navigation_styles_cover_expanded_collapsed_dark_and_responsive_states():
    styles = (ROOT / 'app/static/css/styles.css').read_text(encoding='utf-8')
    dark_styles = (ROOT / 'app/static/css/dark.css').read_text(encoding='utf-8')

    for selector in (
        '.app-nav-search',
        '.menu a.menu-active',
        '.nav-group-toggle',
        '.nav-submenu-toggle',
        '.p_menu.is-open > .v_menu',
        'html.nav-collapsed .top-menu',
        'html.nav-collapsed .container',
        '@media (max-width: 900px)',
    ):
        assert selector in styles

    assert '.p_menu:hover .v_menu' not in styles
    assert 'top: -9999px' not in styles
    assert '.app-nav-search input' in dark_styles
    assert '.menu a.menu-active' in dark_styles


def test_navigation_collapse_control_is_not_duplicated_in_footer():
    base = (ROOT / 'app/templates/base.html').read_text(encoding='utf-8')

    assert 'id="hide_menu"' not in base
    assert 'id="show_menu"' not in base
