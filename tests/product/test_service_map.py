import json
import pytest
from app.modules.db.db_model import InstallationTasks, OperationalAssessment, UserGroups, Server, PacemakerCluster
from app.modules.operations.queue import deserialize_operation_payload as unseal
from app.modules.service import proxy_assessments as assessments
from tests.product.test_proxy_diagnostics import diagnostic_host


def discover(client):
    response=client.post('/insights/api/services/discover',json=dict(service='haproxy',server_id=11))
    assert response.status_code==202,response.text
    assert assessments.execute(InstallationTasks.get_by_id(response.json['task_id']))=='completed'
    return response.json['id']


def confirm(client,ident,**values):
    return client.post('/insights/api/services/confirm',json=dict(assessment_id=ident,frontend_id='frontend:public',domain='example.test',note='Confirmed against the application registry',**values))


def test_discovery_is_durable_encrypted_and_confirmation_is_separate(product_client,diagnostic_host):
    ident=discover(product_client)
    assert OperationalAssessment.get_by_id(ident).result.startswith('fernet:')
    from app.modules.service import service_map
    service_map.view(1, OperationalAssessment.get_by_id(ident).user_id)
    row=product_client.get('/insights/api/services').json['data'][0]
    assert row['relationship']=='discovered' and row['domain']=='example.test'
    assert row['backends'][0]['host']=='192.0.2.88' and row['confirmation'] is None
    assert not diagnostic_host.calls # config/interface discovery only; no traffic probes
    response=confirm(product_client,ident);assert response.status_code==201,response.text
    row=product_client.get('/insights/api/services').json['data'][0]
    assert row['relationship']=='confirmed' and row['domain_origin']=='discovered'
    assert product_client.delete('/insights/api/services/confirm/'+str(response.json['id'])).status_code==200
    assert product_client.get('/insights/api/services').json['data'][0]['relationship']=='discovered'


def test_manual_domain_remains_operator_supplied_and_never_changes_configuration(product_client,diagnostic_host):
    ident=discover(product_client)
    response=product_client.post('/insights/api/services/confirm',json=dict(assessment_id=ident,frontend_id='frontend:public',domain='manual.example.test',note='Known application routing alias'))
    assert response.status_code==201
    rows=product_client.get('/insights/api/services').json['data']
    manual=next(row for row in rows if row['domain']=='manual.example.test')
    assert manual['domain_origin']=='operator-supplied' and manual['relationship']=='confirmed'
    assert not diagnostic_host.calls


def test_superseded_snapshot_and_unknown_frontend_are_rejected(product_client,diagnostic_host):
    ident=discover(product_client)
    assert product_client.post('/insights/api/services/confirm',json=dict(assessment_id=ident,frontend_id='shell:unknown',domain='example.test',note='Test unknown frontend')).status_code==400
    discover(product_client)
    assert confirm(product_client,ident).status_code==409
    assert product_client.get('/insights/api/assessments/'+str(ident)).status_code==200


def test_impact_links_registered_proxy_ha_and_backend_candidates_without_predicting_outage(product_client,product,diagnostic_host):
    Server.create(server_id=33,hostname='Backend',ip='192.0.2.88',group_id='1',cred_id=11)
    Server.create(server_id=44,hostname='HA peer',ip='192.0.2.44',group_id='1',cred_id=11)
    PacemakerCluster.create(name='Product HA',group_id=1,servers=json.dumps([dict(server_id=11,name='node1'),dict(server_id=44,name='node2')]))
    discover(product_client)
    for ident in (11,33,44):
        data=product_client.get('/insights/api/services?impact_node='+str(ident)).json
        assert len(data['data'])==1 and 'not an outage prediction' in data['summary']
    assert product_client.get('/insights/api/services?impact_node=22').status_code==400
    row=product_client.get('/insights/api/services').json['data'][0]
    assert row['ha'][0]['members']==[11,44]


def test_identity_change_is_visible_and_prevents_confirmation(product_client,diagnostic_host):
    ident=discover(product_client)
    Server.update(ip='192.0.2.77').where(Server.server_id==11).execute()
    assert not product_client.get('/insights/api/services').json['data'][0]['identity_current']
    assert confirm(product_client,ident).status_code==409


def test_tenant_and_read_only_role_cannot_confirm_or_probe(product_client,product,diagnostic_host):
    ident=discover(product_client)
    OperationalAssessment.update(group_id=2).where(OperationalAssessment.id==ident).execute()
    assert confirm(product_client,ident).status_code==404
    assert product_client.get('/insights/api/services').json['data']==[]
    UserGroups.update(user_role_id=4).where(UserGroups.user_id==product.admin.user_id).execute()
    assert confirm(product_client,ident).status_code==403
    assert product_client.post('/insights/api/services/discover',json=dict(service='haproxy',server_id=11)).status_code==403


def test_failed_refresh_retains_successful_snapshot_and_secret_paths_never_leave_parser(product_client,diagnostic_host,monkeypatch):
    ident=discover(product_client)
    monkeypatch.setattr(assessments.inventory,'discover',lambda *args:(_ for _ in ()).throw(RuntimeError('PRIVATE PASSWORD')))
    response=product_client.post('/insights/api/services/discover',json=dict(service='haproxy',server_id=11))
    assert assessments.execute(InstallationTasks.get_by_id(response.json['task_id']))=='failed'
    result=product_client.get('/insights/api/services')
    assert result.json['data'][0]['assessment_id']==ident
    assert 'PRIVATE PASSWORD' not in result.text and '/private/site.pem' not in result.text


def test_map_and_diagnostics_have_independent_queue_locks_and_history(product_client, diagnostic_host):
    from tests.product.test_proxy_diagnostics import queue
    mapping = product_client.post('/insights/api/services/discover', json=dict(service='haproxy', server_id=11))
    diagnostic = queue(product_client)
    assert mapping.status_code == diagnostic.status_code == 202
    assert product_client.post('/insights/api/services/discover', json=dict(service='haproxy', server_id=11)).status_code == 409
    assert queue(product_client).status_code == 409
    for response in (mapping, diagnostic):
        assert assessments.execute(InstallationTasks.get_by_id(response.json['task_id'])) == 'completed'
    history = product_client.get('/insights/api/diagnostics?service=haproxy&server_id=11').json['data']
    assert [row['id'] for row in history] == [diagnostic.json['id']]
    assert {row['assessment_id'] for row in product_client.get('/insights/api/services').json['data']} == {mapping.json['id']}


def test_task_kind_cannot_be_changed_to_overwrite_another_report(product_client, diagnostic_host):
    from app.modules.operations.queue import serialize_operation_payload as seal
    from tests.product.test_proxy_diagnostics import queue
    response = queue(product_client)
    task = InstallationTasks.get_by_id(response.json['task_id'])
    payload = unseal(task.operation_payload)
    payload['kind'] = 'service-map'
    payload['request'].pop('url')
    payload['request'].pop('frontend_id')
    InstallationTasks.update(operation_payload=seal(payload)).where(InstallationTasks.id == task.id).execute()
    assert assessments.execute(task) == 'failed'
    assert not diagnostic_host.discoveries
    assert OperationalAssessment.get_by_id(response.json['id']).result == ''


def test_ha_topology_queries_do_not_grow_with_proxy_count(product_client, product, diagnostic_host):
    from playhouse.test_utils import count_queries
    from app.modules.db.db_model import HaCluster, HaClusterRouter, HaClusterSlave, HaClusterVip
    from app.modules.service import service_map
    cluster = HaCluster.create(name='VIP pair', description='Product test', group_id=1)
    router = HaClusterRouter.create(cluster_id=cluster)
    HaClusterSlave.create(cluster_id=cluster, router_id=router, server_id=11)
    HaClusterVip.create(cluster_id=cluster, router_id=router, vip='192.0.2.100')
    PacemakerCluster.create(name='Product HA', group_id=1, servers=json.dumps([dict(server_id=11), dict(server_id=22)]))
    with count_queries() as queries:
        result = service_map.ha_dependencies(1, product.admin.user_id, {11})
    # One permissions lookup and four topology reads; never one query per cluster/node.
    assert len(queries.get_queries()) <= 6
    assert result[11][0]['vips'] == ['192.0.2.100']
    assert result[11][1]['members'] == [11]  # foreign-group node 22 stays outside the map
    discover(product_client)
    Server.create(server_id=44, hostname='Second proxy', ip='192.0.2.44', group_id='1', cred_id=11, haproxy=1)
    response = product_client.post('/insights/api/services/discover', json=dict(service='haproxy', server_id=44))
    assert assessments.execute(InstallationTasks.get_by_id(response.json['task_id'])) == 'completed'
    with count_queries() as queries:
        result = service_map.view(1, product.admin.user_id)
    assert {row['server_id'] for row in result['data']} == {11, 44}
    topology_reads = [q.getMessage() for q in queries.get_queries() if any('"'+name+'"' in q.getMessage() for name in ('ha_clusters', 'ha_cluster_slaves', 'ha_cluster_vips', 'pacemaker_clusters'))]
    assert len(topology_reads) == 4


def test_confirmation_lookup_index_upgrade_is_idempotent_and_retains_evidence(product_client, diagnostic_host):
    from importlib import import_module
    from peewee import SqliteDatabase
    from playhouse.migrate import MySQLMigrator, SqliteMigrator, migrate
    from app.modules.db.db_model import PublishedServiceConfirmation
    ident = discover(product_client)
    response = confirm(product_client, ident)
    assert response.status_code == 201
    database = PublishedServiceConfirmation._meta.database
    table = PublishedServiceConfirmation._meta.table_name
    index = next(index for index in database.get_indexes(table) if tuple(index.columns) == ('assessment_id',))
    migrator = SqliteMigrator(database) if isinstance(database, SqliteDatabase) else MySQLMigrator(database)
    migrate(migrator.drop_index(table, index.name))
    migration = import_module('app.modules.db.migrations.20261030020000_published_service_confirmation_index')
    migration.up()
    migration.up()
    assert sum(tuple(index.columns) == ('assessment_id',) for index in database.get_indexes(table)) == 1
    assert PublishedServiceConfirmation.get_by_id(response.json['id']).assessment_id == ident
    assert product_client.get('/insights/api/services').json['data'][0]['relationship'] == 'confirmed'
