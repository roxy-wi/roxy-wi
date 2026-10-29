"""Container defaults belong to the target group in web and background paths."""
import pytest
from flask import g

from app import cache
from app.modules.db.db_model import Server, Setting
from app.modules.service import container_settings


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache', 'keepalived'])
def test_container_name_default_uses_target_group_without_a_request(app, service):
    server = Server.create(hostname='container-group-fixture', ip='192.0.2.198', group_id='8765')
    setting = Setting.create(param=service + '_container_name', section=service, value='team-two-' + service,
        desc='Container group fixture', group_id=8765)
    try:
        cache.clear()
        with app.test_request_context():
            g.user_params = dict(group_id=1)
            assert container_settings.name(server.server_id, service) == 'team-two-' + service
        assert container_settings.name(server.server_id, service) == 'team-two-' + service
    finally:
        setting.delete_instance()
        server.delete_instance()
        cache.clear()
