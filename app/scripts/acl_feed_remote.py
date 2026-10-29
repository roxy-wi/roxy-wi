"""Standalone, journaled HAProxy IP-ACL transaction (no shell or service restart)."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import tempfile
import time
from uuid import UUID
import roxywi_config_candidate as candidate
import roxywi_certificate_remote as transport


def canonical(text):
    if not isinstance(text,str) or len(text.encode())>2*1024*1024:raise ValueError('ACL limit exceeded')
    values=set()
    for line in text.splitlines():
        value=line.split('#',1)[0].strip()
        if not value:continue
        values.add(str(ipaddress.ip_network(value,strict=False)))
        if len(values)>100000:raise ValueError('ACL entry limit exceeded')
    return '\n'.join(sorted(values))+'\n' if values else ''


def digest(value):return hashlib.sha256(value).hexdigest()


def safe_path(value,root):
    if not isinstance(value,str) or not re.fullmatch(r'/[A-Za-z0-9_./-]{1,4095}',value):raise ValueError('Unsupported ACL path')
    path=Path(value)
    if '..' in path.parts or path.is_symlink() or path.resolve()!=path or root not in path.parents or not path.is_file():
        raise ValueError('ACL must be a regular file below the managed configuration root')
    return path


def runtime(data,command):
    if data.get('_runtime_namespace'):
        return transport.haproxy_runtime.execute_runtime_command(data['_runtime_host'],int(data['transport']['runtime_port']),command,timeout=3,response_limit=8*1024*1024)
    host,port=transport.runtime_endpoint(data['transport'])
    return transport.haproxy_runtime.execute_runtime_command(host,port,command,timeout=3,response_limit=8*1024*1024)


def process_identity(data):
    if not data['transport'].get('docker'):
        process=transport.runtime_pid(data['transport'])
        value=Path('/proc',str(int(process)),'stat').read_text()
        return process+':'+value.rsplit(')',1)[1].split()[19]
    state=json.loads(transport.command(transport.runtime_argv(data['transport'],['inspect',data['transport']['container']]),'Inspect ACL runtime process'))[0]
    return digest(json.dumps(dict(id=state.get('Id',state.get('ID')),pid=state.get('State',{}).get('Pid'),started=state.get('State',{}).get('StartedAt')),sort_keys=True).encode())


def runtime_content(data,path,version=None):
    output=runtime(data,'show acl '+(('@'+str(version)+' ') if version is not None else '')+path)
    values=[]
    for line in output.splitlines():
        if not line.strip() or line.startswith('#'):continue
        match=re.fullmatch(r'0x[0-9a-fA-F]+\s+(.+)',line.strip())
        if not match:raise ValueError('Unexpected runtime ACL output')
        values.append(match[1])
    return canonical('\n'.join(values))


def inspect(data):
    spec=data['validation'];root=Path(data['root']).resolve();main=Path(spec['main']).resolve()
    validator=candidate._HaproxyValidator(dict(spec,action='reload'),main,main);validator.inspect()
    files=validator.files(False)
    if not files or len(files)>128:raise ValueError('Cannot establish bounded startup sources')
    texts=[];total=0;host_paths={};unsafe=set()
    for path in files:
        content=candidate._contents(path)
        if content is None:raise ValueError('Missing configuration source')
        total+=len(content)
        if total>2*1024*1024:raise ValueError('Configuration limit exceeded')
        texts.append((str(path),content.decode()))
    for _path,text in texts:
        for line in text.splitlines():
            try:tokens=shlex.split(line,comments=True)
            except ValueError:raise ValueError('Cannot parse configuration')
            if not tokens:continue
            for index,token in enumerate(tokens[:-1]):
                if token!='-f':continue
                value=tokens[index+1]
                ip_acl=tokens[0]=='acl' and len(tokens)>3 and tokens[2]=='src' and ('-m' not in tokens or tokens[tokens.index('-m')+1]=='ip')
                if not ip_acl:unsafe.add(value);continue
                if not re.fullmatch(r'/[A-Za-z0-9_./-]{1,4095}',value):continue
                if validator.container:
                    choices=[]
                    for mount in validator.mounts:
                        dest=Path(mount.get('Destination',''))
                        if not dest.is_absolute():continue
                        try:relative=Path(value).relative_to(dest)
                        except ValueError:continue
                        choices.append((len(dest.parts),Path(mount['Source'])/relative))
                    if not choices:continue
                    longest=max(length for length,_ in choices);matching={str(p) for length,p in choices if length==longest}
                    if len(matching)!=1:continue
                    host=Path(next(iter(matching)))
                else:host=Path(value)
                try:host=safe_path(str(host),root)
                except ValueError:continue
                if validator.container and candidate._container_path(host,validator.mounts,directory=True,writable=True,bind_only=True,aliases=True)!=value:
                    continue
                host_paths[str(host)]=value
        unsafe.update(re.findall(r'\bmap(?:_[a-z]+)?\(([^,)]+)',text))
    runtime_lists=runtime(data,'show acl')
    if not runtime_lists.startswith('#') or 'prepare acl' not in runtime(data,'help'):
        raise ValueError('HAProxy 2.4+ administrative Runtime API is required')
    process=transport.runtime_pid(data['transport'])
    result=[];list_bytes=0
    for host,value in host_paths.items():
        if value in unsafe:continue
        matches=[line for line in runtime_lists.splitlines() if re.match(r'^\d+\s+\('+re.escape(value)+r'\)',line)]
        if len(matches)!=1:continue
        original=Path(host).read_bytes();content=canonical(original.decode())
        list_bytes+=len(content.encode())
        if list_bytes>4*1024*1024:raise ValueError('Combined ACL inventory exceeds its size limit')
        if runtime_content(data,value)!=content:continue # Do not overwrite unpersisted manual runtime edits.
        result.append(dict(path=host,runtime_path=value,sha256=digest(original),content=content,entries=len(content.splitlines())))
    configuration=digest(json.dumps(texts,separators=(',',':')).encode())
    mounts=digest(json.dumps(validator.mounts,sort_keys=True,separators=(',',':')).encode())
    return validator,dict(lists=result,configuration=configuration,mounts=mounts,process=process,process_identity=process_identity(data))


def write_json(path,data):
    transport.private_file(path,json.dumps(data,sort_keys=True).encode())


def replace_runtime(data,path,content,process):
    if transport.runtime_pid(data['transport'])!=process:raise ValueError('HAProxy process changed')
    prepared=runtime(data,'prepare acl '+path)
    match=re.fullmatch(r'New version created:\s*(\d+)\s*',prepared.strip())
    if not match:raise ValueError('ACL transaction could not be prepared')
    version=int(match[1]);deadline=time.monotonic()+120
    for entry in content.splitlines():
        if runtime(data,'add acl @'+str(version)+' '+path+' '+entry).strip():raise ValueError('ACL entry was refused')
        if time.monotonic()>deadline:raise ValueError('ACL staging exceeded its time limit')
    if runtime_content(data,path,version)!=content:raise ValueError('Staged ACL differs from the candidate')
    if transport.runtime_pid(data['transport'])!=process:raise ValueError('HAProxy process changed before commit')
    runtime(data,'commit acl @'+str(version)+' '+path)
    if runtime_content(data,path)!=content or transport.runtime_pid(data['transport'])!=process:
        raise ValueError('ACL runtime commit could not be verified')


def handle(data):
    os.umask(0o077)
    operation=data['operation']
    validator,found=inspect(data)
    if operation=='discover':
        return dict(lists=[{key:value for key,value in item.items() if key!='content'} for item in found['lists']],configuration=found['configuration'])
    root=Path(data['root']).resolve();path=safe_path(data['path'],root)
    selected=next((item for item in found['lists'] if item['path']==str(path)),None)
    # Recovery must tolerate the deliberate disk/runtime difference after a lost
    # response; the immutable journal supplies the original inspected binding.
    transaction=str(UUID(data['transaction'])) if operation!='preview' else None
    journal=root/'.roxywi-acl-feeds'/transaction if transaction else None
    record=journal/'state.json' if journal else None
    if operation=='preview':
        if selected is None:raise ValueError('Select a persistent, currently loaded src IP ACL')
        return dict(selected,configuration=found['configuration'],mounts=found['mounts'],process=found['process'],process_identity=found['process_identity'])
    if operation not in ('prepare','apply','rollback','commit'):raise ValueError('Unsupported ACL operation')
    wanted=canonical(data['content'])
    if not wanted or wanted!=data['content']:raise ValueError('Candidate must be a canonical nonempty IP/CIDR list')
    if (root/'.roxywi-acl-feeds').is_symlink() or journal.is_symlink() or record.is_symlink():raise ValueError('Unsafe ACL journal')
    for directory in (root/'.roxywi-acl-feeds',journal):
        if directory.exists() and (not directory.is_dir() or directory.stat().st_uid!=os.geteuid() or directory.stat().st_mode&0o077):
            raise ValueError('ACL journal must be private to the helper owner')
    saved=json.loads(record.read_text()) if record.exists() else None
    expected=data['expected']
    if found['configuration']!=expected['configuration'] or found['mounts']!=expected['mounts']:
        raise ValueError('Configuration or container mounts changed since review')
    if operation not in ('rollback','commit') and found['process_identity']!=expected['process_identity']:raise ValueError('HAProxy process changed since review')
    if saved:
        if saved['path']!=str(path) or saved['digest']!=digest(wanted.encode()) or saved['expected']!=expected:
            raise ValueError('ACL transaction identity changed')
    elif operation in ('rollback','commit'):
        if operation=='commit':raise ValueError('Applied ACL journal is missing')
        if digest(path.read_bytes())!=expected['sha256'] or runtime_content(data,expected['runtime_path'])!=expected['content']:
            raise ValueError('No journal exists and the original ACL could not be verified')
        return dict(finished=True,state='unchanged')
    elif operation=='prepare':
        if selected is None or selected['sha256']!=expected['sha256'] or found['process']!=expected['process']:
            raise ValueError('ACL changed since review')
        journal.mkdir(parents=True,exist_ok=True,mode=0o700)
        (root/'.roxywi-acl-feeds').chmod(0o700)
        if (journal/'previous').exists() or (journal/'previous').is_symlink():raise ValueError('Unconfirmed ACL backup already exists')
        candidate._copy(path,journal/'previous')
        saved=dict(path=str(path),digest=digest(wanted.encode()),expected=expected,state='prepared')
        write_json(record,saved)
    else:raise ValueError('Prepare the reviewed ACL before applying')
    if operation=='prepare':return dict(prepared=True)
    current=digest(path.read_bytes());before=digest((journal/'previous').read_bytes()) if (journal/'previous').exists() else None
    if saved['state']=='committed':
        if current!=saved['digest'] or runtime_content(data,expected['runtime_path'])!=wanted:raise ValueError('Committed ACL drifted')
        if operation=='rollback':raise ValueError('A committed version requires a newly reviewed rollback')
        return dict(finished=True,state='committed')
    if current not in (before,saved['digest']):raise ValueError('ACL changed outside this transaction')
    live=runtime_content(data,expected['runtime_path'])
    original_content=canonical((journal/'previous').read_text()) if (journal/'previous').exists() else None
    if live not in (original_content,wanted):raise ValueError('Runtime ACL changed outside this transaction')
    if operation=='commit':
        if saved['state']!='applied' or current!=saved['digest'] or runtime_content(data,expected['runtime_path'])!=wanted:
            raise ValueError('ACL application is not verified')
        saved['state']='committed';write_json(record,saved)
        (journal/'previous').unlink(missing_ok=True)
        return dict(finished=True,state='committed')
    content=(journal/'previous').read_bytes() if operation=='rollback' else wanted.encode()
    saved['state']='rolling-back' if operation=='rollback' else 'applying';write_json(record,saved)
    transport.private_file(path,content,metadata=dict(mode=(journal/'previous').stat().st_mode&0o7777,uid=(journal/'previous').stat().st_uid,gid=(journal/'previous').stat().st_gid))
    # The complete loaded -f tree must still parse before the runtime transaction.
    if not validator.validate():raise ValueError('Full HAProxy configuration validation failed')
    canonical_content=canonical(content.decode())
    if live!=canonical_content:replace_runtime(data,expected['runtime_path'],canonical_content,found['process'])
    if process_identity(data)!=found['process_identity']:raise ValueError('HAProxy process changed during ACL apply')
    if path.read_bytes()!=content:raise ValueError('ACL file changed during apply')
    saved['state']='rolled-back' if operation=='rollback' else 'applied';write_json(record,saved)
    return dict(applied=operation=='apply',finished=operation=='rollback',state=saved['state'])


def main():
    import sys
    try:
        data=globals().get('_ROXYWI_ACL_DATA')
        if data is None:data=json.load(sys.stdin)
        selected=data.get('transport',{})
        if selected.get('docker') and selected.get('container_runtime',{}).get('owner','root')!='root' and not data.get('_runtime_namespace'):
            # Pin the network namespace once for the whole transaction, rather
            # than spawning nsenter/Python for every entry in a large feed.
            source=globals().get('source')
            if not isinstance(source,bytes):raise ValueError('Rootless ACL operation requires its framed helper source')
            data['_runtime_host']=transport.runtime_endpoint(selected)[0];data['_runtime_namespace']=True
            bootstrap='import json,sys\nd=json.load(sys.stdin)\nexec(compile(d["source"],"roxywi-acl-helper","exec"),{"__name__":"__main__","_ROXYWI_ACL_DATA":d["request"]})\n'
            output=transport.container_runtime.in_network(selected['container_runtime'],selected['container'],bootstrap,
                dict(source=source.decode(),request=data),timeout=225)
            print(json.dumps(json.loads(output)));return
        if data.get('_runtime_namespace'):
            transport.runtime_request=lambda _settings,command:runtime(data,command)
        with transport.configuration_lock():result=handle(data)
        print(json.dumps(result))
    except Exception:
        print(json.dumps(dict(error='ACL transaction could not be verified; retain the journal and use recovery')))


if __name__=='__main__':main()
