from types import SimpleNamespace

from flask import g, render_template


def _setting(param, section, description, value='value'):
    return SimpleNamespace(
        param=param,
        section=section,
        desc=description,
        value=value,
    )


def _render_settings(app, settings):
    with app.test_request_context('/admin/settings'):
        g.user_params = {'role': 1}
        return render_template(
            'include/admin_settings.html',
            settings=settings,
            timezones=[],
            lang='en',
        )


def test_change_center_policy_settings_are_not_duplicated_in_generic_settings(app):
    rendered = _render_settings(app, [
        _setting(
            'haproxy_deployment_mode',
            'change_center',
            'Configuration deployment mode for HAProxy',
            'both',
        ),
    ])

    assert 'haproxy_deployment_mode' not in rendered
    assert 'Configuration deployment mode for HAProxy' not in rendered


def test_unknown_setting_uses_database_description_instead_of_failing(app):
    rendered = _render_settings(app, [
        _setting('future_option', 'future_section', 'Future option description'),
    ])

    assert 'Future Section' in rendered
    assert 'future_option' in rendered
    assert 'Future option description' in rendered
