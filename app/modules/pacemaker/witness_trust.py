"""Move/rotate qnetd trust with host-local keys, public CSRs and fail-stop recovery."""
import base64
import hashlib
import json
from contextlib import ExitStack
from uuid import uuid4

from app.modules.pacemaker import service,witness_migration
from app.modules.pacemaker.remote import Remote
from app.modules.pacemaker.platforms import SOURCE
from app.modules.pacemaker.witness_docker import RUNTIME
from app.modules.pacemaker.witness_lifecycle import COMMON
from app.modules.roxywi.exception import RoxywiValidationError,RoxywiConflictError

# Shared atomic journal/backup helpers. Override lifecycle paths and recovery below.
BASE=SOURCE+RUNTIME+COMMON+r'''
import base64
TRUST=ROOT/'trust'
def folder(token):
    if not re.fullmatch(r'[0-9a-f]{32}',token):raise ValueError('Invalid trust migration identity')
    return TRUST/token
def timer(token):return 'roxywi-qnetd-trust-'+token
def host_snapshot(token=None):
    ensure_no_pending(token)
    if pathlib.Path('/etc/pve').exists():raise ValueError('A Proxmox host cannot be a witness')
    platform_profile()
    for unit in ('corosync','pacemaker'):
        if subprocess.run(['systemctl','is-active','--quiet',unit],capture_output=True).returncode==0:raise ValueError('Select an independent witness')
    container=container_state()
    if container:
        if not docker_status(container)['active']:raise ValueError('container witness must be active')
        root=DATA;args=[ENGINE,'exec',CONTAINER,'corosync-qnetd-tool','-l']
        mode=ENGINE;image=container['Image'];restart=container.get('HostConfig',{}).get('RestartPolicy',{}).get('Name') or 'no'
    else:
        if subprocess.run(['systemctl','is-active','--quiet','corosync-qnetd'],capture_output=True).returncode:raise ValueError('Native witness must be active')
        root=NATIVE;args=['corosync-qnetd-tool','-l'];mode='native';image=None;restart=None
        pid=int(command(['systemctl','show','corosync-qnetd','--property=MainPID','--value']))
        values=pathlib.Path('/proc/'+str(pid)+'/cmdline').read_bytes().decode().strip('\x00').split('\x00')
        if pathlib.Path(values[0]).name!='corosync-qnetd' or any(value not in ('-f',) for value in values[1:]):raise ValueError('Custom qnetd listener arguments require compatible settings before migration')
    text=command(args);clusters=sorted(set(re.findall(r'^Cluster "(.*)":',text,re.M)))
    if text.strip() and not clusters:raise ValueError('Cannot identify attached clusters')
    return dict(mode=mode,image_id=image,restart=restart,native_enabled=native_enabled(),
                ca_fingerprint=hashlib.sha256((root/'nssdb/qnetd-cacert.crt').read_bytes()).hexdigest(),
                database_digest=tree_digest(root),clusters=clusters)
def stop_host(state):
    if state['source']['mode'] in ('docker','podman'):
        command([ENGINE,'update','--restart=no',CONTAINER]);command([ENGINE,'stop','--time','20',CONTAINER])
    else:command(['systemctl','disable','--now','corosync-qnetd'])
def start_host(state):
    if state['source']['mode'] in ('docker','podman'):
        command([ENGINE,'update','--restart='+state['source']['restart'],CONTAINER]);command([ENGINE,'start',CONTAINER])
    else:
        command(['systemctl','enable' if state['source']['native_enabled'] else 'disable','corosync-qnetd']);command(['systemctl','start','corosync-qnetd'])
def host_recover(token,force=False):
    state=load(token)
    if state['phase'] in ('rolled-back','committed') and not force:return state
    if state['phase']=='prepared' and not force:
        state['phase']='rolled-back';save(token,state);return state
    # Remote target/source recovery deliberately leaves the listener stopped. The controller
    # must establish that the other arbiter is stopped before restoring the original source.
    stop_host(state)
    if state['role']=='rotation' and state.get('replaced'):
        root=DATA if state['source']['mode'] in ('docker','podman') else NATIVE
        if root.exists():shutil.rmtree(root)
        copy_state(folder(token)/'before',root);start_host(state)
    restore_receipt(state)
    state['phase']='rolled-back';save(token,state)
    subprocess.run(['systemctl','stop',timer(token)+'.timer'],capture_output=True,timeout=15)
    return state
'''
HOST_RECOVERY=BASE
HOST=BASE+'\nHOST_RECOVERY='+repr(HOST_RECOVERY)+r'''
def tool(state,args):
    stage=folder(state['token'])/'stage'
    if state['source']['mode'] in ('docker','podman'):
        return command([ENGINE,'run','--rm','--network','none','--read-only','--user','65532:65532','--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','corosync-qnetd-certutil','--volume',str(stage)+':/etc/corosync/qnetd:rw,Z',state['source']['image_id'],*args],timeout=120)
    installed=pathlib.Path(shutil.which('corosync-qnetd-certutil')).read_text()
    marker='CONFIG_DIR="/etc/corosync/qnetd"'
    if installed.count(marker)!=1:raise ValueError('Unsupported certificate utility layout')
    helper=folder(state['token'])/'certutil.sh';helper.write_text(installed.replace(marker,'CONFIG_DIR="'+str(stage)+'"'));helper.chmod(0o700)
    return command(['/bin/bash',str(helper),*args],timeout=120)
def prepare(data):
    token=data['token'];current=host_snapshot()
    if current!=data['source']:raise ValueError('Witness changed after review')
    directory=folder(token);directory.mkdir(parents=True,mode=0o700)
    state=dict(token=token,mode_before=json.loads((ROOT/'mode.json').read_text()) if (ROOT/'mode.json').exists() else None,source=current,role=data['role'],phase='prepared',context=data['context'],replaced=False)
    save(token,state)
    root=DATA if current['mode'] in ('docker','podman') else NATIVE
    copy_state(root,directory/'before')
    if tree_digest(root)!=current['database_digest'] or tree_digest(directory/'before')!=current['database_digest']:raise ValueError('Witness changed while taking its certificate backup')
    if data['role'] in ('target','rotation'):
        stage=directory/'stage'
        if data['role']=='rotation':
            stage.mkdir(mode=0o700)
            if current['mode'] in ('docker','podman'):os.chown(stage,65532,65532)
            tool(state,['-i'])
        else:copy_state(root,stage)
        state['target_ca']=hashlib.sha256((stage/'nssdb/qnetd-cacert.crt').read_bytes()).hexdigest();save(token,state)
    script=directory/'recover.py';script.write_text(HOST_RECOVERY+'\nlock=open("/run/lock/roxywi-qnetd.lock","a")\nfcntl.flock(lock,fcntl.LOCK_EX)\nhost_recover('+repr(token)+')\n');script.chmod(0o600)
    return state
def sign(data):
    state=load(data['token']);stage=folder(data['token'])/'stage'
    if state['phase']!='prepared' or state['role'] not in ('target','rotation'):raise ValueError('Trust target is not prepared')
    alias=data['alias']
    if not re.fullmatch(r'[a-z0-9-]{1,63}',alias):raise ValueError('Invalid certificate request identity')
    path=stage/('request-'+alias+'.crq');path.write_bytes(base64.b64decode(data['request'],validate=True));path.chmod(0o600)
    if state['source']['mode'] in ('docker','podman'):os.chown(path,65532,65532)
    request='/etc/corosync/qnetd/'+path.name if state['source']['mode'] in ('docker','podman') else str(path)
    tool(state,['-s','-c',request,'-n',alias]);path.unlink()
    return base64.b64encode((stage/'nssdb'/('cluster-'+alias+'.crt')).read_bytes()).decode()
os.umask(0o077)
lock=open('/run/lock/roxywi-qnetd.lock','a')
try:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);data=json.load(sys.stdin);action=data['action']
    if action=='snapshot':result=host_snapshot()
    elif action=='prepare':result=prepare(data)
    elif action=='state':result=load(data['token'])
    elif action=='recheck':
        state=load(data['token'])
        if state['phase']!='prepared' or host_snapshot(data['token'])!=state['source']:raise ValueError('Witness or connected clusters changed during certificate preparation')
        result=True
    elif action=='pending':result=[dict(json.loads(p.read_text()),token=p.parent.name) for p in sorted(TRUST.glob('*/state.json')) if json.loads(p.read_text())['phase'] not in ('committed','rolled-back')]
    elif action=='ca':
        state=load(data['token']);result=base64.b64encode((folder(data['token'])/'stage/nssdb/qnetd-cacert.crt').read_bytes()).decode()
    elif action=='sign':result=sign(data)
    elif action=='arm':
        state=load(data['token']);state['phase']='switching';save(data['token'],state)
        command(['systemd-run','--unit',timer(data['token']),'--on-active=180s','/usr/bin/python3',str(folder(data['token'])/'recover.py')]);result=state
    elif action=='stop':
        state=load(data['token']);state['phase']='switching';save(data['token'],state);stop_host(state);result=state
    elif action=='activate':
        state=load(data['token'])
        if state['phase']!='switching':raise ValueError('Target is not armed for switchover')
        root=DATA if state['source']['mode'] in ('docker','podman') else NATIVE
        if state['role']=='rotation':
            stop_host(state);state['replaced']=True;save(data['token'],state)
            shutil.rmtree(root);copy_state(folder(data['token'])/'stage',root)
            if state['source']['mode']=='native':
                import pwd
                user=command(['systemctl','show','corosync-qnetd','--property=User','--value']);account=pwd.getpwnam(user or 'root')
                for path in [root,*root.rglob('*')]:os.chown(path,account.pw_uid,account.pw_gid)
                if shutil.which('restorecon'):command(['restorecon','-R',str(root)])
        elif state['role']=='target':
            # Include locally signed certificates/serial state in the target's preserved CA DB.
            stop_host(state);shutil.rmtree(root);copy_state(folder(data['token'])/'stage',root)
        else:raise ValueError('Only a trust target can be activated')
        if state['source']['mode']=='native':
            import pwd
            user=command(['systemctl','show','corosync-qnetd','--property=User','--value']);account=pwd.getpwnam(user or 'root')
            for path in [root,*root.rglob('*')]:os.chown(path,account.pw_uid,account.pw_gid)
            if shutil.which('restorecon'):command(['restorecon','-R',str(root)])
        start_host(state);state['phase']='verifying';save(data['token'],state);result=state
    elif action in ('commit','complete','abort'):
        state=load(data['token'])
        if action=='commit' and state['phase'] not in ('switching','verifying'):raise ValueError('Witness is not awaiting verified commit')
        if action=='complete' and state['phase']!='finalizing':raise ValueError('Witness is not finalizing')
        if action=='abort' and state['phase']!='prepared':raise ValueError('Only preparation can be aborted without recovery')
        state['phase']='finalizing' if action in ('commit','complete') else 'rolled-back';save(data['token'],state)
        subprocess.run(['systemctl','stop',timer(data['token'])+'.timer'],capture_output=True,timeout=15)
        if action=='complete' and state['role'] in ('target','rotation'):
            root=DATA if state['source']['mode'] in ('docker','podman') else NATIVE
            receipt=ROOT/'mode.json'
            with tempfile.NamedTemporaryFile(mode='w',dir=ROOT,delete=False) as stream:
                path=pathlib.Path(stream.name)
                try:
                    json.dump(dict(mode=state['source']['mode'],trust=data['token'],ca_fingerprint=hashlib.sha256((root/'nssdb/qnetd-cacert.crt').read_bytes()).hexdigest()),stream);stream.flush();os.fsync(stream.fileno());path.chmod(0o600);os.replace(path,receipt)
                finally:path.unlink(missing_ok=True)
        if action=='complete':state['phase']='committed';save(data['token'],state)
        result=state
    elif action=='recover':result=host_recover(data['token'],data.get('force',False))
    elif action=='restore-source':
        state=load(data['token'])
        if state['role']!='source':raise ValueError('Wrong source journal')
        start_host(state);state['phase']='rolled-back';save(data['token'],state);result=state
    else:raise ValueError('Unknown trust action')
    print(json.dumps({'data':result}))
except ValueError as exc:print(json.dumps({'error':str(exc)}))
except BaseException:print(json.dumps({'error':'Trust migration host step failed; inspect its journal and use reviewed recovery'}))
'''

NODE_BASE=r'''
import base64,fcntl,hashlib,json,os,pathlib,re,shutil,subprocess,sys,tempfile
ROOT=pathlib.Path('/var/lib/roxy-wi/qdevice-trust')
NET=pathlib.Path('/etc/corosync/qdevice/net')
CONFIG=pathlib.Path('/etc/corosync/corosync.conf')
def command(args,timeout=30):return subprocess.run(args,capture_output=True,text=True,check=True,timeout=timeout).stdout.strip()
def folder(token):
    if not re.fullmatch(r'[0-9a-f]{32}',token):raise ValueError('Invalid trust migration identity')
    return ROOT/token
def load(token):return json.loads((folder(token)/'state.json').read_text())
def save(token,state):
    with tempfile.NamedTemporaryFile(mode='w',dir=folder(token),delete=False) as stream:
        path=pathlib.Path(stream.name)
        try:
            json.dump(state,stream);stream.flush();os.fsync(stream.fileno());path.chmod(0o600);os.replace(path,folder(token)/'state.json')
        finally:path.unlink(missing_ok=True)
def timer(token):return 'roxywi-qdevice-trust-'+token
def recover(token,force=False):
    state=load(token)
    if state['phase'] in ('rolled-back','committed') and not force:return state
    if state['phase']=='prepared':
        state['phase']='rolled-back';save(token,state);return state
    command(['systemctl','stop','corosync-qdevice'])
    if state.get('replaced'):
        if NET.exists():shutil.rmtree(NET)
        shutil.copytree(folder(token)/'before',NET,copy_function=shutil.copy2)
        stage=CONFIG.parent/('.trust-recover-'+token);stage.write_bytes((folder(token)/'before.conf').read_bytes());stage.chmod(0o600);os.replace(stage,CONFIG)
        if shutil.which('restorecon'):command(['restorecon','-R',str(NET),str(CONFIG)])
        command(['corosync-cfgtool','-R'])
    if state['rotation'] and state['active']:command(['systemctl','start','corosync-qdevice'])
    state['phase']='rolled-back';save(token,state)
    subprocess.run(['systemctl','stop',timer(token)+'.timer'],capture_output=True,timeout=15)
    return state
'''
NODE=NODE_BASE+'\nNODE_RECOVERY='+repr(NODE_BASE)+r'''
os.umask(0o077)
try:
    if pathlib.Path('/etc/pve').exists():raise ValueError('Refusing a Proxmox host')
    lock=open('/run/lock/roxywi-qdevice-trust.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    data=json.load(sys.stdin);token=data['token'];action=data['action'];directory=folder(token)
    if action=='prepare':
        if hashlib.sha256(CONFIG.read_bytes()).hexdigest()!=data['digest']:raise ValueError('Corosync configuration changed after review')
        directory.mkdir(parents=True,mode=0o700);shutil.copytree(NET,directory/'before');shutil.copy2(CONFIG,directory/'before.conf')
        candidate=directory/'candidate.conf';candidate.write_text(data['config']);candidate.chmod(0o600)
        command(['corosync','-t','-c',str(candidate)])
        state=dict(phase='prepared',rotation=data['rotation'],active=command(['systemctl','show','corosync-qdevice','--property=ActiveState','--value'])=='active',replaced=False)
        save(token,state)
        database=directory/'stage/nssdb';database.mkdir(parents=True,mode=0o700)
        password=database/'pwdfile.txt';password.write_text('');password.chmod(0o600)
        ca=directory/'ca.crt';ca.write_bytes(base64.b64decode(data['ca'],validate=True))
        noise=directory/'noise';noise.write_bytes(os.urandom(128))
        command(['certutil','-N','-d',str(database),'-f',str(password)])
        command(['certutil','-A','-d',str(database),'-f',str(password),'-t','CT,c,c','-n','QNet CA','-i',str(ca)])
        request=directory/'request.crq'
        command(['certutil','-R','-s','CN='+data['name'],'-o',str(request),'-d',str(database),'-f',str(password),'-z',str(noise),'-k','rsa','-g','3072'],timeout=120)
        script=directory/'recover.py';script.write_text(NODE_RECOVERY+'\nlock=open("/run/lock/roxywi-qdevice-trust.lock","a")\nfcntl.flock(lock,fcntl.LOCK_EX)\nrecover('+repr(token)+')\n');script.chmod(0o600)
        result=base64.b64encode(request.read_bytes()).decode()
    elif action=='certificate':
        state=load(token)
        if state['phase']!='prepared':raise ValueError('Client is not prepared')
        database=directory/'stage/nssdb';cert=directory/'client.crt';cert.write_bytes(base64.b64decode(data['cert'],validate=True))
        command(['certutil','-A','-d',str(database),'-f',str(database/'pwdfile.txt'),'-t','u,u,u','-n','Cluster Cert','-i',str(cert)])
        command(['certutil','-V','-d',str(database),'-n','Cluster Cert','-u','C'])
        # Retain the standard local PKCS12 file for future node enrollment; never send it to the controller.
        command(['pk12util','-d',str(database),'-o',str(database/'qdevice-net-node.p12'),'-W','','-n','Cluster Cert'])
        result=state
    elif action=='arm-stop':
        state=load(token);state['phase']='switching';save(token,state)
        command(['systemd-run','--unit',timer(token),'--on-active=195s','/usr/bin/python3',str(directory/'recover.py')])
        command(['systemctl','stop','corosync-qdevice']);result=state
    elif action=='switch':
        state=load(token)
        if state['phase']!='switching':raise ValueError('Client is not stopped for migration')
        state['replaced']=True;save(token,state)
        shutil.rmtree(NET);shutil.copytree(directory/'stage',NET)
        stage=CONFIG.parent/('.trust-new-'+token);shutil.copy2(directory/'candidate.conf',stage);os.replace(stage,CONFIG)
        if shutil.which('restorecon'):command(['restorecon','-R',str(NET),str(CONFIG)])
        result=state
    elif action=='start':command(['systemctl','start','corosync-qdevice']);result=load(token)
    elif action=='commit':
        state=load(token)
        if state['phase']!='switching':raise ValueError('Client recovery already ran; verify trust before retrying')
        state['phase']='committed';save(token,state)
        subprocess.run(['systemctl','stop',timer(token)+'.timer'],capture_output=True,timeout=15);result=state
    elif action=='recover':result=recover(token,data.get('force',False))
    elif action=='restore-client':
        state=load(token)
        if state['active']:command(['systemctl','start','corosync-qdevice'])
        result=state
    else:raise ValueError('Unknown client trust action')
    print(json.dumps({'data':result}))
except ValueError as exc:print(json.dumps({'error':str(exc)}))
except BaseException:print(json.dumps({'error':'Client trust migration step failed; inspect its journal and recover from the GUI'}))
'''


def call(server,action,*,node=False,**data):
    result=json.loads(Remote(server).run(['python3','-c',NODE if node else HOST],data=json.dumps(dict(action=action,**data)),timeout=240))
    if result.get('error'):raise RoxywiValidationError(result['error'])
    return result['data']


def plan(source_id,target_id,group_id,rotate=False):
    from app.modules.pacemaker.qdevice import witness_server
    from app.modules.pacemaker.corosync import read_all,fingerprint
    from app.modules.pacemaker.corosync_text import scalar
    source=witness_server(source_id,group_id);target=witness_server(target_id,group_id)
    if (source_id==target_id)!=rotate:raise RoxywiValidationError('Select another host for a move, or the same host for CA rotation')
    unfinished=call(source,'pending')
    if unfinished:return dict(server=source.hostname,eligible=False,pending=[dict(token=x['token'],phase=x['phase']) for x in unfinished])
    if not rotate and call(target,'pending'):raise RoxywiValidationError('Recover the target witness trust journal before another migration')
    before=call(source,'snapshot');after=before if rotate else call(target,'snapshot')
    if not rotate and after['clusters']:raise RoxywiValidationError('The target witness must have no connected clusters')
    clusters=witness_migration.attachments(source,group_id,before['clusters'])
    if not clusters:raise RoxywiValidationError('Attach and register the source cluster before migrating trust')
    if not rotate and witness_migration.attachments(target,group_id):raise RoxywiValidationError('The target is already assigned to a registered cluster')
    witness_migration.verify(clusters,source.ip)
    configs=[]
    for cluster in clusters:
        for member,server,text in read_all(cluster):
            if scalar(text,('quorum','device','net','host'))!=source.ip:raise RoxywiValidationError('Map the actual source witness before changing trust')
            if scalar(text,('quorum','device','net','tls')) not in ('required','on'):raise RoxywiValidationError('Mutual TLS is required for trust migration')
            configs.append(dict(cluster_id=cluster.id,name=cluster.name,server_id=member.server_id,ip=server.ip,port=server.port,cred_id=server.cred_id,digest=fingerprint(text)))
    data=dict(source_id=source_id,target_id=target_id,rotate=rotate,source=before,target=after,
              source_identity=dict(ip=source.ip,port=source.port,cred_id=source.cred_id),target_identity=dict(ip=target.ip,port=target.port,cred_id=target.cred_id),nodes=configs,
              clusters=[dict(id=c.id,name=c.name,members=c.servers) for c in clusters])
    return dict(data,server=source.hostname,target_server=target.hostname,eligible=True,pending=[],plan_digest=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest())


def recover(source_id,group_id,token):
    from app.modules.pacemaker.qdevice import witness_server
    from app.modules.pacemaker.adoption import server_for
    source=witness_server(source_id,group_id);state=call(source,'state',token=token)
    if state['phase'] in ('committed','rolled-back'):raise RoxywiValidationError('Trust migration is already finished; create a new reviewed plan')
    context=state['context'];target=witness_server(context['target_id'],group_id)
    if context['source_id']!=source_id:raise RoxywiValidationError('Recovery source does not match')
    for server,identity in [(source,context['source_identity']),(target,context['target_identity'])]:
        if dict(ip=server.ip,port=server.port,cred_id=server.cred_id)!=identity:raise RoxywiConflictError('A witness identity changed; restore its registered identity before recovery')
    clusters=witness_migration.attachments(source,group_id,[x['name'] for x in context['clusters']])
    nodes=[]
    for item in context['nodes']:
        server=server_for(item['server_id'],group_id)
        if dict(ip=server.ip,port=server.port,cred_id=server.cred_id)!={key:item[key] for key in ('ip','port','cred_id')}:raise RoxywiConflictError('A client identity changed before recovery')
        nodes.append(server)
    with ExitStack() as stack:
        for cluster in clusters:stack.enter_context(service.locked(cluster))
        # Reachability and a confirmed stopped target are mandatory before any source restart.
        call(target,'recover',token=token,force=True)
        for server in nodes:call(server,'recover',node=True,token=token,force=True)
        if not context['rotate']:call(source,'restore-source',token=token)
        for server in nodes:call(server,'restore-client',node=True,token=token)
        witness_migration.wait_verify(clusters,source.ip)
        from app.modules.db.db_model import PacemakerCluster
        with PacemakerCluster._meta.database.atomic():
            for cluster in clusters:
                cluster=service.get_cluster(cluster.id,group_id)
                settings=json.loads(cluster.corosync_settings);settings.pop('witness_pending',None);settings.update(qdevice_server_id=source_id,qdevice_host=source.ip)
                PacemakerCluster.update(corosync_settings=json.dumps(settings)).where(PacemakerCluster.id==cluster.id).execute()
    return dict(phase='rolled-back',token=token)


def execute(source_id,target_id,group_id,rotate,digest,user_id=0):
    from app.modules.pacemaker.qdevice import witness_server
    from app.modules.pacemaker.corosync import read_all
    from app.modules.pacemaker.corosync_text import scalar
    from app.modules.db.db_model import PacemakerCluster,InstallationTasks
    source=witness_server(source_id,group_id);target=witness_server(target_id,group_id)
    current=plan(source_id,target_id,group_id,rotate)
    if not current.get('eligible') or current['plan_digest']!=digest:raise RoxywiConflictError('Trust migration plan changed; review it again')
    clusters=witness_migration.attachments(source,group_id,current['source']['clusters']);token=uuid4().hex
    context={key:current[key] for key in ('source_id','target_id','rotate','source_identity','target_identity','clusters','nodes')}
    nodes=[];prepared_hosts=[];prepared_nodes=[];switching=False
    with ExitStack() as stack:
        locks=[(c,stack.enter_context(service.locked(c))) for c in clusters]
        for cluster,_lock in locks:
            if cluster.active_task_id:
                active=InstallationTasks.get_or_none(InstallationTasks.id==cluster.active_task_id)
                if active and active.status not in ('completed','failed'):raise RoxywiConflictError('An attached cluster operation is pending')
        try:
            for cluster in clusters:
                settings=json.loads(cluster.corosync_settings);settings['witness_pending']=dict(token=token,source_id=source_id,target_id=target_id)
                PacemakerCluster.update(corosync_settings=json.dumps(settings)).where(PacemakerCluster.id==cluster.id).execute()
            # Only public CA/CSRs/signed certificates cross SSH boundaries. Every private key stays on its host.
            if not rotate:
                prepared_hosts.append(source);call(source,'prepare',token=token,source=current['source'],role='source',context=context)
            prepared_hosts.append(target);call(target,'prepare',token=token,source=current['target'],role='rotation' if rotate else 'target',context=context)
            ca=call(target,'ca',token=token)
            for cluster in clusters:
                for member,server,text in read_all(cluster):
                    prepared_nodes.append(server)
                    config=text if rotate else scalar(text,('quorum','device','net','host'),target.ip)
                    item=next(x for x in current['nodes'] if x['server_id']==member.server_id)
                    request=call(server,'prepare',node=True,token=token,digest=item['digest'],config=config,rotation=rotate,ca=ca,name=cluster.name)
                    cert=call(target,'sign',token=token,request=request,alias=token+'-'+str(member.server_id))
                    call(server,'certificate',node=True,token=token,cert=cert);nodes.append(server)
                    for c,lock in locks:service.renew_lock(c,lock)
            witness_migration.verify(clusters,source.ip)
            call(source,'recheck',token=token)
            if not rotate:call(target,'recheck',token=token)
            switching=True
            # Stop every old client before the source can be retired or a new trust root activated.
            for server in nodes:call(server,'arm-stop',node=True,token=token)
            call(target,'arm',token=token)
            if not rotate:call(source,'stop',token=token)
            call(target,'activate',token=token)
            for server in nodes:call(server,'switch',node=True,token=token)
            for cluster in clusters:Remote(service.members(cluster)[0][1]).run(['corosync-cfgtool','-R'])
            for server in nodes:call(server,'start',node=True,token=token)
            witness_migration.wait_verify(clusters,target.ip)
            # Commit the source retirement first. An interrupted commit must not reactivate two arbiters.
            if not rotate:call(source,'commit',token=token)
            call(target,'commit',token=token)
            for server in nodes:call(server,'commit',node=True,token=token)
            for cluster in clusters:
                cluster=service.get_cluster(cluster.id,group_id)
                settings=json.loads(cluster.corosync_settings);settings.pop('witness_pending',None);settings.update(qdevice_server_id=target_id,qdevice_host=target.ip)
                PacemakerCluster.update(corosync_settings=json.dumps(settings)).where(PacemakerCluster.id==cluster.id).execute()
                service.event(cluster,user_id,'witness-ca-rotation' if rotate else 'witness-host-migration','completed')
            call(target,'complete',token=token)
            if not rotate:call(source,'complete',token=token)
            return dict(phase='committed',token=token,ca_fingerprint=hashlib.sha256(base64.b64decode(ca)).hexdigest())
        except Exception as failure:
            # Do not pretend to atomically undo distributed changes. Journals/timers leave a fail-stop
            # state if a host is unreachable; recovery first proves the new arbiter has stopped.
            if switching:raise RoxywiValidationError('Trust migration did not finish. Use Recover original trust; the target timer stops the new witness and clients restore their backups. The old remote witness remains stopped until reviewed recovery') from failure
            for server in prepared_nodes:
                try:call(server,'recover',node=True,token=token)
                except Exception:pass
            # Before switchover leave the original live source untouched. Mark prepared journals closed.
            for server in prepared_hosts:
                try:call(server,'abort',token=token)
                except Exception:pass
            for cluster in clusters:
                cluster=service.get_cluster(cluster.id,group_id);settings=json.loads(cluster.corosync_settings);settings.pop('witness_pending',None)
                PacemakerCluster.update(corosync_settings=json.dumps(settings)).where(PacemakerCluster.id==cluster.id).execute()
            raise RoxywiValidationError('Trust preparation failed before witness switchover; the original witness is still active') from failure
