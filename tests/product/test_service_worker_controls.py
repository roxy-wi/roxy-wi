from datetime import timedelta
from html.parser import HTMLParser

import pytest

from app.modules.common.time import utc_now
from app.modules.db.db_model import Server, UserGroups, WorkerState
from app.modules.roxywi import common


class Inputs(HTMLParser):
    def __init__(self, response):
        super().__init__()
        assert response.status_code == 200, response.text
        self.fields = {}
        self.feed(response.text)

    def handle_starttag(self, tag, attrs):
        if tag == 'input':
            values = dict(attrs)
            self.fields[values.get('id')] = values


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
@pytest.mark.parametrize('selected', [False, True])
def test_remote_workers_enable_controls_without_local_packages(product_client, product, service_worker_controls, service, selected):
    setattr(product.server, service, 1)
    product.server.save()
    if not selected:
        # Keep the route on the server list instead of its single-server shortcut.
        Server.create(server_id=33, hostname='Second server', ip='192.0.2.33', group_id='1', cred_id=11, **{service: 1})
    url = f'/service/{service}' + (f'/{product.server.ip}' if selected else '')
    controls = Inputs(product_client.get(url)).fields
    assert 'disabled' not in controls['alert-11']
    assert 'disabled' not in controls['metrics-11']
    assert 'disabled' in controls['active-11']
    assert len(service_worker_controls.commands) == 2  # keep_alive process and package only.


@pytest.mark.parametrize('status,enabled', [('starting', True), ('running', True), ('degraded', True),
                                          ('stale', False), ('stopped', False), ('draining', False), ('absent', False)])
def test_controls_follow_heartbeat_liveness_independently(product_client, product, service_worker_controls, status, enabled):
    if status == 'absent':
        WorkerState.delete().where(WorkerState.service == 'checker').execute()
    else:
        WorkerState.update(status='running' if status == 'stale' else status,
                           expires_at=utc_now() + timedelta(minutes=-1 if status == 'stale' else 5)).where(
            WorkerState.service == 'checker').execute()
    # An installed package must not turn an unavailable worker into a live one.
    service_worker_controls.local_installed = True
    controls = Inputs(product_client.get('/service/nginx')).fields
    assert ('disabled' not in controls['alert-11']) is enabled
    assert 'disabled' not in controls['metrics-11']
    assert 'disabled' not in controls['active-11']


def test_expired_old_replica_does_not_block_live_worker(product_client, product, service_worker_controls):
    WorkerState.create(worker_id='old-checker', service='checker', status='running', group_ids=[1],
                       last_heartbeat=utc_now() - timedelta(hours=1), expires_at=utc_now() - timedelta(minutes=1))
    assert 'disabled' not in Inputs(product_client.get('/service/nginx')).fields['alert-11']


def test_worker_from_other_group_does_not_enable_controls(product_client, product, service_worker_controls):
    product.admin.group_id = 2
    product.admin.save()
    UserGroups.create(user_id=product.admin.user_id, user_group_id=2, user_role_id=2)
    product.other.nginx = 1
    product.other.save()
    response = product_client.post('/login', json={'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/service/nginx'})
    assert response.status_code == 200
    controls = Inputs(product_client.get('/service/nginx')).fields
    assert 'disabled' in controls['alert-22'] and 'disabled' in controls['metrics-22']
    WorkerState.update(group_ids=[2]).execute()
    controls = Inputs(product_client.get('/service/nginx')).fields
    assert 'disabled' not in controls['alert-22'] and 'disabled' not in controls['metrics-22']


def test_inactive_subscription_keeps_controls_disabled(product_client, product, service_worker_controls, monkeypatch):
    monkeypatch.setattr(common, 'return_user_subscription', lambda: {'user_status': 0, 'user_plan': 'support'})
    controls = Inputs(product_client.get('/service/nginx')).fields
    assert all('disabled' in controls[name + '-11'] for name in ('alert', 'metrics', 'active'))


def test_disabled_controls_preserve_saved_settings(product_client, product, service_worker_controls):
    Server.update(nginx_alert=1, nginx_metrics=1).where(Server.server_id == 11).execute()
    WorkerState.delete().execute()
    controls = Inputs(product_client.get('/service/nginx')).fields
    assert all('checked' in controls[name + '-11'] and 'disabled' in controls[name + '-11'] for name in ('alert', 'metrics'))
    server = Server.get_by_id(11)
    assert server.nginx_alert == server.nginx_metrics == 1


@pytest.mark.parametrize('distro', ['ubuntu', 'rocky'])
def test_auto_start_still_checks_its_local_package(product_client, product, service_worker_controls, monkeypatch, distro):
    monkeypatch.setattr('app.routes.service.routes.distro.id', lambda: distro)
    service_worker_controls.local_installed = True
    assert 'disabled' not in Inputs(product_client.get('/service/nginx')).fields['active-11']
    assert service_worker_controls.commands[-1].startswith('apt ' if distro == 'ubuntu' else 'rpm ')


def test_read_only_role_has_no_worker_switches(product_client, product, service_worker_controls):
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    controls = Inputs(product_client.get('/service/nginx')).fields
    assert all(name + '-11' not in controls for name in ('alert', 'metrics', 'active'))
