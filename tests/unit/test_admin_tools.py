from pathlib import Path

import pytest
from flask import render_template

from app.modules.tools import common as tools_common
from app.routes.admin import routes as admin_routes


def test_tools_route_leaves_failures_to_the_global_error_handler(app, monkeypatch):
    monkeypatch.setattr(admin_routes.roxywi_auth, 'page_for_admin', lambda: None)
    monkeypatch.setattr(
        admin_routes.roxywi_common,
        'get_user_lang_for_flask',
        lambda: 'en',
    )
    monkeypatch.setattr(
        admin_routes.tools_common,
        'get_services_status',
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('tools failed')),
    )
    monkeypatch.setattr(admin_routes.service_event_sql, 'worker_summary', lambda: {})

    with app.test_request_context('/admin/tools'):
        with pytest.raises(RuntimeError, match='tools failed'):
            admin_routes.show_tools()


def test_tools_route_passes_worker_heartbeats_to_status_loader(app, monkeypatch):
    worker_states = {'checker': {'active': 1}}
    captured = {}

    monkeypatch.setattr(admin_routes.roxywi_auth, 'page_for_admin', lambda: None)
    monkeypatch.setattr(admin_routes.roxywi_common, 'get_user_lang_for_flask', lambda: 'en')
    monkeypatch.setattr(admin_routes.service_event_sql, 'worker_summary', lambda: worker_states)

    def fake_get_services_status(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(admin_routes.tools_common, 'get_services_status', fake_get_services_status)
    monkeypatch.setattr(admin_routes, 'render_template', lambda *_args, **_kwargs: 'rendered')

    with app.test_request_context('/admin/tools'):
        assert admin_routes.show_tools() == 'rendered'

    assert captured == {'update_cur_ver': 1, 'worker_states': worker_states}


def test_distributed_service_status_and_runtime_version_override_local_state(monkeypatch):
    monkeypatch.setattr(
        tools_common.roxy_sql,
        'get_all_tools',
        lambda: {
            'roxy-wi-checker': {
                'current_version': '4.9',
                'new_version': '5.0.0',
                'desc': '',
            },
            'roxy-wi-metrics': {
                'current_version': '3.8',
                'new_version': '4.0.0',
                'desc': '',
            },
            'roxy-wi-socket': {
                'current_version': '1.6',
                'new_version': '2.0.0',
                'desc': '',
            },
            'roxy-wi-portscanner': {
                'current_version': '1.8',
                'new_version': '2.0.0',
                'desc': '',
            },
        },
    )
    monkeypatch.setattr(tools_common, 'is_tool_active', lambda tool: 'failed')

    services = tools_common.get_services_status(worker_states={
        'checker': {
            'active': 1,
            'degraded': 1,
            'stale': 0,
            'draining': 0,
            'stopped': 0,
            'assignments': 14,
            'versions': ['5.0.0'],
        },
        'metrics': {
            'active': 2,
            'degraded': 0,
            'stale': 0,
            'draining': 0,
            'stopped': 0,
            'assignments': 8,
            'versions': ['4.0.0'],
        },
        'socket': {
            'active': 2,
            'degraded': 0,
            'stale': 0,
            'draining': 0,
            'stopped': 0,
            'assignments': 4,
            'versions': ['2.0.0'],
        },
        'portscanner': {
            'active': 1,
            'degraded': 0,
            'stale': 0,
            'draining': 0,
            'stopped': 0,
            'assignments': 6,
            'versions': ['2.0.0'],
        },
    })

    checker, metrics, socket, portscanner = services
    assert checker[1] == 'degraded'
    assert checker[2]['current_version'] == '5.0.0'
    assert checker[3]['assignments'] == 14
    assert metrics[1] == 'active'
    assert metrics[2]['current_version'] == '4.0.0'
    assert metrics[3]['assignments'] == 8
    assert socket[1] == 'active'
    assert socket[2]['current_version'] == '2.0.0'
    assert socket[3]['assignments'] == 4
    assert portscanner[1] == 'active'
    assert portscanner[2]['current_version'] == '2.0.0'
    assert portscanner[3]['assignments'] == 6


def test_tools_template_renders_worker_health_and_version_before_actions(app):
    service = [
        'roxy-wi-checker',
        'degraded',
        {'current_version': '5.0.0', 'new_version': '5.0.0'},
        {
            'active': 1,
            'degraded': 1,
            'stale': 0,
            'draining': 0,
            'stopped': 0,
            'assignments': 14,
        },
        {
            'category': 'distributed',
            'management': 'Worker deployment',
            'can_lifecycle': False,
            'instances': 1,
            'stale': 0,
        },
    ]

    with app.test_request_context('/admin/tools'):
        html = render_template('ajax/load_services.html', services=[service], lang='en')

    assert 'serverWarn server-status' in html
    assert 'workers: active 1; degraded 1' in html
    assert 'Distributed services' in html
    assert 'Worker deployment' in html
    assert html.index('admin-version-cell') < html.index('admin-actions-cell')

    admin_template = Path('app/templates/admin.html').read_text(encoding='utf-8')
    tools_header = admin_template.split('<div id="tools">', 1)[1].split('</thead>', 1)[0]
    assert tools_header.index('admin-version-cell') < tools_header.index('admin-actions-cell')


def test_tools_template_labels_socket_activity_as_connections(app):
    service = [
        'roxy-wi-socket',
        'active',
        {'current_version': '2.0.0', 'new_version': '2.0.0'},
        {'active': 2, 'assignments': 4},
        {
            'category': 'distributed',
            'management': 'Worker deployment',
            'can_lifecycle': False,
            'instances': 2,
            'stale': 0,
        },
    ]

    with app.test_request_context('/admin/tools'):
        html = render_template('ajax/load_services.html', services=[service], lang='en')

    assert 'workers: 2; connections: 4' in html


def test_internal_process_uses_shared_heartbeat_and_application_version(monkeypatch):
    monkeypatch.setattr(
        tools_common.roxy_sql,
        'get_all_tools',
        lambda: {
            'roxy-wi-scheduler': {
                'current_version': 'old',
                'new_version': 'old',
                'desc': '',
            },
        },
    )
    monkeypatch.setattr(tools_common.roxywi_mod, 'deployment_mode', lambda: 'kubernetes')
    monkeypatch.setattr(tools_common, 'is_tool_active', lambda _tool: 'unknown')

    services = tools_common.get_services_status(worker_states={
        'roxy-wi-scheduler': {
            'active': 2,
            'degraded': 0,
            'stale': 1,
            'draining': 0,
            'stopped': 0,
            'assignments': 0,
            'versions': ['9.0.0'],
        },
    })

    scheduler = services[0]
    assert scheduler[1] == 'active'
    assert scheduler[2]['current_version'] == '9.0.0'
    assert scheduler[4] == {
        'category': 'internal',
        'management': 'Kubernetes',
        'can_lifecycle': False,
        'instances': 2,
        'stale': 0,
        'last_heartbeat': None,
        'heartbeat_age_seconds': None,
        'deployment_mode': 'kubernetes',
    }


def test_package_internal_process_exposes_systemd_actions_but_web_does_not(monkeypatch):
    monkeypatch.setattr(tools_common.roxywi_mod, 'deployment_mode', lambda: 'package')

    scheduler = tools_common._management_metadata('roxy-wi-scheduler', 'active', {'active': 1})
    web = tools_common._management_metadata('roxy-wi-web', 'active', {'active': 1})

    assert scheduler['management'] == 'systemd'
    assert scheduler['can_lifecycle'] is True
    assert scheduler['last_heartbeat'] is None
    assert web['management'] == 'systemd'
    assert web['can_lifecycle'] is False
