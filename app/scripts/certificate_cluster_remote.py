"""Stdlib ownership proof for cluster certificate operations on managed hosts."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import xml.etree.ElementTree as ET


try:
    import roxywi_container_runtime as runtime
    import roxywi_config_candidate as candidate
    import roxywi_haproxy_discovery as discovery
except ModuleNotFoundError:
    from app.modules.connectors import containers as runtime
    from app.modules.config import candidate,haproxy_discovery as discovery


def parse(text):
    if not isinstance(text,str) or len(text.encode())>1024*1024 or re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b',text,re.I):
        raise ValueError('Unsupported cluster XML')
    return ET.fromstring(text)


def configuration_digest(text):
    root=parse(text)
    configs=root.findall('configuration')
    if root.tag!='cib' or len(configs)!=1:raise ValueError('Expected one CIB configuration')
    canonical=ET.canonicalize(ET.tostring(configs[0],encoding='unicode'),strip_text=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def declaration(resource,config):
    indexed={node.get('id'):node for node in config.iter() if node.get('id')}
    template=indexed.get(resource.get('template'));attributes=dict(template.attrib) if template is not None else {}
    attributes.update(resource.attrib);parameters={}
    for origin in ([template,resource] if template is not None else [resource]):
        for group in origin.findall('./instance_attributes'):
            if group.get('id-ref'):group=indexed.get(group.get('id-ref'))
            if group is None or group.find('rule') is not None:raise ValueError('Conditional resource bindings cannot be staged automatically')
            parameters.update({value.get('name'):value.get('value') for value in group.findall('nvpair')})
    return dict(id=resource.get('id'),**{key:attributes.get(key,'') for key in ('class','provider','type')},parameters=parameters)


def role(state,resource_id,node):
    if state.tag!='pacemaker-result':raise ValueError('Unsupported cluster status')
    dc=state.find('./summary/current_dc')
    if dc is None or dc.get('with_quorum')!='true':raise ValueError('Cluster is not quorate')
    nodes=[value for value in state.findall('./nodes/node') if value.get('name')==node]
    if len(nodes)!=1 or nodes[0].get('online')!='true' or nodes[0].get('unclean')!='false' or nodes[0].get('maintenance','false')!='false':
        raise ValueError('Cluster node is not online, clean and managed')
    resources=[value for value in state.findall('./resources//resource') if re.sub(r':\d+$','',value.get('id',''))==resource_id]
    if not resources or any(value.get('managed')!='true' or value.get('failed')!='false' or value.get('blocked')!='false' for value in resources):
        raise ValueError('Proxy resource is not clean and managed')
    active=[value for value in resources if value.get('active')=='true']
    if not active:raise ValueError('At least one cluster proxy instance must remain active')
    own=any(any(n.get('name')==node for n in value.findall('node')) for value in active)
    return 'active' if own else 'passive'


def run(argv,*,allowed=(0,)):
    result=subprocess.run(argv,check=False,capture_output=True,text=True,timeout=20)
    if result.returncode not in allowed or len(result.stdout.encode())>1024*1024:raise ValueError('Cannot verify cluster ownership')
    return result.stdout


def verify(data,*,mode=None):
    proof=data.get('cluster_proof')
    if proof is None:return None
    xml=run(['cibadmin','--query'])
    if configuration_digest(xml)!=proof['cib']:raise ValueError('Cluster configuration changed')
    name=run(['corosync-cmapctl','totem.cluster_name']).strip().split(' = ',1)[-1]
    if name!=proof['cluster']:raise ValueError('Cluster identity changed')
    config=parse(xml).find('configuration')
    resource=next((value for value in config.findall('./resources//primitive') if value.get('id')==proof['declaration']['id']),None)
    if resource is None or declaration(resource,config)!=proof['declaration']:raise ValueError('Proxy binding changed')
    observed=role(parse(run(['crm_mon','--one-shot','--output-as=xml'],allowed=(0,1,2))),proof['declaration']['id'],proof['node'])
    if observed!=(mode or proof['mode']):raise ValueError('Proxy resource placement changed')
    return observed


def static_volumes(options):
    tokens=shlex.split(options or '');result=[];index=0
    while index<len(tokens):
        value=tokens[index]
        if value in ('-v','--volume'):
            index+=1
            if index>=len(tokens):raise ValueError('Invalid resource volume option')
            value=tokens[index]
        elif value.startswith('--volume='):value=value.split('=',1)[1]
        elif value.startswith('-v') and len(value)>2:value=value[2:]
        elif value.startswith(('--mount','--volumes-from')):raise ValueError('Use explicit static directory bind volumes for passive certificate staging')
        else:index+=1;continue
        parts=value.split(':')
        if len(parts)<2 or not Path(parts[0]).is_absolute() or not Path(parts[1]).is_absolute():raise ValueError('Resource volumes must be absolute static binds')
        result.append((str(Path(parts[0]).resolve()),parts[1]));index+=1
    return result


def container_record(data):
    result=subprocess.run(runtime.argv(data.get('container_runtime'),['inspect',data['container']]),check=False,capture_output=True,text=True,timeout=15)
    if len(result.stdout)>1024*1024:raise ValueError('Container inspection exceeds its limit')
    declared=data['cluster_proof']['declaration']
    if result.returncode:
        return declared_container(data) if declared['class']=='ocf' else quadlet_container(data)
    record=json.loads(result.stdout)[0]
    state=record.get('State',{})
    if state.get('Running') or int(state.get('Pid',0))!=0:raise ValueError('Passive proxy container is not stopped')
    if declared['class']=='ocf':
        if declared['type']!=data.get('container_runtime',{}).get('engine','docker') or data.get('container_runtime',{}).get('owner','root')!='root':
            raise ValueError('The resource must own this exact rootful OCI runtime')
        params=declared['parameters']
        if (params.get('name') or declared['id'])!=data['container']:raise ValueError('Resource container name differs')
        if params.get('image') not in (record.get('Image'),record.get('Config',{}).get('Image')):raise ValueError('Resource image differs from the stopped container')
        binds=static_volumes(params.get('run_opts',''))
        for mount in record.get('Mounts',[]):
            if mount.get('Type')=='bind' and (str(Path(mount['Source']).resolve()),mount['Destination']) not in binds:
                raise ValueError('Container bind mounts differ from the resource declaration')
        expected=declared_container(data)
        for key in ('Entrypoint','Cmd'):
            if (record.get('Config',{}).get(key) or [])!=(expected['Config'].get(key) or []):raise ValueError('Container startup command differs from its resource declaration')
        if record.get('Image')!=expected['Image']:raise ValueError('Container image changed from the resource declaration')
    else:
        values=quadlet_values(data)
        image=shlex.split((values.get('Image') or [''])[0])
        if len(image)!=1 or image[0] not in (record.get('Image'),record.get('Config',{}).get('Image')):raise ValueError('Quadlet image differs from the stopped container')
        if shlex.split((values.get('Exec') or [''])[0])!=(record.get('Config',{}).get('Cmd') or []):raise ValueError('Quadlet Exec differs from the stopped container')
        binds=[]
        for value in values.get('Volume',[]):binds.extend(static_volumes('--volume '+value))
        for mount in record.get('Mounts',[]):
            if mount.get('Type')=='bind' and (str(Path(mount['Source']).resolve()),mount['Destination']) not in binds:raise ValueError('Quadlet volumes changed')
        declared_env=[value for line in values.get('Environment',[]) for value in shlex.split(line)]
        if any(value not in record.get('Config',{}).get('Env',[]) for value in declared_env):raise ValueError('Quadlet environment changed')
    return record


def quadlet_values(data):
    spec=runtime.validate(data.get('container_runtime'))
    if spec['engine']!='podman' or spec['owner']!='root':raise ValueError('Passive Quadlet staging requires a rootful static unit')
    runtime.verify_unit(spec,data['container'])
    unit=spec['unit'];fields=dict(line.split('=',1) for line in run(['systemctl','show',unit,'--property=ActiveState,MainPID']).splitlines() if '=' in line)
    if fields.get('ActiveState') not in ('inactive','failed') or fields.get('MainPID')!='0':raise ValueError('The selected Quadlet unit must be stopped')
    source=run(['systemctl','show',unit,'--property=SourcePath','--value']).strip();file=Path(source)
    if file.is_symlink() or not file.is_file() or file.stat().st_size>65536:raise ValueError('Unsupported Quadlet definition')
    section=None;values={}
    for line in file.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith(('#',';')):continue
        if line.startswith('['):section=line;continue
        if section=='[Container]' and '=' in line:
            key,value=line.split('=',1)
            if value.endswith('\\') or '%' in value:raise ValueError('Use explicit static Quadlet values for passive staging')
            values.setdefault(key,[]).append(value)
    unsupported={'PodmanArgs','EnvironmentFile','Mount','Entrypoint','WorkingDir','Secret','VolumeFrom','Rootfs'}
    if any(values.get(key) for key in unsupported):raise ValueError('Passive Quadlet staging requires explicit static image, Exec and Volume fields')
    if any(value not in ('0','root') for key in ('User','Group') for value in values.get(key,[])):
        raise ValueError('Passive Quadlet staging requires a root HAProxy process inside the container')
    return values


def quadlet_container(data):
    values=quadlet_values(data)
    image=shlex.split((values.get('Image') or [''])[0])
    if len(image)!=1:raise ValueError('Quadlet requires one static image')
    options=[]
    for value in values.get('Volume',[]):options+=['--volume',value]
    for value in values.get('Environment',[]):
        for item in shlex.split(value):options+=['--env',item]
    declared=dict(data['cluster_proof']['declaration'],**{'class':'ocf','type':'podman'},parameters=dict(
        name=data['container'],image=image[0],run_opts=shlex.join(options),run_cmd=(values.get('Exec') or [''])[0]))
    return declared_container(dict(data,cluster_proof=dict(data['cluster_proof'],declaration=declared)))


def declared_container(data):
    """OCF OCI agents normally remove passive containers; never start one to inspect it."""
    declared=data['cluster_proof']['declaration'];spec=runtime.validate(data.get('container_runtime'))
    params=declared['parameters']
    if declared['class']!='ocf' or declared['type']!=spec['engine'] or spec['owner']!='root' or (params.get('name') or declared['id'])!=data['container']:
        raise ValueError('This resource does not own the selected rootful OCI binding')
    image=params.get('image','')
    result=subprocess.run(runtime.argv(spec,['image','inspect',image]),check=True,capture_output=True,text=True,timeout=15)
    if len(result.stdout)>1024*1024:raise ValueError('Image inspection exceeds its limit')
    info=json.loads(result.stdout)[0];image_id=info.get('Id',info.get('ID',''))
    if not re.fullmatch(r'(?:sha256:)?[a-f0-9]{64}',image_id):raise ValueError('Install the resource image on each node before staging')
    tokens=shlex.split(params.get('run_opts',''));options={};index=0
    flags={'-v','--volume','--network','--net','-p','--publish','--user','-u','--entrypoint','--env','-e','--label','-l','--hostname','--log-driver','--log-opt','--restart','--stop-timeout','--security-opt','--cap-add','--cap-drop','--ulimit'}
    while index<len(tokens):
        value=tokens[index];key,separator,argument=value.partition('=')
        if key in ('--read-only','--init') and not separator:index+=1;continue
        if value.startswith('-v') and len(value)>2:key='-v';argument=value[2:];separator='='
        if key not in flags:raise ValueError('Passive OCI staging requires explicit static bind-volume and direct HAProxy startup options')
        if not separator:
            index+=1
            if index>=len(tokens):raise ValueError('Incomplete OCI resource option')
            argument=tokens[index]
        options.setdefault(key,[]).append(argument);index+=1
    if any(value not in ('0','root','0:0') for value in options.get('--user',[])+options.get('-u',[])):
        raise ValueError('Passive OCI staging currently requires a root HAProxy process inside the container')
    binds=static_volumes(params.get('run_opts',''));mounts=[]
    for source,destination in binds:
        path=Path(source)
        if path.is_symlink() or not path.is_dir():raise ValueError('Certificate/configuration binds must be existing persistent directories')
        mounts.append(dict(Type='bind',Source=source,Destination=destination,RW=True))
    config=info.get('Config',{});entry=config.get('Entrypoint') or [];command=config.get('Cmd') or []
    if options.get('--entrypoint'):
        entry=shlex.split(options['--entrypoint'][-1])
        if len(entry)!=1 or Path(entry[0]).name!='haproxy':raise ValueError('Use a direct HAProxy entrypoint for passive staging')
    if params.get('run_cmd'):
        if any(value in params['run_cmd'] for value in ('$','`',';','|','&','\n','\r')):raise ValueError('Dynamic OCI startup commands cannot be staged automatically')
        command=shlex.split(params['run_cmd'])
    env=dict(value.split('=',1) for value in config.get('Env',[]) if '=' in value)
    for value in options.get('--env',[])+options.get('-e',[]):
        key,separator,text=value.partition('=')
        if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',key) or any(char in text for char in '\r\n\x00'):
            raise ValueError('Use explicit single-line environment values for passive staging')
        env[key]=text
    return dict(Image=image_id,Config=dict(Image=image,Entrypoint=entry,Cmd=command,Env=[key+'='+value for key,value in sorted(env.items())],WorkingDir=config.get('WorkingDir','')),
        Mounts=mounts,State=dict(Running=False,Pid=0),ProcessLabel='',_declared=True)


def context(data):
    verify(data,mode='passive')
    if not data.get('docker'):
        if data['cluster_proof']['declaration']['class']=='systemd':
            paths,_mounts,active=discovery.systemd_sources(data['service_unit'])
            if active:raise ValueError('The passive service already runs')
        else:paths=[data['config_path']]
        found=discovery.describe_sources(paths,[],data['root'],data['config_path'])
    else:
        record=container_record(data);config=record['Config'];entry=config.get('Entrypoint') or [];command=config.get('Cmd') or []
        argv=entry+command
        if entry and Path(entry[0]).name in ('docker-entrypoint.sh','docker-entrypoint'):
            argv=command
            if argv and argv[0].startswith('-'):argv=['haproxy',*argv]
        paths=discovery.sources_from_argv(argv,config.get('WorkingDir') or '/')
        found=discovery.describe_sources(paths,record.get('Mounts',[]),data['root'],data['config_path'],docker=True)
    return dict(service='haproxy',target=data['config_path'],main=data['config_path'],root=data['root'],candidate='',action='check',
        sources=[value['path'] for value in found['sources']],container=data['container'] if data.get('docker') else '',
        **({'container_runtime':data['container_runtime']} if data.get('container_runtime') else {}))


def stopped(data):
    verify(data,mode='passive')
    if not data.get('cluster_proof'):raise ValueError('Passive staging requires cluster ownership proof')
    if data.get('docker'):return container_record(data)
    declared=data['cluster_proof']['declaration']
    if declared['class']=='systemd':
        unit=data['service_unit']
        if declared['type'].removesuffix('.service')!=unit.removesuffix('.service'):raise ValueError('Proxy service unit differs')
        fields=dict(line.split('=',1) for line in run(['systemctl','show',unit,'--property=ActiveState,MainPID']).splitlines() if '=' in line)
        if fields.get('ActiveState') not in ('inactive','failed') or fields.get('MainPID')!='0':raise ValueError('Passive proxy unit is not stopped')
        sources,_mounts,active=discovery.systemd_sources(unit)
        if active or [str(Path(value).resolve()) for value in sources]!=[str(Path(value).resolve()) for value in data['validation']['sources']]:
            raise ValueError('Passive proxy startup sources changed')
    elif declared['class']!='ocf' or declared['type']!='haproxy':raise ValueError('Unsupported passive proxy agent')
    # Do not mistake an unmanaged native HAProxy for a safely stopped resource.
    pids=run(['pgrep','-x','haproxy'],allowed=(0,1)).split()
    if len(pids)>4096:raise ValueError('Too many native proxy processes')
    own_mount=os.readlink('/proc/self/ns/mnt')
    for pid in pids:
        try:
            if os.readlink('/proc/'+str(int(pid))+'/ns/mnt')!=own_mount:continue
            directory=os.readlink('/proc/'+str(int(pid))+'/cwd')
            sources=discovery.sources_from_argv(discovery.process_argv(int(pid)),directory)
            expected=[Path(value).resolve() for value in data['validation']['sources']]
            if any(Path(value).resolve()==wanted or wanted in Path(value).resolve().parents or Path(value).resolve() in wanted.parents for value in sources for wanted in expected):
                raise ValueError('The selected native HAProxy still runs on the passive node')
        except (FileNotFoundError,ProcessLookupError):continue
    return None


def validate_offline(data):
    record=stopped(data);spec=data['validation'];main=Path(spec['main']).resolve()
    validator=candidate._HaproxyValidator(dict(spec,action='check'),main,main)
    if record is not None:validator.mounts=record.get('Mounts',[])
    else:validator.inspect()
    files=validator.files(False)
    if not files or len(files)>128:raise ValueError('Cannot establish passive startup sources')
    if record is None:
        if not validator.validate():raise ValueError('Passive native HAProxy configuration is invalid')
    else:
        arguments=[]
        for source in spec['sources']:
            arguments+=['-f',candidate._container_path(Path(source),record.get('Mounts',[]),bind_only=True,aliases=True)]
        run_validator(data,record,arguments)
        if container_record(data)!=record:raise ValueError('Stopped container changed during offline validation')
    stopped(data)
    return True


def run_validator(data,record,arguments,extra_mounts=()):
    """Bounded, immutable-image syntax check; never starts the resource container."""
    image=record.get('Image','')
    if not re.fullmatch(r'(?:sha256:)?[a-f0-9]{64}',image):raise ValueError('Cannot identify the immutable proxy image')
    # Active rootful HAProxy can read configurations owned by the SSH account.
    # Keep host permissions intact; this one read capability is bounded by
    # the explicit read-only directory binds and an isolated network.
    args=['run','--rm','--network','none','--read-only','--cap-drop','ALL','--cap-add','DAC_READ_SEARCH',
          '--security-opt','no-new-privileges','--user','0']
    label=record.get('ProcessLabel','').split(':',3)
    if len(label)==4:
        if not re.fullmatch(r's\d+(?::c\d+(?:,c\d+)*)?',label[3]):raise ValueError('Unsupported container security label')
        args+=['--security-opt','label=level:'+label[3]]
    else:
        # This transient validator has no network or writable host mounts.
        # Do not relabel persistent resource files when the original no longer exists.
        args+=['--security-opt','label=disable']
    for mount in [*record.get('Mounts',[]),*extra_mounts]:
        source=Path(mount['Source']);destination=mount['Destination']
        if mount.get('Type')!='bind' or source.is_symlink() or not source.is_dir() or any(value in str(source)+destination for value in (',','\n','\r')):
            raise ValueError('Offline validation requires explicit static directory binds')
        args+=['--mount','type=bind,source='+str(source)+',destination='+destination+',readonly']
    working=record.get('Config',{}).get('WorkingDir')
    if working:args+=['--workdir',working]
    with tempfile.TemporaryDirectory(prefix='roxywi-validator-') as folder:
        file=Path(folder)/'environment'
        environment=record.get('Config',{}).get('Env',[])
        if any(any(char in value for char in ('\n','\r','\x00')) for value in environment):raise ValueError('Unsupported container environment')
        file.touch(mode=0o600);file.write_text('\n'.join(environment)+'\n')
        args+=['--env-file',str(file),'--entrypoint','haproxy',image,'-c',*arguments]
        result=subprocess.run(runtime.argv(data.get('container_runtime'),args),check=False,capture_output=True,timeout=60)
        if result.returncode:raise ValueError('Passive container configuration is invalid')
