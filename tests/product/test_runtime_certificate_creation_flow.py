from uuid import uuid4

import pytest

from app.modules.db.db_model import Server, UserGroups
from tests.product.test_runtime_certificates import run


@pytest.fixture(params=['directory', 'crt_list'])
def create_request(product_client, product, certificate_host, request):
    url = f'/service/haproxy/certificates/{product.server.server_id}'
    catalog = product_client.get(url).json
    assert catalog['can_create']
    destination = next(item for item in catalog['destinations'] if item['kind'] == request.param)
    return url + '/new', dict(name='new.pem', pem=certificate_host.new,
                             destination=destination, operation_id=str(uuid4()))


@pytest.mark.parametrize('failure', ['', 'deploy', 'destination', 'collision'])
def test_new_certificate_synchronizes_or_rolls_back_cluster(product_client, product, certificate_host, create_request, failure):
    host = certificate_host
    slave = Server.create(server_id=12, ip='192.0.2.12', hostname='Slave', group_id='1',
                          master=product.server.server_id, haproxy=1)
    host.add(slave.ip, host.old)
    target = host.files[slave.ip].parent / 'new.pem'
    if failure == 'deploy':
        host.failed_hosts.add(slave.ip)
    elif failure == 'destination':
        host.sources = {key: value for key, value in host.sources.items() if slave.ip not in key}
    elif failure == 'collision':
        target.write_text(host.old)
    url, body = create_request
    response = product_client.post(url, json=body)
    assert response.status_code == 202, response.text
    task_id = response.json['id']
    assert product_client.post(url, json=body).json['id'] == task_id
    assert run(task_id) == ('failed' if failure else 'completed')
    for server in (product.server, slave):
        new_file = host.files[server.ip].parent / 'new.pem'
        if not failure:
            assert new_file.read_text() == host.new
            assert host.active[str(new_file)] == host.new
        elif failure == 'collision' and server == slave:
            assert new_file.read_text() == host.old
        else:
            assert not new_file.exists()
            assert str(new_file) not in host.active
        assert host.files[server.ip].read_text() == host.old
    result = product_client.get(f'/service/haproxy/certificates/operations/{task_id}').json
    assert not result['retryable']
    if failure in ('destination', 'collision'):
        assert all(t['status'] == 'not_applied' for t in result['targets'])
        assert not any(c.startswith(('new ', 'set ', 'add ')) for c in host.calls)
    assert not list(host.root.rglob('pending.json'))


def test_creation_authorization_validation_and_idempotency(product_client, product, create_request):
    url, body = create_request
    assert product_client.post(url, json=body | {'name': '../new.pem'}).status_code == 400
    assert product_client.post(url, json=body | {'pem': 'invalid'}).status_code == 400
    assert product_client.post(url, json=body | {'destination': {'path': '/', 'kind': 'unknown'}}).status_code == 400
    assert product_client.post(f'/service/haproxy/certificates/{product.other.server_id}/new', json=body).status_code == 404
    csrf = product_client.environ_base.pop('HTTP_X_CSRF_TOKEN')
    assert product_client.post(url, json=body).status_code == 401
    product_client.environ_base['HTTP_X_CSRF_TOKEN'] = csrf
    assert product_client.post(url, json=body).status_code == 202
    assert product_client.post(url, json=body | {'destination': {'path': '/different', 'kind': 'directory'}}).status_code == 409
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.post(url, json=body | {'operation_id': str(uuid4())}).status_code == 403
    assert not product_client.get(url.removesuffix('/new')).json['can_create']
