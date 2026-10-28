import json
import stat
from pathlib import Path
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app.modules.roxywi.exception import RoxywiValidationError
from app.modules.pacemaker import exporter,service
from app.modules.pacemaker.schemas import ClusterCreate
from app.modules.db.db_model import Server
from app.modules.service import exporter_installation


@pytest.mark.parametrize('options',[
    {'listen_address':'127.0.0.1','port':'9664'},
    {'listen_address':'127.0.0.1','port':True},
    {'listen_address':'127.0.0.1','port':22},
    {'listen_address':'::1%evil\nUser=root'},
    {'listen_address':'localhost;id'},
    {'listen_address':'127.0.0.1','image':'arbitrary'},
])
def test_exporter_refuses_unreviewed_listener_inputs(options):
    with pytest.raises((ValidationError,RoxywiValidationError)):
        exporter.inventory('192.0.2.1',exporter.VERSION,options)


def test_exporter_release_and_arch_checksums_are_fixed():
    with pytest.raises(Exception,match='reviewed'):exporter.inventory('192.0.2.1','latest')
    inv,ips=exporter_installation.generate_exporter_inv('192.0.2.1',exporter.VERSION,'ha_cluster')
    data=inv['server']['hosts']['192.0.2.1']
    assert ips==['192.0.2.1'] and data['ha_cluster_exporter_port']==9664
    assert data['ha_cluster_exporter_listen_address']=='192.0.2.1'
    assert set(data['ha_cluster_exporter_checksums'])=={'amd64','arm64','ppc64le','s390x'}
    assert all(len(v)==64 for v in data['ha_cluster_exporter_checksums'].values())


@pytest.fixture
def cluster_node():
    nodes=[Server.create(hostname=f'exporter-node-{n}',ip=f'192.0.2.{210+n}',group_id='1') for n in (1,2)]
    cluster=service.register(ClusterCreate(name='exporter-test',members=[dict(server_id=s.server_id,name=s.hostname,address=s.ip,nodeid=n) for n,s in enumerate(nodes,1)]),1)
    yield nodes[0]
    cluster.delete_instance(recursive=True)
    for node in nodes:node.delete_instance()


def test_exporter_only_accepts_registered_nodes_in_the_active_group(cluster_node):
    assert exporter.member_server(cluster_node.ip,1).server_id==cluster_node.server_id
    with pytest.raises(Exception):exporter.member_server(cluster_node.ip,2)
    with pytest.raises(Exception):exporter.member_server('192.0.2.1',1)


def test_exporter_uses_job_scoped_public_host_key_pin(tmp_path,monkeypatch):
    from app.modules.server import ssh
    from app.modules.db import server
    monkeypatch.setattr(server,'get_server_by_ip',lambda _:SimpleNamespace(port=2222))
    key=SimpleNamespace(get_name=lambda:'ssh-ed25519',get_base64=lambda:'PUBLICKEYONLY')
    class Connection:
        ssh=SimpleNamespace(get_transport=lambda:SimpleNamespace(get_remote_server_key=lambda:key))
        def __enter__(self):return self
        def __exit__(self,*_):pass
    monkeypatch.setattr(ssh,'ssh_connect',lambda *_,**__:Connection())
    path=Path(exporter.pin_ansible_hosts(['192.0.2.1'],str(tmp_path)))
    assert path.read_text()=='[192.0.2.1]:2222 ssh-ed25519 PUBLICKEYONLY\n'
    assert stat.S_IMODE(path.stat().st_mode)==0o600


def test_exporter_api_passes_validated_options_to_the_existing_installer(cluster_node,client,authenticated,monkeypatch):
    import app.routes.install.routes as routes
    monkeypatch.setattr(routes.roxywi_common,'check_is_server_in_group',lambda _:True)
    calls=[]
    monkeypatch.setattr(routes.exp_installation,'install_exporter',lambda *args:calls.append(args) or 123)
    body={'server_ip':cluster_node.ip,'exporter_v':exporter.VERSION,'listen_address':cluster_node.ip,'port':9664}
    response=client.post('/install/exporter/ha_cluster',headers=authenticated[1],json=body)
    assert response.status_code==202 and calls[0][2]=='ha_cluster'
    assert calls[0][3]=={'listen_address':cluster_node.ip,'port':9664}
    authenticated[0]['role']=4
    assert client.post('/install/exporter/ha_cluster',headers=authenticated[1],json=body).status_code==403
