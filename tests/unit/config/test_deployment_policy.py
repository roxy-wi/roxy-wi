import importlib
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import g, render_template
from flask_jwt_extended import create_access_token

import app.modules.change.service as change_service
import app.modules.config.config as config_module
import app.modules.config.deployment_policy as deployment_policy
import app.modules.db.group as group_sql
from app.modules.change.schemas import ConfigChangeCreate
from app.modules.db.db_model import Groups, Server, Setting
from app.modules.roxywi.exception import RoxywiPermissionError, RoxywiValidationError
import app.modules.roxywi.auth as roxywi_auth
import app.routes.server.routes as server_routes


@pytest.fixture()
def policy_group():
    group = Groups.create(
        name=f'deployment-policy-{uuid.uuid4().hex}',
        description='Deployment policy tests',
    )
    yield group
    Server.delete().where(Server.group_id == str(group.group_id)).execute()
    Setting.delete().where(Setting.group_id == group.group_id).execute()
    Groups.delete_by_id(group.group_id)


@pytest.fixture()
def policy_server(policy_group):
    return Server.create(
        hostname=f'policy-server-{uuid.uuid4().hex}',
        ip=f'policy-{uuid.uuid4().hex}.example.test',
        group_id=str(policy_group.group_id),
        enabled=1,
        haproxy=1,
        nginx=1,
        apache=1,
        keepalived=1,
    )


def _all_modes(mode='both'):
    return {service: mode for service in deployment_policy.SERVICES}


def test_missing_policy_preserves_legacy_direct_and_change_center_access(policy_group):
    assert deployment_policy.get_group_policy(policy_group.group_id) == _all_modes()
    assert deployment_policy.direct_deployment_allowed(policy_group.group_id, 'haproxy')
    assert deployment_policy.change_center_creation_allowed(policy_group.group_id, 'haproxy')


def test_policy_is_persisted_independently_for_every_service(policy_group):
    expected = {
        'haproxy': 'change_center',
        'nginx': 'direct',
        'apache': 'both',
        'keepalived': 'change_center',
    }

    assert deployment_policy.update_group_policy(policy_group.group_id, expected) == expected
    assert deployment_policy.get_group_policy(policy_group.group_id) == expected


def test_invalid_policy_fails_closed(policy_group):
    Setting.create(
        param='haproxy_deployment_mode',
        value='unexpected',
        section='change_center',
        desc='invalid test value',
        group_id=policy_group.group_id,
    )

    with pytest.raises(RoxywiValidationError, match='Invalid deployment mode'):
        deployment_policy.direct_deployment_allowed(policy_group.group_id, 'haproxy')


def test_change_center_mode_blocks_direct_writes_but_not_validation(policy_group):
    deployment_policy.update_group_policy(
        policy_group.group_id,
        {**_all_modes(), 'haproxy': 'change_center'},
    )

    with pytest.raises(RoxywiPermissionError, match='Direct Haproxy'):
        deployment_policy.require_direct_deployment(
            policy_group.group_id, 'haproxy', action='reload'
        )
    deployment_policy.require_direct_deployment(
        policy_group.group_id, 'haproxy', action='test'
    )


def test_direct_mode_blocks_new_change_center_drafts(policy_group):
    deployment_policy.update_group_policy(
        policy_group.group_id,
        {**_all_modes(), 'nginx': 'direct'},
    )

    with pytest.raises(RoxywiPermissionError, match='Change Center creation'):
        deployment_policy.require_change_center_creation(
            policy_group.group_id, 'nginx'
        )


def test_common_upload_layer_enforces_policy_before_remote_write(
    policy_group, policy_server, monkeypatch
):
    deployment_policy.update_group_policy(
        policy_group.group_id,
        {**_all_modes(), 'haproxy': 'change_center'},
    )
    monkeypatch.setattr(
        config_module,
        'upload',
        lambda *_args, **_kwargs: pytest.fail('remote upload must not start'),
    )

    with pytest.raises(RoxywiPermissionError, match='create a change'):
        config_module.upload_and_restart(
            policy_server.ip, 'unused.cfg', 'reload', 'haproxy'
        )


def test_change_center_internal_upload_can_apply_when_direct_writes_are_disabled(
    policy_group, policy_server, tmp_path, monkeypatch
):
    deployment_policy.update_group_policy(
        policy_group.group_id,
        {**_all_modes(), 'haproxy': 'change_center'},
    )
    config_path = tmp_path / 'candidate.cfg'
    config_path.write_text('global\n', encoding='utf-8')
    uploads = []
    monkeypatch.setattr(
        config_module,
        'upload',
        lambda server_ip, remote_path, local_path: uploads.append(
            (server_ip, remote_path, local_path)
        ),
    )
    monkeypatch.setattr(config_module, '_generate_command', lambda *_args: 'apply')
    monkeypatch.setattr(
        config_module.server_mod, 'ssh_command', lambda *_args, **_kwargs: '{"status":"ok"}'
    )
    monkeypatch.setattr(
        config_module.roxywi_common, 'logging', lambda *_args, **_kwargs: None
    )

    result = config_module.upload_and_restart(
        policy_server.ip,
        str(config_path),
        'reload',
        'haproxy',
        record_version=False,
        normalize_config=False,
        deployment_policy_bypass=True,
    )

    assert result == 'Haproxy'
    assert len(uploads) == 1


def test_change_service_rejects_direct_only_policy_before_snapshot(
    policy_group, policy_server, monkeypatch
):
    deployment_policy.update_group_policy(
        policy_group.group_id,
        {**_all_modes(), 'haproxy': 'direct'},
    )
    monkeypatch.setattr(change_service, 'require_feature', lambda *_args: None)
    monkeypatch.setattr(
        change_service.change_automation,
        'validate_notification_destinations',
        lambda *_args: [],
    )
    monkeypatch.setattr(
        change_service,
        '_capture_rollout_targets',
        lambda *_args, **_kwargs: pytest.fail('SSH snapshot must not start'),
    )
    body = ConfigChangeCreate(
        server_id=policy_server.server_id,
        service='haproxy',
        config='global\n',
        title='Blocked draft',
    )

    with pytest.raises(RoxywiPermissionError, match='use direct'):
        change_service.create_change(
            body, user_id=1, group_id=policy_group.group_id
        )


def test_migration_adds_compatible_policy_to_existing_groups(policy_group):
    migration = importlib.import_module(
        'app.modules.db.migrations.20260830000000_add_group_deployment_policies'
    )

    migration.up()

    assert deployment_policy.get_group_policy(policy_group.group_id) == _all_modes()


def test_new_groups_receive_all_policy_settings():
    name = f'new-policy-group-{uuid.uuid4().hex}'
    group_id = group_sql.add_group(name, 'new group defaults')
    try:
        assert deployment_policy.get_group_policy(group_id) == _all_modes()
        params = {
            setting.param
            for setting in Setting.select().where(
                (Setting.group_id == group_id)
                & (Setting.section == deployment_policy.SETTING_SECTION)
            )
        }
        assert params == {
            deployment_policy.setting_name(service)
            for service in deployment_policy.SERVICES
        }
    finally:
        group_sql.delete_group(group_id)


@pytest.fixture()
def group_policy_api(app, monkeypatch):
    user_params = {
        'user_id': 1,
        'user': 'admin',
        'role': 1,
        'group_id': 1,
        'lang': 'en',
    }
    monkeypatch.setattr(
        server_routes.roxywi_common,
        'get_users_params',
        lambda **_kwargs: dict(user_params),
    )
    monkeypatch.setattr(
        server_routes.roxywi_common,
        'require_request_server_access',
        lambda: None,
    )
    monkeypatch.setattr(roxywi_auth, 'is_admin', lambda **_kwargs: True)
    monkeypatch.setattr(
        server_routes.roxywi_common, 'logging', lambda *_args, **_kwargs: None
    )
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})
    return {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}


def test_superadmin_can_read_and_update_group_policy(
    client, group_policy_api, policy_group
):
    expected = {
        'haproxy': 'change_center',
        'nginx': 'direct',
        'apache': 'both',
        'keepalived': 'both',
    }

    get_response = client.get(
        f'/server/group/{policy_group.group_id}/deployment-policy',
        headers=group_policy_api,
    )
    put_response = client.put(
        f'/server/group/{policy_group.group_id}/deployment-policy',
        headers=group_policy_api,
        json=expected,
    )

    assert get_response.status_code == 200
    assert get_response.get_json()['data'] == _all_modes()
    assert put_response.status_code == 200
    assert put_response.get_json()['data'] == expected


def test_non_superadmin_cannot_manage_group_policy(
    client, group_policy_api, policy_group, monkeypatch
):
    monkeypatch.setattr(
        roxywi_auth,
        'is_admin',
        lambda level=1, **_kwargs: int(level) >= 2,
    )

    response = client.get(
        f'/server/group/{policy_group.group_id}/deployment-policy',
        headers=group_policy_api,
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ('direct_allowed', 'change_allowed', 'has_direct', 'has_change'),
    ((False, True, False, True), (True, False, True, False), (True, True, True, True)),
)
def test_config_editor_renders_only_actions_allowed_by_policy(
    app, direct_allowed, change_allowed, has_direct, has_change
):
    with app.test_request_context('/config/haproxy/192.0.2.1/edit/'):
        g.user_params = {
            'role': 3,
            'servers': [(1, 'server', '192.0.2.1')],
        }
        html = render_template(
            'config.html',
            lang='en',
            service='haproxy',
            service_desc=SimpleNamespace(service='HAProxy'),
            serv='192.0.2.1',
            action='',
            config='global\n',
            cfg='/tmp/haproxy.cfg',
            config_file_name=None,
            remote_config_path='/etc/haproxy/haproxy.cfg',
            stderr='',
            error='',
            is_serv_protected=False,
            is_restart=0,
            user_subscription={'user_status': 1, 'user_plan': 'support'},
            direct_deployment_allowed=direct_allowed,
            change_center_creation_allowed=change_allowed,
        )

    assert ('value="reload" name="action"' in html) is has_direct
    assert ('id="open-change-dialog"' in html) is has_change
    assert 'value="test" name="action"' in html


def test_admin_template_exposes_per_group_policy_modal_and_icon():
    template = Path('app/templates/admin.html').read_text(encoding='utf-8')
    script = Path('app/static/js/admin/group.js').read_text(encoding='utf-8')

    assert 'id="group-deployment-policy-dialog"' in template
    assert 'group-deployment-policy-button' in template
    assert "'/deployment-policy'" in script
    assert "type: 'PUT'" in script


def test_deployment_policy_translations_have_the_same_complete_key_set(app):
    languages = ('en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh')
    with app.app_context():
        catalogs = [
            app.jinja_env.get_template(f'languages/{language}.html').module.deployment_policy
            for language in languages
        ]

    expected_keys = set(catalogs[0])
    expected_modes = set(catalogs[0]['modes'])
    for catalog in catalogs:
        assert set(catalog) == expected_keys
        assert set(catalog['modes']) == expected_modes == {'both', 'change_center', 'direct'}
        assert all(value for key, value in catalog.items() if key != 'modes')
