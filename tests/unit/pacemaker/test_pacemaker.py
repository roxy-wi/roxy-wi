import json
from types import SimpleNamespace

import pytest
from flask_jwt_extended import create_access_token
from pydantic import ValidationError

from app.modules.db.db_model import PacemakerCluster, PacemakerChange, PacemakerEvent, Server, InstallationTasks
from app.modules.pacemaker import service, operations
from app.modules.pacemaker import monitor
from app.modules.pacemaker.editor import Edit, build
from app.modules.pacemaker.schemas import ClusterCreate, Candidate, Action
from app.modules.pacemaker.xml import digest, parse, configuration, summary
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiResourceNotFound
import app.routes.pacemaker.routes as routes


CIB = '<cib epoch="1" num_updates="0"><configuration><crm_config/><nodes/><resources/><constraints/></configuration><status/></cib>'


@pytest.fixture
def cluster():
    servers = [Server.create(hostname=f'pcmk-test-{i}', ip=f'192.0.2.{210+i}', group_id='1') for i in (1, 2)]
    row = service.register(ClusterCreate(name='pcmk-test', members=[
        {'server_id': server.server_id, 'name': server.hostname, 'address': server.ip, 'nodeid': i}
        for i, server in enumerate(servers, 1)
    ]), 1)
    yield row
    row.delete_instance(recursive=True)
    for server in servers:
        server.delete_instance()


def test_digest_ignores_runtime_status_versions_and_xml_formatting():
    other = CIB.replace('epoch="1"', 'epoch="99"').replace('<status/>', '<status><node_state id="1"/></status>')
    assert digest(CIB) == digest(other)
    assert digest(CIB) != digest(CIB.replace('<resources/>', '<resources><primitive id="x"/></resources>'))


@pytest.mark.parametrize('value', [
    '<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]><cib><configuration>&y;</configuration></cib>',
    '<!DOCTYPE cib><cib><configuration/></cib>', '<a/>', '<cib/>',
    '<cib><configuration/><configuration/></cib>',
])
def test_untrusted_cib_is_rejected(value):
    with pytest.raises(ValueError):
        configuration(value)


def test_xml_size_is_bounded():
    with pytest.raises(ValueError):
        parse(' ' * (1024 * 1024 + 1))


def test_encryption_preserves_quotes_and_hides_resource_secrets():
    value = '<cib><configuration password="it\'s-secret"/></cib>'
    encrypted = service.encrypt(value)
    assert 'secret' not in encrypted
    assert service.decrypt(encrypted) == value


def test_registration_checks_active_group_and_unique_members(cluster):
    with pytest.raises(RoxywiResourceNotFound):
        service.get_cluster(cluster.id, 2)
    with pytest.raises(ValueError, match='already registered'):
        service.register(ClusterCreate(name='other', members=json.loads(cluster.servers)), 1)
    with pytest.raises(RoxywiResourceNotFound):
        service.register(ClusterCreate(name='wrong-group', members=json.loads(cluster.servers)), 2)


def test_moved_server_invalidates_saved_cluster_access(cluster):
    first_id = json.loads(cluster.servers)[0]['server_id']
    Server.update(group_id='2').where(Server.server_id == first_id).execute()
    with pytest.raises(RoxywiResourceNotFound):
        service.members(cluster)
    Server.update(group_id='1').where(Server.server_id == first_id).execute()


def test_cluster_operations_are_serialized_and_lock_released(cluster):
    with service.locked(cluster):
        with pytest.raises(RoxywiConflictError):
            with service.locked(cluster):
                pytest.fail('Concurrent lock acquired')
    with service.locked(cluster):
        pass


def test_draft_requires_current_configuration_and_encrypts_snapshots(cluster, monkeypatch):
    monkeypatch.setattr(service, 'connection', lambda _cluster: (None, CIB))
    with pytest.raises(RoxywiConflictError):
        service.draft(cluster, 1, Candidate(xml=CIB, base_digest='0' * 64))
    change = service.draft(cluster, 1, Candidate(xml=CIB, base_digest=digest(CIB)))
    assert '<cib' not in change.candidate
    assert service.decrypt(change.previous) == CIB


def test_restore_creates_a_fresh_draft_against_current_config(cluster, monkeypatch):
    monkeypatch.setattr(service, 'connection', lambda _cluster: (None, CIB))
    original = service.draft(cluster, 1, Candidate(xml=CIB, base_digest=digest(CIB)))
    restored = service.restore_draft(cluster, original.id, 1)
    assert restored.id != original.id and restored.status == 'draft'


def test_apply_requires_validation_and_unknown_result_cannot_be_replayed(cluster, monkeypatch):
    monkeypatch.setattr(service, 'connection', lambda _cluster: (None, CIB))
    change = service.draft(cluster, 1, Candidate(xml=CIB, base_digest=digest(CIB)))
    with pytest.raises(ValueError, match='Validate'):
        service.validate_or_apply(cluster, change.id, 1, apply=True)
    PacemakerChange.update(status='unknown').where(PacemakerChange.id == change.id).execute()
    with pytest.raises(RoxywiConflictError, match='already attempted'):
        service.validate_or_apply(cluster, change.id, 1, apply=True)


def test_apply_timeout_is_persisted_as_unknown(cluster, monkeypatch):
    class FailedRemote:
        def run(self, *_args, **_kwargs):
            raise TimeoutError('password=must-not-be-recorded')
    monkeypatch.setattr(service, 'connection', lambda _cluster: (FailedRemote(), CIB))
    monkeypatch.setattr(service, 'status', lambda _cluster: {'quorate': True})
    change = service.draft(cluster, 1, Candidate(xml=CIB, base_digest=digest(CIB)))
    PacemakerChange.update(status='validated').where(PacemakerChange.id == change.id).execute()
    with pytest.raises(TimeoutError):
        service.validate_or_apply(cluster, change.id, 1, apply=True)
    assert PacemakerChange.get_by_id(change.id).status == 'unknown'
    assert 'password' not in PacemakerChange.get_by_id(change.id).result


def test_queue_blocks_duplicate_operations(cluster):
    first = operations.enqueue(cluster, 1, 'bootstrap')
    try:
        with pytest.raises(RoxywiConflictError):
            operations.enqueue(cluster, 1, 'bootstrap')
    finally:
        first.delete_instance()


@pytest.mark.parametrize('wrapper', ['none', 'group', 'clone', 'promotable'])
def test_resource_builder_escapes_parameters_and_supports_containers(wrapper):
    candidate = build(CIB, Edit(base_digest=digest(CIB), kind='resource', data={
        'id': 'vip', 'agent': 'ocf:heartbeat:IPaddr2', 'parameters': {'ip': 'a<&"b'},
        'wrapper': wrapper, 'wrapper_id': 'vip-container',
    }))
    resource = configuration(candidate.xml).find('.//primitive')
    assert resource.get('provider') == 'heartbeat'
    assert resource.find('.//nvpair').get('value') == 'a<&"b'


@pytest.mark.parametrize('kind', ['location', 'colocation', 'order'])
def test_constraint_builder(kind):
    candidate = build(CIB, Edit(base_digest=digest(CIB), kind='constraint', data={
        'id': 'test-rule', 'type': kind, 'resource': 'vip', 'other': 'node1',
    }))
    assert configuration(candidate.xml).find(f'./constraints/rsc_{kind}') is not None


def test_operator_inputs_cannot_add_shell_options():
    with pytest.raises(ValidationError):
        Action(action='move', target='vip; shutdown -h now', node='node1')
    with pytest.raises(ValidationError):
        Action(action='fence', target='900')


def test_status_summary_never_exposes_resource_parameters():
    result = summary('<pacemaker-result><summary><current_dc name="n1" with_quorum="true"/></summary>'
                     '<nodes><node name="n1" online="true"/></nodes><resources><group id="g">'
                     '<resource id="r" role="Started"><node name="n1"/><secret password="hide"/></resource>'
                     '</group></resources></pacemaker-result>')
    assert result['quorate']
    assert result['resources'][0]['nodes'] == ['n1']
    assert 'password' not in json.dumps(result)


def test_clone_instance_controls_target_the_clone_container():
    result = summary('<pacemaker-result><summary/><resources><clone id="copies">'
                     '<resource id="worker:0"/><resource id="worker:1"/></clone></resources></pacemaker-result>')
    assert [resource['target_id'] for resource in result['resources']] == ['copies', 'copies']


def test_api_requires_authentication(client):
    assert client.get('/pacemaker/api', headers={'Accept': 'application/json'}).status_code == 401


def test_api_rejects_service_permission_revocation(client, authenticated, monkeypatch):
    monkeypatch.setattr(routes.auth, 'is_access_permit_to_service', lambda _service: False)
    assert client.get('/pacemaker/api', headers=authenticated[1]).status_code == 403


@pytest.mark.parametrize('suffix', ['/config', '/corosync', '/changes/1', '/logs/1'])
def test_viewer_cannot_read_secrets(client, authenticated, cluster, suffix):
    authenticated[0]['role'] = 4
    assert client.get(f'/pacemaker/api/{cluster.id}{suffix}', headers=authenticated[1]).status_code == 403


def test_viewer_cannot_queue_actions(client, authenticated, cluster):
    authenticated[0]['role'] = 4
    result = client.post(f'/pacemaker/api/{cluster.id}/actions', headers=authenticated[1], json={'action': 'standby', 'target': 'pcmk-test-1'})
    assert result.status_code == 403


def test_api_does_not_resolve_clusters_in_another_group(client, authenticated, cluster):
    authenticated[0]['group_id'] = 2
    assert client.get(f'/pacemaker/api/{cluster.id}/status', headers=authenticated[1]).status_code == 404


def test_page_renders_for_operator_and_viewer(app, client, authenticated):
    for role in (1, 4):
        authenticated[0]['role'] = role
        result = client.get('/pacemaker', headers=authenticated[1])
        assert result.status_code == 200
        assert ('id="pcmk-resource-form"' in result.text) == (role <= 3)


def test_monitor_deduplicates_failures_and_reports_recovery(cluster, monkeypatch):
    from app.modules.db.db_model import ServiceNotification
    PacemakerCluster.update(monitor_enabled=True).where(PacemakerCluster.id == cluster.id).execute()
    state = {'quorate': False, 'nodes': [], 'resources': [], 'failures': 0}
    monkeypatch.setattr(service, 'status', lambda _cluster: dict(state))
    initial = ServiceNotification.select().count()
    try:
        monitor.check(cluster)
        monitor.check(cluster)
        assert ServiceNotification.select().count() == initial + 1
        state['quorate'] = True
        monitor.check(cluster)
        assert ServiceNotification.select().count() == initial + 2
        assert service.get_cluster(cluster.id, 1).health == 'healthy'
    finally:
        ServiceNotification.delete().where(ServiceNotification.category == 'pacemaker').execute()


def test_monitor_opt_in_and_no_initial_healthy_notification(cluster, monkeypatch):
    from app.modules.db.db_model import ServiceNotification
    monkeypatch.setattr(service, 'status', lambda _cluster: {'quorate': True, 'nodes': [], 'resources': [], 'failures': 0})
    initial = ServiceNotification.select().count()
    monitor.check(cluster)
    assert ServiceNotification.select().count() == initial


def test_monitor_dispatch_queues_as_system_without_a_user(cluster):
    PacemakerCluster.update(monitor_enabled=True).where(PacemakerCluster.id == cluster.id).execute()
    try:
        assert monitor.dispatch() == 1
        saved = service.get_cluster(cluster.id, cluster.group_id)
        task = InstallationTasks.get_by_id(saved.active_task_id)
        assert task.user_id_id is None
        queued_event = PacemakerEvent.select().where(PacemakerEvent.cluster == cluster.id).order_by(PacemakerEvent.id.desc()).get()
        assert queued_event.user_id == 0
    finally:
        saved = service.get_cluster(cluster.id, cluster.group_id)
        if saved.active_task_id:
            InstallationTasks.delete().where(InstallationTasks.id == saved.active_task_id).execute()


def test_interrupted_apply_is_not_replayed(cluster, monkeypatch):
    from app.modules.operations.queue import serialize_operation_payload, deserialize_operation_payload
    monkeypatch.setattr(service, 'connection', lambda _cluster: (None, CIB))
    change = service.draft(cluster, 1, Candidate(xml=CIB, base_digest=digest(CIB)))
    task = operations.enqueue(cluster, 1, 'apply', {'change_id': change.id})
    payload = deserialize_operation_payload(task.operation_payload)
    payload['started'] = True
    task.operation_payload = serialize_operation_payload(payload)
    task.save()
    try:
        monkeypatch.setattr(service, 'validate_or_apply', lambda *_args, **_kw: pytest.fail('Remote write replayed'))
        assert operations.execute(task) == 'failed'
        assert PacemakerChange.get_by_id(change.id).status == 'unknown'
    finally:
        task.delete_instance()


def test_corosync_template_requires_a_separate_witness(cluster):
    from app.modules.pacemaker.corosync import render
    from app.modules.pacemaker.schemas import CorosyncCandidate
    first = json.loads(cluster.servers)[0]['server_id']
    with pytest.raises(ValueError, match='separate'):
        render(cluster, CorosyncCandidate(name=cluster.name, members=json.loads(cluster.servers), qdevice_server_id=first), service.members(cluster))


def test_membership_rejects_duplicate_ids_and_addresses(cluster):
    data = json.loads(cluster.servers)
    data[1]['nodeid'] = data[0]['nodeid']
    with pytest.raises(ValidationError):
        ClusterCreate(name='other', members=data)


def test_read_only_role_cannot_enable_background_monitoring(client, authenticated, cluster):
    authenticated[0]['role'] = 4
    response = client.put(f'/pacemaker/api/{cluster.id}/monitor', headers=authenticated[1], json={'enabled': True})
    assert response.status_code == 403


def test_pacemaker_navigation_belongs_to_services(client, authenticated):
    response = client.get('/pacemaker', headers=authenticated[1])
    services = response.text.split('data-nav-group="services"', 1)[1].split('data-nav-group="monitoring"', 1)[0]
    operations = response.text.split('data-nav-group="operations"', 1)[1].split('data-nav-group="services"', 1)[0]
    assert 'Corosync / Pacemaker' in services
    assert 'Corosync / Pacemaker' not in operations


def test_worker_rejects_changed_ssh_target_before_remote_execution(cluster, monkeypatch):
    task = operations.enqueue(cluster, 1, 'bootstrap')
    first_id = json.loads(cluster.servers)[0]['server_id']
    Server.update(port=2222).where(Server.server_id == first_id).execute()
    import app.modules.pacemaker.bootstrap as bootstrap
    monkeypatch.setattr(bootstrap, 'provision', lambda *_args: pytest.fail('Changed target was executed'))
    try:
        assert operations.execute(task) == 'failed'
    finally:
        task.delete_instance()


def test_migration_is_idempotent_and_preserves_existing_ha_tables(tmp_path):
    import importlib
    from peewee import SqliteDatabase
    migration = importlib.import_module('app.modules.db.migrations.20261027000000_pacemaker')
    database = SqliteDatabase(str(tmp_path / 'migration.db'), pragmas={'foreign_keys': 1})
    with database.bind_ctx([PacemakerCluster, PacemakerChange, PacemakerEvent]), database.connection_context():
        database.execute_sql('CREATE TABLE ha_clusters (id INTEGER PRIMARY KEY, name TEXT)')
        database.execute_sql("INSERT INTO ha_clusters (name) VALUES ('existing-keepalived')")
        migration.up()
        row = PacemakerCluster.create(name='migration-test', group_id=1)
        migration.up()
        assert PacemakerCluster.get_by_id(row.id).name == 'migration-test'
        assert database.execute_sql('SELECT name FROM ha_clusters').fetchone()[0] == 'existing-keepalived'
        assert {'pacemaker_clusters', 'pacemaker_changes', 'pacemaker_events'} <= set(database.get_tables())


def test_bootstrap_syn_flood_requires_an_explicit_boolean(client, authenticated, cluster, monkeypatch):
    calls = []
    def enqueue(_cluster, _user, action, data):
        calls.append((action, data))
        return SimpleNamespace(id=123, status='created')
    monkeypatch.setattr(operations, 'enqueue', enqueue)
    for value in (True, False):
        response = client.post(f'/pacemaker/api/{cluster.id}/bootstrap', headers=authenticated[1],
                               json={'confirm': cluster.name, 'syn_flood': value})
        assert response.status_code == 202
        assert calls[-1] == ('bootstrap', {'syn_flood': value, 'fence_pve': False})
    assert client.post(f'/pacemaker/api/{cluster.id}/bootstrap', headers=authenticated[1],
                       json={'confirm': cluster.name, 'syn_flood': 'false'}).status_code == 400


def test_docker_resource_uses_the_native_ocf_agent():
    body = Edit(base_digest=digest(CIB), kind='resource', data={
        'id': 'container-web', 'agent': 'ocf:heartbeat:docker',
        'parameters': {'image': 'nginx:stable', 'run_opts': '--network=host'},
    })
    result = configuration(build(CIB, body).xml)
    resource = result.find('./resources/primitive')
    assert resource.get('type') == 'docker' and resource.get('provider') == 'heartbeat'
    assert resource.find('./instance_attributes/nvpair[@name="image"]').get('value') == 'nginx:stable'


def test_container_bundle_actions_target_the_bundle_not_an_implicit_resource():
    state = summary('<pacemaker-result><summary/><resources><bundle id="web-bundle">'
                    '<replica id="0"><resource id="web-bundle-docker-0"/></replica>'
                    '</bundle></resources></pacemaker-result>')
    assert state['resources'][0]['target_id'] == 'web-bundle'


def test_service_submenu_respects_operator_and_viewer_access(client, authenticated):
    from bs4 import BeautifulSoup
    for role in (1, 4):
        authenticated[0]['role'] = role
        response = client.get('/pacemaker', headers=authenticated[1])
        soup = BeautifulSoup(response.text, 'html.parser')
        menu = soup.find(id='menu-pacemaker').find_parent('li')
        assert {'p_menu', 'nav-service'} <= set(menu['class'])
        assert menu.select_one('button.nav-submenu-toggle')['aria-expanded'] == 'false'
        links = {link['href'].rsplit('/', 1)[-1] for link in menu.select('ul.v_menu a')}
        assert {'pacemaker', 'resources', 'history'} <= links
        for section in ('configuration', 'quorum', 'logs', 'monitoring'):
            assert (section in links) == (role <= 3)
        assert soup.find(id='pcmk-history-panel')
        assert bool(soup.find(id='pcmk-logs-panel')) == (role <= 3)


@pytest.mark.parametrize('view', ['resources', 'configuration', 'quorum', 'logs', 'monitoring', 'history'])
def test_service_pages_have_separate_views_and_no_visible_installer(client, authenticated, view):
    from bs4 import BeautifulSoup
    response = client.get('/pacemaker/' + view, headers=authenticated[1])
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, 'html.parser')
    assert soup.find(id='pacemaker-app')['data-view'] == view
    setup = soup.find(attrs={'data-pcmk-view': 'setup'})
    assert setup.has_attr('hidden')
    assert setup.find(id='pcmk-bootstrap-syn')
    authenticated[0]['role'] = 4
    assert client.get('/pacemaker/' + view, headers=authenticated[1]).status_code == (200 if view in ('resources','history') else 403)


def test_syn_flood_and_bootstrap_belong_to_installation(client, authenticated):
    from bs4 import BeautifulSoup
    response = client.get('/install/pacemaker?setup=new', headers=authenticated[1])
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, 'html.parser')
    assert soup.find(id='pacemaker-app')['data-view'] == 'setup'
    assert not soup.find(attrs={'data-pcmk-view': 'setup'}).has_attr('hidden')
    assert soup.find(id='pcmk-bootstrap-syn')
    response = client.get('/pacemaker?setup=new', headers=authenticated[1])
    assert response.status_code == 302 and '/install/pacemaker' in response.headers['Location']


def test_bootstrap_proxmox_fencing_is_explicit_and_strict(client, authenticated, cluster, monkeypatch):
    calls = []
    monkeypatch.setattr(operations, 'enqueue', lambda _c, _u, _action, data: (calls.append(data) or SimpleNamespace(id=42, status='created')))
    response = client.post(f'/pacemaker/api/{cluster.id}/bootstrap', headers=authenticated[1],
                           json={'confirm': cluster.name, 'fence_pve': True})
    assert response.status_code == 202
    assert calls == [{'syn_flood': False, 'fence_pve': True}]
    assert client.post(f'/pacemaker/api/{cluster.id}/bootstrap', headers=authenticated[1],
                       json={'confirm': cluster.name, 'fence_pve': 'true'}).status_code == 400
