import importlib.util
import io
import json
from pathlib import Path
import sys
import pytest
from app.modules.config import candidate
from app.scripts import certificate_remote


def test_rootless_acl_uses_one_verified_namespace_for_the_complete_framed_helper(monkeypatch,capsys):
    monkeypatch.setitem(sys.modules,'roxywi_config_candidate',candidate)
    monkeypatch.setitem(sys.modules,'roxywi_certificate_remote',certificate_remote)
    spec=importlib.util.spec_from_file_location('rootless_acl_helper',Path(certificate_remote.__file__).with_name('acl_feed_remote.py'))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    calls=[];source=b'# complete immutable framed helper source\n'
    monkeypatch.setattr(helper,'source',source,raising=False)
    monkeypatch.setattr(certificate_remote,'runtime_endpoint',lambda _ :('10.88.0.2',1999))
    def network(runtime,name,bootstrap,payload,**kwargs):
        calls.append((runtime,name,bootstrap,payload,kwargs));return '{"prepared":true}'
    monkeypatch.setattr(certificate_remote.container_runtime,'in_network',network)
    data=dict(operation='prepare',content='192.0.2.1/32\n192.0.2.2/32\n',transport=dict(docker=True,container='proxy',runtime_port=1999,container_runtime=dict(engine='podman',owner='proxy',unit='proxy.service')))
    monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps(data)))
    helper.main()
    assert json.loads(capsys.readouterr().out)==dict(prepared=True)
    assert len(calls)==1
    runtime,name,bootstrap,payload,options=calls[0]
    assert runtime['owner']=='proxy' and name=='proxy' and options['timeout']==225
    assert payload['source']==source.decode() and payload['request']['_runtime_namespace']
    assert payload['request']['_runtime_host']=='10.88.0.2' and payload['request']['content']==data['content']
    assert source.decode() not in bootstrap # large source travels on stdin, not argv
