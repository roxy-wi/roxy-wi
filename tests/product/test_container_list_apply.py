import shlex
import json
import pytest
from flask import g
from app.modules.db.db_model import ServiceSetting,Server
from app.modules.config import add
from app.modules.service import certificates


def test_existing_list_gui_uses_each_nodes_selected_runtime_and_preserves_quoted_paths(product,app,monkeypatch):
    peer=Server.create(server_id=33,hostname='Native peer',ip='192.0.2.33',group_id='1',cred_id=11,haproxy=1)
    for name,value in dict(dockerized='1',container_engine='podman',container_owner='root',container_name='managed-proxy').items():
        ServiceSetting.create(server_id=11,service='haproxy',setting=name,value=value)
    directory=product.root/'lists/1/black';directory.mkdir(parents=True)
    monkeypatch.setattr(add.get_config,'get_config_var',lambda *_:str(product.root))
    monkeypatch.setattr(add.sql,'get_setting',lambda *args,**kwargs:'/srv/proxy config')
    monkeypatch.setattr(add.server_sql,'is_master',lambda _: [(peer.ip,)])
    calls=[];uploads=[]
    monkeypatch.setattr(add.server_mod,'ssh_command',lambda ip,command,**kwargs:calls.append((ip,command,kwargs)) or '')
    monkeypatch.setattr(add.config_mod,'upload',lambda *args:uploads.append(args))
    monkeypatch.setattr(add.roxywi_common,'logging',lambda *args,**kwargs:None)
    with app.test_request_context():
        g.user_params=dict(user_id=product.admin.user_id,group_id=1,role=1)
        assert 'error:' not in add.save_bwlist('source.lst','192.0.2.0/24\n','black','1',product.server.ip,'reload')
    assert len(uploads)==2 and (directory/'source.lst').read_text()=='192.0.2.0/24\n'
    mkdir=[shlex.split(command) for _,command,_ in calls if 'mkdir' in command]
    assert mkdir==[['sudo','mkdir','-p','--','/srv/proxy config/black']]*2
    applied=[(ip,command) for ip,command,kwargs in calls if kwargs.get('error_context')=='Cannot apply HAProxy list']
    assert applied[0][0]==product.server.ip
    envelope=json.loads(shlex.split(applied[0][1].removesuffix(' > /dev/null'))[-1])
    assert envelope['runtime']==dict(engine='podman',owner='root',unit='') and envelope['container']=='managed-proxy'
    assert envelope['action']=='haproxy-reload'
    assert applied[1][0]==peer.ip and 'systemctl reload' in applied[1][1]


def test_cross_group_slave_is_rejected_before_local_or_remote_list_write(product,app,monkeypatch):
    directory=product.root/'lists/1/black';directory.mkdir(parents=True)
    monkeypatch.setattr(add.get_config,'get_config_var',lambda *_:str(product.root))
    monkeypatch.setattr(add.server_sql,'is_master',lambda _: [(product.other.ip,)])
    monkeypatch.setattr(add.server_mod,'ssh_command',lambda *args,**kwargs:pytest.fail('Unauthorized remote write'))
    with app.test_request_context():
        g.user_params=dict(user_id=product.admin.user_id,group_id=1,role=1)
        with pytest.raises(Exception):add.save_bwlist('source.lst','192.0.2.0/24\n','black','1',product.server.ip,'reload')
    assert not (directory/'source.lst').exists()


def test_global_admin_may_explicitly_select_another_group_but_protected_operator_cannot_write(product,app,monkeypatch):
    directory=product.root/'lists/2/black';directory.mkdir(parents=True)
    monkeypatch.setattr(add.get_config,'get_config_var',lambda *_:str(product.root))
    monkeypatch.setattr(add.sql,'get_setting',lambda *args,**kwargs:'/srv/proxy')
    monkeypatch.setattr(add.server_sql,'is_master',lambda _:[])
    calls=[]
    monkeypatch.setattr(add.server_mod,'ssh_command',lambda *args,**kwargs:calls.append(args) or '')
    monkeypatch.setattr(add.config_mod,'upload',lambda *args:None)
    monkeypatch.setattr(add.roxywi_common,'logging',lambda *args,**kwargs:None)
    with app.test_request_context():
        g.user_params=dict(user_id=product.admin.user_id,group_id=1,role=1)
        assert 'success:' in add.save_bwlist('source.lst','192.0.2.0/24\n','black','2',product.other.ip,'save')
    assert (directory/'source.lst').exists() and calls
    calls.clear();Server.update(protected=1).where(Server.server_id==11).execute()
    with app.test_request_context():
        g.user_params=dict(user_id=product.admin.user_id,group_id=1,role=3)
        with pytest.raises(Exception):add.save_bwlist('source.lst','192.0.2.0/24\n','black','1',product.server.ip,'save')
    assert not calls
