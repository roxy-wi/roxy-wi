from pathlib import Path


ADMIN_TEMPLATES = (
    'admin.html',
    'include/admin_users.html',
    'include/admin_servers.html',
    'include/admin_ssh.html',
    'include/admin_backup.html',
    'include/admin_oidc.html',
    'include/admin_action_menu.html',
    'ajax/new_ssh.html',
    'ajax/new_backup.html',
    'ajax/new_s3_backup.html',
    'ajax/new_git.html',
    'ajax/load_services.html',
    'ajax/load_updateroxywi.html',
)


def test_admin_action_menu_templates_compile(app):
    for template in ADMIN_TEMPLATES:
        assert app.jinja_env.get_template(template)


def test_admin_tables_use_one_labeled_actions_column():
    templates = (
        'app/templates/include/admin_users.html',
        'app/templates/include/admin_servers.html',
        'app/templates/include/admin_ssh.html',
        'app/templates/include/admin_backup.html',
        'app/templates/include/admin_oidc.html',
        'app/templates/admin.html',
    )

    for template in templates:
        source = Path(template).read_text(encoding='utf-8')
        assert 'admin-actions-cell' in source
        assert 'lang.words.actions' in source


def test_admin_row_actions_share_the_same_dropdown_component():
    menu_template = Path('app/templates/include/admin_action_menu.html').read_text(encoding='utf-8')
    stylesheet = Path('app/static/css/ui-components.css').read_text(encoding='utf-8')
    script = Path('app/static/js/admin/common.js').read_text(encoding='utf-8')

    assert 'admin-actions-toggle' in menu_template
    assert 'fa-ellipsis-v' in menu_template
    assert 'role="menu"' in menu_template
    assert '.admin-actions-menu .admin-action-item' in stylesheet
    assert "$(document).on('click', '.admin-actions-toggle'" in script
    assert "event.key === 'Escape'" in script


def test_ajax_generated_admin_rows_keep_action_labels_and_icons():
    group_script = Path('app/static/js/admin/group.js').read_text(encoding='utf-8')
    oidc_script = Path('app/static/js/admin/oidc.js').read_text(encoding='utf-8')

    for script in (group_script, oidc_script):
        assert 'admin-actions-toggle' in script
        assert 'admin-actions-menu' in script
        assert 'admin-action-item' in script
        assert 'fa-ellipsis-v' in script


def test_tools_loader_renders_successful_html_instead_of_scanning_css_class_names():
    script = Path('app/static/js/admin/common.js').read_text(encoding='utf-8')
    loader = script.split('function loadServices()', 1)[1].split(
        'function loadupdatehapwi()', 1
    )[0]

    assert "$('#ajax-services-body').html(data)" in loader
    assert "data.indexOf('danger')" not in loader
    assert 'toastr.error(data)' not in loader
