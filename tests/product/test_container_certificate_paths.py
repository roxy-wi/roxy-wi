import pytest

from app.modules.db.db_model import ServiceSetting, UserGroups
from app.modules.service import certificates, container_settings


def test_managed_podman_certificates_use_the_mounted_service_directory(product,monkeypatch):
    ServiceSetting.create(server_id=11,service='haproxy',setting='certificate_directory',value='/var/lib/roxy-wi/certificates/haproxy')
    assert container_settings.certificate_directory(product.server,'haproxy')=='/var/lib/roxy-wi/certificates/haproxy'
    calls=[]
    monkeypatch.setattr(certificates,'remote',lambda server,data:calls.append(data) or {'stored':True})
    certificates.store_uploaded_file(product.server.ip,'test.crt','public chain',service='haproxy')
    assert calls[0]['cert_dir']=='/var/lib/roxy-wi/certificates/haproxy'


def test_upload_checks_every_target_and_protected_policy_before_writing(product_client,product,monkeypatch):
    product.server.protected=1;product.server.save()
    UserGroups.update(user_role_id=3).where(UserGroups.user_id==product.admin.user_id).execute()
    monkeypatch.setattr(certificates,'store_uploaded_file',lambda *_a,**_kw:pytest.fail('A protected target was written'))
    response=product_client.post('/service/haproxy/certificates/11/upload',json={'name':'test','cert':'public chain','cert_type':'crt'})
    assert response.status_code==403
    assert response.json['error_code']=='permission_denied'
    assert product_client.post('/service/haproxy/certificates/22/upload',json={'name':'test','cert':'public chain'}).status_code==404
