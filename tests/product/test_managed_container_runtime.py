import json
import shlex

import pytest
from flask import g

from app.modules.db.db_model import ServiceSetting
from app.modules.service import managed_runtime, container_settings


def bind():
    for setting,value in dict(dockerized='1',container_engine='podman',container_owner='proxy',container_name='rootless-proxy').items():
        ServiceSetting.create(server_id=11,service='haproxy',setting=setting,value=value)


def test_rootless_runtime_dispatch_uses_the_exact_owner_and_stdin_not_host_tcp(product,monkeypatch):
    bind();calls=[]
    class Remote:
        def __init__(self,server): assert server.server_id==11
        def run(self,args,**kwargs): calls.append((args,kwargs));return 'Version: test\n'
    monkeypatch.setattr(managed_runtime,'Remote',Remote)
    monkeypatch.setattr(managed_runtime.haproxy_runtime,'execute_runtime_command',lambda *_a,**_kw:pytest.fail('Rootless traffic used the host endpoint'))
    result=managed_runtime.execute_runtime_command(product.server.ip,1999,'show info')
    assert result=='Version: test\n'
    args,options=calls[0];data=json.loads(options['data'])
    assert data['runtime']==dict(engine='podman',owner='proxy',unit='')
    assert data['name']=='rootless-proxy' and data['payload']['command']=='show info'
    assert options['timeout']==20 and 'show info' not in ' '.join(args)


def test_container_http_credentials_are_not_exposed_in_process_arguments(product,monkeypatch):
    bind();calls=[]
    class Remote:
        def __init__(self,server): pass
        def run(self,args,**kw): calls.append((args,kw));return 'Active connections: 1\n'
    monkeypatch.setattr(managed_runtime,'Remote',Remote)
    result=managed_runtime.http_stats(product.server,'nginx',8080,'stats','stats-user','private-password')
    args,options=calls[0]
    assert 'private-password' not in ' '.join(args)
    assert json.loads(options['data'])['payload']['password']=='private-password'
    assert 'Active connections' in result


def test_managed_runtime_cannot_select_a_server_outside_the_active_group(app,product,monkeypatch):
    with app.test_request_context():
        g.user_params={'group_id':1}
        with pytest.raises(ValueError,match='current group'):
            managed_runtime.execute_runtime_command(product.other.ip,1999,'show info')


def test_master_worker_haproxy_reload_uses_usr2_instead_of_terminating_it_with_hup(product):
    for setting,value in dict(dockerized='1',container_engine='podman',container_owner='root',container_name='managed-proxy').items():
        ServiceSetting.create(server_id=11,service='haproxy',setting=setting,value=value)
    data=json.loads(shlex.split(container_settings.command(11,'haproxy',action='reload'))[-1])
    assert data['action']=='haproxy-reload' and data['container']=='managed-proxy'


def test_global_admin_retains_registered_cross_group_statistics_access(app, product, monkeypatch):
    calls = []
    monkeypatch.setattr(managed_runtime.requests, 'get', lambda url, **kwargs: calls.append((url, kwargs)) or 'response')
    with app.test_request_context():
        g.user_params = {'group_id': 1, 'role': 1}
        assert managed_runtime.statistics_response(product.other.ip, 'apache', 8080, '/server-status', 'user', 'secret') == 'response'
        with pytest.raises(ValueError, match='registered server'):
            managed_runtime.statistics_response('192.0.2.99', 'apache', 8080, '/', 'user', 'secret')
        g.user_params['role'] = 2
        with pytest.raises(ValueError, match='current group'):
            managed_runtime.statistics_response(product.other.ip, 'apache', 8080, '/', 'user', 'secret')
    assert len(calls) == 1 and calls[0][1]['allow_redirects'] is False


@pytest.mark.parametrize('service',['haproxy','apache'])
def test_stopped_container_has_a_real_stopped_status(product_client,product,monkeypatch,service):
    for setting,value in dict(dockerized='1',container_engine='podman',container_name='proxy').items():
        ServiceSetting.create(server_id=11,service=service,setting=setting,value=value)
    monkeypatch.setattr(managed_runtime,'execute_runtime_command',lambda *_:(_ for _ in ()).throw(ValueError('Container is not running')))
    monkeypatch.setattr(managed_runtime,'statistics_response',lambda *_:(_ for _ in ()).throw(RuntimeError('Container is not running')))
    monkeypatch.setattr(container_settings,'is_running',lambda *_:False)
    response=product_client.get(f'/service/{service}/11/status')
    assert response.status_code==200
    row=response.get_json()
    assert row['status']=='stopped' and row['Process']=='0' and not row.get('error')
