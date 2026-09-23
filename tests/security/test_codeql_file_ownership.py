from pathlib import Path
from types import SimpleNamespace

import pytest
from flask_jwt_extended import create_access_token
from peewee import SqliteDatabase

from app.modules.config import add, common as config_common, config as config_mod
from app.modules.db import config as config_sql, server as server_sql
from app.modules.db.db_model import Server, ConfigVersion
from app.modules.roxywi import auth, common
from app.routes.config import routes
from app.routes.waf import routes as waf_routes

pytestmark = pytest.mark.security
SERVER = 'edge-prod.example.com'
SERVICES = ['haproxy', 'nginx', 'apache', 'keepalived']


@pytest.fixture
def editor(app, monkeypatch):
    params = dict(user_id=1, user='test', role=3, group_id=1, lang='en', servers=[], user_services=[])
    server = SimpleNamespace(server_id=1, ip=SERVER, group_id=1, hostname=SERVER)
    monkeypatch.setattr(common, 'get_users_params', lambda **_: dict(params))
    monkeypatch.setattr(auth, 'is_admin', lambda level=1, **_: 3 <= level)
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: True)
    monkeypatch.setattr(common, 'check_user_group_for_flask', lambda: True)
    monkeypatch.setattr(common.server_sql, 'get_server_by_ip', lambda _: server)
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1', 'user_id': 1})
    return {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}


@pytest.fixture
def versions(tmp_path, monkeypatch):
    for service in SERVICES:
        (tmp_path / service).mkdir()
    monkeypatch.setattr(config_common, 'get_config_dir', lambda service: str(tmp_path / service) + '/')
    records = {}
    monkeypatch.setattr(config_sql, 'get_config_version',
                        lambda owner, service, path: records.get((owner, service, str(Path(path).resolve()))))

    def make(service, owner=SERVER, content='own config\n'):
        path = Path(config_common.generate_config_path(service, owner))
        path.write_text(content)
        records[(owner, service, str(path.resolve()))] = SimpleNamespace(local_path=str(path), remote_path='/etc/service/site.conf')
        return path
    return make


@pytest.mark.parametrize('service', SERVICES)
@pytest.mark.parametrize('operation', ['compare_left', 'compare_right', 'show', 'save'])
def test_foreign_version_is_rejected_before_read_or_deployment(client, editor, versions, monkeypatch, service, operation):
    own = versions(service)
    foreign = versions(service, SERVER + '-foreign.example.com', 'foreign secret\n')
    monkeypatch.setattr(config_mod, 'diff_config', lambda *a: pytest.fail('Read foreign config'))
    monkeypatch.setattr(config_mod, 'open', lambda *a, **k: pytest.fail('Read foreign config'), raising=False)
    monkeypatch.setattr(config_mod, 'upload_and_restart', lambda *a, **k: pytest.fail('Deployed foreign config'))
    monkeypatch.setattr(config_mod, 'master_slave_upload_and_restart', lambda *a, **k: pytest.fail('Deployed foreign config'))
    monkeypatch.setattr(routes.deployment_policy, 'require_direct_deployment_for_server', lambda *a, **k: None)
    monkeypatch.setattr(routes.service_sql, 'select_service', lambda name: SimpleNamespace(slug=name))
    monkeypatch.setattr(routes.config_sql, 'select_remote_path_from_version', lambda **kw: '/etc/service/site.conf')
    monkeypatch.setattr(routes.roxywi_common, 'logging', lambda *a, **k: None)
    if operation.startswith('compare'):
        left, right = (foreign, own) if operation == 'compare_left' else (own, foreign)
        response = client.post(f'/config/compare/{service}/{SERVER}/show', headers=editor,
                               json={'left': left.name, 'right': right.name})
    elif operation == 'show':
        response = client.post(f'/config/{service}/show', headers=editor,
                               json={'serv': SERVER, 'configver': foreign.name})
    else:
        response = client.post(f'/config/versions/{service}/{SERVER}/{foreign.name}/save', headers=editor,
                               json={'action': 'reload'})
    assert response.status_code == 400 and response.json['status'] == 'failed'
    assert foreign.read_text() == 'foreign secret\n'


@pytest.mark.parametrize('service', SERVICES)
@pytest.mark.parametrize('historical', [False, True])
def test_own_versions_remain_comparable_readable_and_deployable(client, editor, versions, monkeypatch, service, historical):
    old = versions(service, content='before\n')
    new = versions(service, content='after\n')
    if historical:
        historical_path = new.with_name('legacy-site-' + new.name)
        new.rename(historical_path)
        new = historical_path
        monkeypatch.setattr(config_sql, 'get_config_version', lambda owner, kind, path:
                            SimpleNamespace(local_path=str(path), remote_path='/etc/service/site.conf')
                            if owner == SERVER and kind == service and Path(path) in (old, new) else None)
    response = client.post(f'/config/compare/{service}/{SERVER}/show', headers=editor,
                           json={'left': old.name, 'right': new.name})
    assert '-before' in response.json['compare'] and '+after' in response.json['compare']

    monkeypatch.setattr(config_mod.user_sql, 'get_user_role_in_group', lambda *a: 3)
    monkeypatch.setattr(config_mod.server_sql, 'is_serv_protected', lambda *a: False)
    monkeypatch.setattr(config_mod.service_sql, 'select_service_setting', lambda *a: '1')
    monkeypatch.setattr(common, 'get_user_lang_for_flask', lambda: {})
    monkeypatch.setattr(config_mod.deployment_policy, 'direct_deployment_allowed', lambda *a: True)
    monkeypatch.setattr(config_mod, 'render_template', lambda template, **kw: ''.join(kw['conf']))
    response = client.post(f'/config/{service}/show', headers=editor,
                           json={'serv': SERVER, 'configver': new.name})
    assert response.status_code == 200 and response.json['data'] == 'after\n'

    uploads = []
    monkeypatch.setattr(routes.deployment_policy, 'require_direct_deployment_for_server', lambda *a, **k: None)
    monkeypatch.setattr(routes.service_sql, 'select_service', lambda name: SimpleNamespace(slug=name))
    monkeypatch.setattr(routes.config_sql, 'select_remote_path_from_version', lambda **kw: '/etc/service/site.conf')
    monkeypatch.setattr(routes.roxywi_common, 'logging', lambda *a, **k: None)
    def upload(server, path, action, kind, **kwargs):
        uploads.append((server, Path(path), action, kind, kwargs))
        return 'saved'
    monkeypatch.setattr(config_mod, 'upload_and_restart', upload)
    monkeypatch.setattr(config_mod, 'master_slave_upload_and_restart', upload)
    response = client.post(f'/config/versions/{service}/{SERVER}/{new.name}/save', headers=editor,
                           json={'action': 'reload'})
    assert response.status_code == 201 and response.json['data'] == 'saved'
    assert uploads[0][:4] == (SERVER, new, 'reload', service)
    if service in ('nginx', 'apache'):
        assert uploads[0][4]['config_file_name'] == '/etc/service/site.conf'


@pytest.mark.parametrize('service', SERVICES)
def test_address_reuse_does_not_transfer_saved_version_ownership(client, editor, tmp_path, monkeypatch, service):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / service
    directory.mkdir()
    monkeypatch.setattr(config_common, 'get_config_dir', lambda _: str(directory))
    monkeypatch.setattr(common, 'get_user_lang_for_flask', lambda: 'en')
    database = SqliteDatabase(':memory:')
    with database.bind_ctx([Server, ConfigVersion]):
        database.create_tables([Server, ConfigVersion])
        original = Server.create(hostname='original', ip=SERVER, group_id='2')
        saved = Path(config_common.generate_config_path(service, SERVER))
        saved.write_text('original owner secret\n')
        ConfigVersion.create(server_id=original.server_id, user_id=1, service=service,
                             local_path=str(saved.relative_to(tmp_path)), remote_path='/etc/service/site.conf', diff='')
        new_address = 'moved.example.com'
        server_sql.update_server('original', new_address, '2', 0, 1, 0, original.server_id, 1, 22, '', 0, 0)
        Server.create(hostname='replacement', ip=SERVER, group_id='1')

        # Old records with relative paths remain usable by the immutable owner after moving.
        assert config_common.resolve_saved_config_path(service, new_address, saved.name) == str(saved)
        assert config_sql.select_remote_path_from_version(new_address, service, str(saved)) == '/etc/service/site.conf'
        monkeypatch.setattr(config_mod, 'render_template', lambda template, **kw: kw['return_files'])
        assert config_mod.show_compare_config(new_address, service) == [saved.name]
        assert config_mod.show_compare_config(SERVER, service) == []

        monkeypatch.setattr(config_mod, 'diff_config', lambda *a: pytest.fail('Read reassigned-address version'))
        monkeypatch.setattr(config_mod, 'open', lambda *a, **k: pytest.fail('Read reassigned-address version'), raising=False)
        monkeypatch.setattr(config_mod, 'upload_and_restart', lambda *a, **k: pytest.fail('Deployed reassigned-address version'))
        monkeypatch.setattr(config_mod, 'master_slave_upload_and_restart', lambda *a, **k: pytest.fail('Deployed reassigned-address version'))
        for url, body in [
            (f'/config/compare/{service}/{SERVER}/show', {'left': saved.name, 'right': saved.name}),
            (f'/config/{service}/show', {'serv': SERVER, 'configver': saved.name}),
            (f'/config/versions/{service}/{SERVER}/{saved.name}/save', {'action': 'reload'}),
        ]:
            response = client.post(url, headers=editor, json=body)
            assert response.status_code == 400 and response.json['status'] == 'failed'
    database.close()


@pytest.fixture
def maps(tmp_path, monkeypatch):
    monkeypatch.setattr(add.get_config, 'get_config_var', lambda *a: str(tmp_path))
    monkeypatch.setattr(add.common, 'set_correct_owner', lambda *a: None)
    monkeypatch.setattr(add.roxywi_common, 'logging', lambda *a, **k: None)
    return tmp_path / 'maps'


@pytest.mark.parametrize('kind', ['absolute', 'traversal', 'backslash', 'empty'])
def test_map_creation_cannot_escape_group(maps, monkeypatch, kind):
    foreign = maps / '2'
    foreign.mkdir(parents=True)
    names = {'absolute': str(foreign / 'injected'), 'traversal': '../2/injected',
             'backslash': '..\\2\\injected', 'empty': ''}
    monkeypatch.setattr(add.common, 'set_correct_owner', lambda *a: pytest.fail('Filesystem mutation before validation'))
    with pytest.raises(ValueError):
        add.create_map(SERVER, names[kind], '1')
    assert list(foreign.iterdir()) == []
    assert not (maps / '1').exists()


@pytest.mark.parametrize('name', ['routes', 'routes.map', 'routes.old.map'])
def test_map_creation_preserves_extension_and_existing_files(maps, name):
    assert add.create_map(SERVER, name, '1') == 'success: '
    target = maps / '1' / 'routes.map'
    assert target.is_file()
    target.write_text('existing routes')
    assert add.edit_map('routes.map', '1') == 'existing routes'
    with pytest.raises(Exception, match='Cannot create'):
        add.create_map(SERVER, name, '1')
    assert target.read_text() == 'existing routes'


@pytest.mark.parametrize('directory_link', [False, True])
def test_map_symlinks_cannot_target_other_groups(maps, directory_link):
    foreign = maps / '2'
    foreign.mkdir(parents=True)
    (foreign / 'routes.map').write_text('foreign')
    group = maps / '1'
    try:
        if directory_link:
            group.symlink_to(foreign, target_is_directory=True)
        else:
            group.mkdir()
            (group / 'routes.map').symlink_to(foreign / 'routes.map')
    except OSError:
        pytest.skip('Symlink creation requires OS privileges')
    for operation in (lambda: add.create_map(SERVER, 'routes.map', '1'),
                      lambda: add.edit_map('routes.map', '1'),
                      lambda: add.save_map('routes.map', 'changed', '1', SERVER, 'save'),
                      lambda: add.delete_map('routes.map', '1', SERVER)):
        with pytest.raises(ValueError):
            operation()
    assert (foreign / 'routes.map').read_text() == 'foreign'


def test_waf_candidates_have_independent_paths(client, editor, tmp_path, monkeypatch):
    monkeypatch.setattr(auth, 'is_admin', lambda level=1, **_: 2 <= level)
    monkeypatch.setattr(waf_routes.roxywi_common, 'check_is_server_in_group', lambda *a: None)
    monkeypatch.setattr(waf_routes.sql, 'get_setting', lambda key: str(tmp_path) + '/')
    monkeypatch.setattr(waf_routes.common, 'resolve_waf_config_path', lambda *a: '/etc/waf/rules/test.conf')
    candidates = []
    monkeypatch.setattr(config_mod, 'master_slave_upload_and_restart',
                        lambda server, cfg, *a, **kw: candidates.append(Path(cfg)) or 'saved')
    for content in ['first', 'second']:
        response = client.post(f'/waf/haproxy/{SERVER}/rule/1/save', headers=editor,
                               json={'action': 'save', 'config': content, 'config_file_name': 'test.conf'})
        assert response.status_code == 200 and response.json['data'] == 'saved'
    assert len(set(candidates)) == 2
    assert [path.read_text() for path in candidates] == ['first', 'second']
    assert all(path.parent == tmp_path for path in candidates)
