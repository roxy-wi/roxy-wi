import pytest

from app.modules.db.db_model import ServiceSetting, User, UserGroups
from app.modules.service import container_settings


def body(**fields):
    return dict(serverSettingsSave='11',serverSettingsDockerized='1',serverSettingsRestart='0',
                container_engine='podman',container_owner='root',container_name='proxy-lab',container_unit='proxy-lab.service',**fields)


def test_engine_identity_is_saved_without_recreating_a_container(product_client,product,monkeypatch):
    monkeypatch.setattr(container_settings,'discover',lambda *_:pytest.fail('Saving a binding must not contact hosts'))
    response=product_client.post('/service/settings/haproxy',data=body())
    assert response.status_code==200,response.text
    assert container_settings.runtime(11,'haproxy')==dict(engine='podman',owner='root',unit='proxy-lab.service')
    assert container_settings.name(11,'haproxy')=='proxy-lab'
    response=product_client.get('/service/settings/haproxy/11')
    assert response.status_code==200 and 'value="podman" selected' in response.text
    assert 'proxy-lab.service' in response.text and 'Discover containers' in response.text
    changed=body();changed.update(container_name='',container_unit='')
    assert product_client.post('/service/settings/haproxy',data=changed).status_code==200
    assert ServiceSetting.get((ServiceSetting.server_id==11)&(ServiceSetting.setting=='container_name')).value==''


@pytest.mark.parametrize('fields',[dict(container_engine='unknown'),dict(container_owner='root; id'),
    dict(container_unit='../sshd.service'),dict(container_name='--privileged'),dict(container_engine='docker')])
def test_invalid_engine_identity_is_atomic(product_client,product,fields):
    changed=body();changed.update(fields)
    assert product_client.post('/service/settings/haproxy',data=changed).status_code==400
    assert not ServiceSetting.select().where(ServiceSetting.server_id==11).exists()


def test_container_discovery_requires_actual_group_and_service_access(product_client,product,monkeypatch):
    seen=[]
    def discover(server,spec):
        seen.append((server.server_id,spec))
        return dict(version='podman version 5',cgroup_v2=True,containers=[dict(name='proxy-lab',image='example/proxy',running=True,unit='proxy-lab.service')])
    monkeypatch.setattr(container_settings,'discover',discover)
    response=product_client.get('/service/settings/haproxy/11/containers?engine=podman&owner=proxy')
    assert response.status_code==200,response.text
    assert seen==[(11,dict(engine='podman',owner='proxy',unit=''))]
    assert 'proxy-lab' in response.text
    UserGroups.update(user_role_id=2).where(UserGroups.user_id==product.admin.user_id).execute()
    assert product_client.get('/service/settings/haproxy/22/containers?engine=podman').status_code in (403,404)
    UserGroups.update(user_role_id=4).where(UserGroups.user_id==product.admin.user_id).execute()
    assert product_client.get('/service/settings/haproxy/11/containers?engine=podman').status_code==403
    assert len(seen)==1


def test_discovery_failure_does_not_disclose_host_output(product_client,product,monkeypatch):
    monkeypatch.setattr(container_settings,'discover',lambda *_:(_ for _ in ()).throw(RuntimeError('SECRET_HOST_ENV')))
    response=product_client.get('/service/settings/haproxy/11/containers?engine=podman')
    assert response.status_code==400 and 'SECRET_HOST_ENV' not in response.text


def test_operator_cannot_rebind_a_service_to_an_arbitrary_container_owner(product_client,product):
    UserGroups.update(user_role_id=3).where(UserGroups.user_id==product.admin.user_id).execute()
    response=product_client.post('/service/settings/haproxy',data=body())
    assert response.status_code==403
    assert not ServiceSetting.select().where(ServiceSetting.server_id==11).exists()
    assert product_client.get('/service/settings/haproxy/11/containers?engine=podman&owner=other').status_code==403


def test_operator_cannot_inspect_another_owners_startup_sources(product_client,product,monkeypatch):
    UserGroups.update(user_role_id=3).where(UserGroups.user_id==product.admin.user_id).execute()
    monkeypatch.setattr('app.modules.config.haproxy_files.discover_sources',lambda *_a,**_kw:pytest.fail('Another owner was inspected'))
    response=product_client.get('/service/settings/haproxy/11/sources?container_engine=podman&container_owner=other')
    assert response.status_code==403
