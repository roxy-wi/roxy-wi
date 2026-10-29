"""Journaled certificate staging on a proved passive Pacemaker member."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import tempfile

try:
    import roxywi_certificate_cluster as cluster
    import roxywi_config_candidate as candidate
except ModuleNotFoundError:
    from app.scripts import certificate_cluster_remote as cluster
    from app.modules.config import candidate


def digest(value):return hashlib.sha256(value).hexdigest()


def scope(data,transport):
    record=cluster.stopped(data)
    spec=data['validation'];main=Path(spec['main']).resolve()
    validator=candidate._HaproxyValidator(dict(spec,action='check'),main,main)
    if record is not None:validator.mounts=record.get('Mounts',[])
    else:validator.inspect()
    files=validator.files(False)
    if not files or len(files)>128:raise ValueError('Cannot establish passive configuration sources')
    contents=[];size=0
    for path in files:
        content=candidate._contents(path)
        if content is None:raise ValueError('A passive configuration source disappeared')
        size+=len(content)
        if size>2*1024*1024:raise ValueError('Passive configuration exceeds its limit')
        contents.append((str(path),content.decode()))
    material=dict(files=contents,mounts=validator.mounts,proof=data['cluster_proof']['cib'])
    if data.get('docker'):
        record=cluster.container_record(data)
        material['container']={key:record.get(key) for key in ('Image','Config','Mounts','ProcessLabel')}
    fingerprint=digest(json.dumps(material,sort_keys=True,separators=(',',':')).encode())
    if data.get('passive_binding') and data['passive_binding']!=fingerprint:raise ValueError('Passive configuration or runtime binding changed')
    return fingerprint,contents


def target(data,transport):
    selected=transport.creation_data(data)
    directory=transport.certificate_directory(selected)
    value=directory/data['pem_name']
    if Path(data['pem_name']).name!=data['pem_name'] or not data['pem_name'].endswith('.pem') or value.is_symlink():
        raise ValueError('Invalid passive PEM path')
    if data.get('docker'):
        record=cluster.container_record(data)
        candidate._container_path(value,record.get('Mounts',[]),directory=True,bind_only=True,aliases=True)
    return selected,value


def references(data,transport,contents,target):
    runtime_path=transport.certificate_runtime_path(dict(transport.creation_data(data),pem_name=target.name))
    destination=data.get('destination');crt_lists=[];direct=[];base=None
    for _name,text in contents:
        for line in text.splitlines():
            tokens=shlex.split(line,comments=True)
            if not tokens:continue
            if tokens[0]=='crt-base' and len(tokens)==2:base=tokens[1]
            for index,value in enumerate(tokens[:-1]):
                if value in ('crt','crt-list'):
                    path=tokens[index+1]
                    if '$' in path or not Path(path).is_absolute() and not base:raise ValueError('Passive SSL bindings require static absolute paths or crt-base')
                    path=str(Path(path) if Path(path).is_absolute() else Path(base)/path)
                    (crt_lists if value=='crt-list' else direct).append(path)
    if destination and destination['kind']=='directory':
        if destination['path'].rstrip('/') not in {value.rstrip('/') for value in direct}:raise ValueError('Passive certificate directory is not bound by the proxy configuration')
    elif destination and destination['kind']=='crt_list':
        if destination['path'] not in crt_lists:raise ValueError('Passive crt-list is not bound by the proxy configuration')
    else:
        if runtime_path not in direct and str(Path(runtime_path).parent) not in {value.rstrip('/') for value in direct}:
            included=False
            for path in crt_lists:
                file=transport.host_path(data,path)
                if file.is_symlink() or not file.is_file() or file.stat().st_size>1024*1024:raise ValueError('Unsupported passive crt-list')
                for line in file.read_text().splitlines():
                    values=shlex.split(line,comments=True)
                    if values and values[0]==runtime_path:included=True
            if not included:raise ValueError('The passive configuration does not reference this certificate')
    return runtime_path


def inspect(data,transport):
    binding,contents=scope(data,transport);selected,path=target(data,transport)
    references(data,transport,contents,path)
    if path.exists():
        if not path.is_file() or path.stat().st_size>1024*1024:raise ValueError('Unsupported passive certificate file')
        raw=path.read_bytes();leaf=re.search(rb'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',raw,re.S)
        item=dict(exists=True,revision=digest(raw),certificate=leaf.group(0).decode() if leaf else '')
    else:item=dict(exists=False,revision='0'*64,certificate='')
    if data.get('verify_passive_digest')==item['revision']:cluster.validate_offline(data)
    return dict(item,binding=binding,verification='disk-staged',can_stage=True)


def validate_material(data,pem,transport):
    # Check this PEM with the same installed binary before its atomic install.
    # This does not open a listening socket or start the managed service.
    with tempfile.TemporaryDirectory(prefix='roxywi-passive-material-') as folder:
        directory=Path(folder);certificate=directory/'candidate.pem';config=directory/'check.cfg'
        transport.private_file(certificate,pem.encode())
        material_path='/roxywi-material/candidate.pem' if data.get('docker') else str(certificate)
        transport.private_file(config,('global\n defaults\n  mode tcp\n  timeout connect 1s\n  timeout client 1s\n  timeout server 1s\n frontend verify_material\n  bind 127.0.0.1:10443 ssl crt '+material_path+'\n').encode())
        if data.get('docker'):
            cluster.run_validator(data,cluster.container_record(data),['-f','/roxywi-material/check.cfg'],
                [dict(Type='bind',Source=folder,Destination='/roxywi-material')])
        else:transport.command(['haproxy','-c','-f',str(config)],'Validate passive certificate material')


def deploy(data,transport):
    binding,contents=scope(data,transport);selected,path=target(data,transport)
    runtime_path=references(data,transport,contents,path);pem=data['pem'];wanted=digest(pem.encode())
    validate_material(data,pem,transport)
    _target,journal=transport.deployment_journal(selected)
    pending,previous,receipt=journal/'pending.json',journal/'previous.pem',journal/'applied'
    saved=json.loads(pending.read_text()) if pending.exists() else None
    actual=digest(path.read_bytes()) if path.exists() else '0'*64
    if saved:
        if saved.get('method')!='disk_stage' or saved.get('transaction')!=data.get('transaction') or saved.get('digest')!=wanted:
            raise ValueError('Another certificate transaction owns this journal')
        if actual not in (saved['old_digest'],wanted):raise ValueError('Passive PEM changed outside its transaction')
    else:
        if data.get('expected_revision') and data['expected_revision']!=actual:raise ValueError('Passive PEM changed after inspection')
        saved=dict(method='disk_stage',transaction=data.get('transaction'),digest=wanted,old_digest=actual,
            had_old=path.exists(),mode=0o600,uid=0,gid=0,binding=binding,cib=data['cluster_proof']['cib'],
            fingerprint=transport.pem_fingerprint(pem),old_fingerprint=transport.pem_fingerprint(path.read_text()) if path.exists() else '')
        try:cluster.validate_offline(data);saved['baseline_valid']=True
        except Exception:
            cluster.stopped(data);scope(dict(data,passive_binding=binding),transport);saved['baseline_valid']=False
        if path.exists():
            info=path.stat();saved.update(uid=info.st_uid,gid=info.st_gid,mode=info.st_mode&0o640)
            transport.private_file(previous,path.read_bytes())
        destination=data.get('destination')
        if destination and destination['kind']=='crt_list':
            file=transport.host_path(data,destination['path'])
            if file.is_symlink() or not file.is_file() or file.stat().st_size>1024*1024:raise ValueError('Unsupported passive crt-list')
            content=file.read_bytes();info=file.stat()
            existing=[shlex.split(line,comments=True) for line in content.decode().splitlines()]
            entry=shlex.quote(runtime_path)+'\n';new=content if any(values and values[0]==runtime_path for values in existing) else content.rstrip(b'\n')+b'\n'+entry.encode()
            saved['crt_list']=dict(path=str(file),old=digest(content),new=digest(new),content=new.decode(),uid=info.st_uid,gid=info.st_gid,mode=info.st_mode&0o777)
            transport.private_file(journal/'previous.crt-list',content)
        transport.private_file(pending,json.dumps(saved).encode())
    cluster.stopped(data)
    transport.private_file(path,pem.encode(),metadata=saved)
    if saved.get('crt_list'):
        item=saved['crt_list'];file=Path(item['path'])
        if digest(file.read_bytes()) not in (item['old'],item['new']):raise ValueError('Passive crt-list changed')
        transport.private_file(file,item['content'].encode(),metadata=item)
    cluster.validate_offline(data)
    scope(dict(data,passive_binding=binding),transport)
    if path.read_bytes()!=pem.encode():raise ValueError('Passive PEM changed during validation')
    transport.private_file(receipt,wanted.encode())
    return dict(deployed=True,verification='disk-staged',sha256=wanted)


def finish(data,transport,saved):
    selected,path=target(data,transport);_target,journal=transport.deployment_journal(selected)
    cluster.stopped(data);scope(dict(data,passive_binding=saved['binding']),transport)
    actual=digest(path.read_bytes()) if path.exists() else '0'*64
    if actual not in (saved['old_digest'],saved['digest']):raise ValueError('Passive certificate recovery found an unknown file')
    if data['operation']=='rollback':
        if saved['had_old']:transport.private_file(path,(journal/'previous.pem').read_bytes(),metadata=saved)
        elif path.exists():path.unlink()
        if saved.get('crt_list'):
            item=saved['crt_list'];file=Path(item['path'])
            if digest(file.read_bytes()) not in (item['old'],item['new']):raise ValueError('Passive crt-list changed outside its transaction')
            transport.private_file(file,(journal/'previous.crt-list').read_bytes(),metadata=item)
        if saved.get('baseline_valid',True):cluster.validate_offline(data)
        (journal/'applied').unlink(missing_ok=True)
    else:
        if saved.get('crt_list'):
            item=saved['crt_list'];file=Path(item['path'])
            if file.is_symlink() or digest(file.read_bytes())!=item['new']:raise ValueError('Passive crt-list changed before finalization')
        if actual!=saved['digest']:raise ValueError('Passive staged certificate is not the committed candidate')
        cluster.validate_offline(data)
    cluster.stopped(data)
    (journal/'pending.json').unlink()
    (journal/'previous.pem').unlink(missing_ok=True)
    (journal/'previous.crt-list').unlink(missing_ok=True)
    return dict(finished=True,verification='disk-staged')


def finish_inactive_runtime(data,transport,saved):
    """A failover can stop a node after its Runtime transaction was installed."""
    selected,path=target(data,transport);_target,journal=transport.deployment_journal(selected)
    cluster.stopped(data);scope(data,transport)
    if saved['method']=='runtime_create':
        transport.creation_disk_state(data,path,journal,saved,rollback=data['operation']=='rollback')
    else:
        actual=digest(path.read_bytes()) if path.exists() else '0'*64
        if actual not in (saved['old_digest'],saved['digest']):raise ValueError('Certificate changed after failover')
        if data['operation']=='rollback':transport.private_file(path,(journal/'previous.pem').read_bytes(),metadata=saved)
        elif actual!=saved['digest']:raise ValueError('Certificate candidate is not staged')
    cluster.validate_offline(data);cluster.stopped(data)
    if data['operation']=='rollback':(journal/'applied').unlink(missing_ok=True)
    (journal/'pending.json').unlink();(journal/'previous.pem').unlink(missing_ok=True);(journal/'previous.crt-list').unlink(missing_ok=True)
    return dict(finished=True,verification='disk-staged')


def finish_active_stage(data,transport,saved):
    """Recover a staged member that became active without starting/reloading it."""
    cluster.verify(data,mode='active')
    selected=transport.creation_data(data);path,journal=transport.deployment_journal(selected)
    if saved['had_old']:
        if saved.get('crt_list') and data['operation']=='rollback':
            raise ValueError('Use cluster maintenance before rolling back a newly activated crt-list entry')
        result=transport.finish_runtime(selected,path,journal,dict(saved,method='runtime'))
        (journal/'previous.crt-list').unlink(missing_ok=True)
        return dict(result,verification='runtime')
    if data.get('destination'):
        converted=dict(saved,method='runtime_create',destination=data['destination'])
        if saved.get('crt_list'):
            item=saved['crt_list'];converted.update(list_before=item['old'],list_after=item['new'],list_metadata=item)
        return transport.finish_creation(selected,path,journal,converted)
    if data['operation']=='commit':
        if digest(path.read_bytes())!=saved['digest'] or transport.runtime_certificate(selected)['fingerprint']!=saved['fingerprint']:
            raise ValueError('Activated certificate is not the staged candidate')
        transport.validate_configuration(selected);(journal/'pending.json').unlink();(journal/'previous.pem').unlink(missing_ok=True)
        return dict(finished=True,verification='runtime')
    raise ValueError('A newly activated certificate without an old file cannot be safely removed; use the cluster maintenance controls before rollback')
