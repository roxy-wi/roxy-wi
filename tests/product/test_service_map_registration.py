"""Service-map reads must preserve the diagnostic registration boundary."""
import pytest

from app.modules.db.db_model import Server, OperationalAssessment, InstallationTasks
from app.modules.service import service_map, proxy_assessments as assessments
from tests.product.test_service_map import discover, confirm
from tests.product.test_proxy_diagnostics import diagnostic_host


def replace_server(same_ip):
    old = Server.get_by_id(11)
    values = dict(old.__data__)
    values.pop('registration_key')
    values.update(hostname='Replacement proxy', ip=old.ip if same_ip else '192.0.2.77')
    Server.delete().where(Server.server_id == old.server_id).execute()
    replacement = Server.create(**values)
    assert replacement.server_id == old.server_id
    assert replacement.registration_key != old.registration_key
    return replacement


@pytest.mark.parametrize('same_ip', [False, True])
def test_replacement_cannot_inherit_map_or_operator_confirmation(product_client, diagnostic_host, same_ip):
    ident = discover(product_client)
    confirmation = confirm(product_client, ident)
    assert confirmation.status_code == 201
    replace_server(same_ip)
    response = product_client.get('/insights/api/services')
    assert response.status_code == 200 and response.json['data'] == []
    assert service_map.latest(1) == []
    assert product_client.get(f'/insights/api/assessments/{ident}').status_code == 404
    assert confirm(product_client, ident).status_code == 404
    assert product_client.delete('/insights/api/services/confirm/' + str(confirmation.json['id'])).status_code == 404
    assert OperationalAssessment.get_by_id(ident).result
    fresh = discover(product_client)
    rows = product_client.get('/insights/api/services').json['data']
    assert {row['assessment_id'] for row in rows} == {fresh}
    assert all(row['server'] == 'Replacement proxy' and row['confirmation'] is None for row in rows)


def test_unbound_legacy_map_is_retained_without_attributing_it_to_current_host(product_client, diagnostic_host):
    ident = discover(product_client)
    OperationalAssessment.update(server_registration_key='').where(OperationalAssessment.id == ident).execute()
    response = product_client.get('/insights/api/services')
    assert response.status_code == 200 and response.json['data'] == []
    assert service_map.latest(1) == []
    assert confirm(product_client, ident).status_code == 404
    assert OperationalAssessment.get_by_id(ident).result


def test_cached_map_row_is_rechecked_before_decrypting_its_report(product_client, product, diagnostic_host, monkeypatch):
    ident = discover(product_client)
    stale = OperationalAssessment.get_by_id(ident)
    replace_server(True)
    monkeypatch.setattr(service_map, 'latest', lambda _group: [stale])
    def forbidden_decrypt(_payload):
        raise AssertionError('Previous registration must not be decrypted for the replacement')
    monkeypatch.setattr(service_map, 'unseal', forbidden_decrypt)
    result = service_map.view(1, product.admin.user_id)
    assert result['data'] == [] and result['omitted'] == 1


def test_map_queued_for_previous_registration_cannot_run_on_replacement(product_client, diagnostic_host):
    queued = product_client.post('/insights/api/services/discover', json={'service': 'haproxy', 'server_id': 11})
    assert queued.status_code == 202
    replace_server(True)
    assert assessments.execute(InstallationTasks.get_by_id(queued.json['task_id'])) == 'failed'
    assert not diagnostic_host.discoveries and not diagnostic_host.calls
    assert product_client.get('/insights/api/services').json['data'] == []
