"""Reviewed Docker qnetd image refresh and conversion back to a native service."""
import hashlib
import json
from contextlib import ExitStack
from uuid import uuid4

from app.modules.pacemaker.platforms import SOURCE
from app.modules.pacemaker.remote import Remote
from app.modules.pacemaker.witness_docker import RUNTIME
from app.modules.pacemaker import service, witness_migration
from app.modules.roxywi.exception import RoxywiValidationError, RoxywiConflictError

COMMON = r'''
import fcntl, re, stat
NATIVE=pathlib.Path('/etc/corosync/qnetd')
def folder(token):
    if not re.fullmatch(r'[0-9a-f]{32}',token):raise ValueError('Invalid lifecycle identity')
    return ROOT/'lifecycle'/token
def save(token,state):
    path=folder(token)/'state.json'
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as stream:
        stage=pathlib.Path(stream.name)
        try:
            json.dump(state,stream);stream.flush();os.fsync(stream.fileno());stage.chmod(0o600);os.replace(stage,path)
        finally:stage.unlink(missing_ok=True)
def restore_receipt(state):
    if 'mode_before' not in state:return
    path=ROOT/'mode.json'
    if state['mode_before'] is None:path.unlink(missing_ok=True);return
    with tempfile.NamedTemporaryFile(mode='w',dir=ROOT,delete=False) as stream:
        stage=pathlib.Path(stream.name)
        try:
            json.dump(state['mode_before'],stream);stream.flush();os.fsync(stream.fileno());stage.chmod(0o600);os.replace(stage,path)
        finally:stage.unlink(missing_ok=True)
def load(token):return json.loads((folder(token)/'state.json').read_text())
def tree_digest(root):
    digest=hashlib.sha256();total=0
    paths=sorted(root.rglob('*'))
    if len(paths)>1000:raise ValueError('Unexpectedly large certificate directory')
    for path in paths:
        metadata=path.lstat()
        if path.is_symlink() or not (path.is_file() or path.is_dir()):raise ValueError('Unsupported certificate storage')
        digest.update(str(path.relative_to(root)).encode());digest.update(str((stat.S_IMODE(metadata.st_mode),metadata.st_uid,metadata.st_gid)).encode())
        if path.is_file():
            total+=metadata.st_size
            if total>32*1024*1024:raise ValueError('Unexpected certificate database size')
            digest.update(path.read_bytes())
    return digest.hexdigest()
def copy_state(source,destination):
    shutil.copytree(source,destination)
    for path in [source,*source.rglob('*')]:
        metadata=path.stat();os.chown(destination/path.relative_to(source),metadata.st_uid,metadata.st_gid)
def timer(token):return 'roxywi-qnetd-lifecycle-'+token
def native_enabled():
    value=subprocess.run(['systemctl','is-enabled','corosync-qnetd'],capture_output=True,text=True).stdout.strip()
    if value not in ('enabled','disabled','not-found',''):raise ValueError('Unsupported native service enablement')
    return value=='enabled'
def restore_enabled(state):
    subprocess.run(['systemctl','enable' if state['native_enabled'] else 'disable','corosync-qnetd'],capture_output=True,timeout=30,check=state['native_enabled'])
def pending():
    return [dict(token=p.parent.name,phase=s['phase'],operation=s['operation'],clusters=s.get('clusters',[]))
            for p in sorted((ROOT/'lifecycle').glob('*/state.json'))
            for s in [json.loads(p.read_text())] if s['phase'] not in ('committed','rolled-back')]
def snapshot(token=None):
    ensure_no_pending(token)
    if pathlib.Path('/etc/pve').exists():raise ValueError('Proxmox hosts are not witness targets')
    platform_profile()
    for unit in ('corosync','pacemaker','corosync-qnetd'):
        if subprocess.run(['systemctl','is-active','--quiet',unit],capture_output=True).returncode==0:raise ValueError('Select an independent running Docker witness with its native service stopped')
    state=container_state()
    if not state or not docker_status(state)['active']:raise ValueError('Select a running managed Docker witness')
    text=command(['docker','exec',CONTAINER,'corosync-qnetd-tool','-l'])
    clusters=sorted(set(re.findall(r'^Cluster "(.*)":',text,re.M)))
    if text.strip() and not clusters:raise ValueError('Cannot identify attached clusters')
    if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,62}',name) for name in clusters):raise ValueError('Unmanageable attached cluster name')
    return dict(mode='docker',image_id=state['Image'],version=docker_status(state)['version'],
                ca_fingerprint=hashlib.sha256(CERT.read_bytes()).hexdigest(),database_digest=tree_digest(DATA),
                native_digest=tree_digest(NATIVE) if NATIVE.exists() else None,native_enabled=native_enabled(),clusters=clusters)
def recover(token):
    state=load(token)
    if state['phase'] in ('committed','rolled-back'):return state
    try:
        names=command(['docker','ps','-a','--format','{{.Names}}']).splitlines()
        old_exists=state['old_container'] in names
        current=container_state()
        if not old_exists and current and current['Image']==state['image_id'] and current['Config']['Labels'].get('org.roxy-wi.migration')!=token:
            if state['operation']=='native' and state.get('backed_up'):
                if NATIVE.exists():shutil.rmtree(NATIVE)
                if (folder(token)/'native-before').exists():copy_state(folder(token)/'native-before',NATIVE)
            command(['docker','start',CONTAINER]);restore_enabled(state)
            restore_receipt(state)
            state['phase']='rolled-back';save(token,state)
            subprocess.run(['systemctl','stop',timer(token)+'.timer'],capture_output=True,timeout=15)
            return state
        if current:
            if current['Config']['Labels'].get('org.roxy-wi.migration')!=token:raise ValueError('Recovery refuses an unrelated container')
            command(['docker','rm','-f',CONTAINER])
        if state['operation']=='native':
            command(['systemctl','stop','corosync-qnetd'])
            if state.get('native_replaced'):
                if NATIVE.exists():shutil.rmtree(NATIVE)
                if (folder(token)/'native-before').exists():copy_state(folder(token)/'native-before',NATIVE)
            restore_enabled(state)
        if old_exists:
            if DATA.exists():shutil.rmtree(DATA)
            copy_state(folder(token)/'docker-before',DATA)
            command(['docker','rename',state['old_container'],CONTAINER])
            command(['docker','start',CONTAINER])
        restore_receipt(state)
        state['phase']='rolled-back';save(token,state)
        subprocess.run(['systemctl','stop',timer(token)+'.timer'],capture_output=True,timeout=15)
        return state
    except BaseException:
        state['phase']='recovery-required';save(token,state);raise
'''
RECOVER_CODE = SOURCE + RUNTIME + COMMON
HELPERS = r'''
def prepare(token,expected,operation):
    if operation not in ('native','image-upgrade'):raise ValueError('Unknown lifecycle operation')
    if pending():raise ValueError('Recover the unfinished witness operation first')
    current=snapshot()
    if current!=expected:raise ValueError('Witness changed; review a new plan')
    directory=folder(token);directory.mkdir(parents=True,mode=0o700)
    state=dict(current,mode_before=json.loads((ROOT/'mode.json').read_text()) if (ROOT/'mode.json').exists() else None,operation=operation,phase='preparing',old_container='roxywi-qnetd-before-'+token,switched=False,native_replaced=False)
    save(token,state)
    copy_state(DATA,directory/'docker-before')
    if NATIVE.exists():copy_state(NATIVE,directory/'native-before')
    state['backed_up']=True;save(token,state)
    recovery=directory/'recover.py'
    recovery.write_text(RECOVER_CODE+'\nlock=open("/run/lock/roxywi-qnetd.lock","a")\nfcntl.flock(lock,fcntl.LOCK_EX)\nrecover('+repr(token)+')\n');recovery.chmod(0o600)
    if operation=='native':
        # Package scripts must not start a second listener while the container is active.
        if pathlib.Path('/run/systemd/system/corosync-qnetd.service').exists():raise ValueError('An existing runtime unit must be inspected first')
        command(['systemctl','mask','--runtime','corosync-qnetd'])
        try:install_packages('witness')
        finally:
            command(['systemctl','unmask','--runtime','corosync-qnetd']);restore_enabled(state)
        # Package installation may initialize an unused native database. Restore the pre-install state.
        if NATIVE.exists():shutil.rmtree(NATIVE)
        if (directory/'native-before').exists():copy_state(directory/'native-before',NATIVE)
        probe=directory/'probe';copy_state(DATA,probe)
        command(['certutil','-d',str(probe/'nssdb'),'-L','-n','QNetd Cert'])
        command(['certutil','-d',str(probe/'nssdb'),'-K','-f',str(probe/'nssdb/pwdfile.txt')])
        state['candidate_version']=command(['dpkg-query','-W','-f=${Version}','corosync-qnetd']) if shutil.which('dpkg-query') else command(['rpm','-q','--qf','%{VERSION}-%{RELEASE}','corosync-qnetd'])
    else:
        # Always refresh the fixed in-repository recipe. Arbitrary images are never accepted.
        with tempfile.TemporaryDirectory(prefix='roxywi-qnetd-refresh-') as build:
            pathlib.Path(build,'Dockerfile').write_text(DOCKERFILE);pathlib.Path(build,'entrypoint').write_text(ENTRYPOINT)
            tag='roxywi-qnetd:refresh-'+token
            command(['docker','build','--pull','--no-cache','--label','org.roxy-wi.recipe='+RECIPE,'-t',tag,build],timeout=900)
        state['candidate_image']=json.loads(command(['docker','image','inspect',tag]))[0]['Id']
        state['candidate_version']=command(['docker','run','--rm','--network','none','--entrypoint','dpkg-query',state['candidate_image'],'-W','-f=${Version}','corosync-qnetd'])
        probe=directory/'probe';copy_state(DATA,probe)
        for path in [probe,*probe.rglob('*')]:os.chown(path,65532,65532)
        for args in (['-L','-n','QNetd Cert'],['-K','-f','/etc/corosync/qnetd/nssdb/pwdfile.txt']):
            command(['docker','run','--rm','--network','none','--read-only','--user','65532:65532','--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','certutil','--volume',str(probe)+':/etc/corosync/qnetd:rw,Z',state['candidate_image'],'-d','/etc/corosync/qnetd/nssdb',*args])
    if snapshot(token)!=expected:raise ValueError('Witness changed during preparation')
    state['phase']='prepared';save(token,state);return state

def switch(token):
    state=load(token)
    if state['phase']!='prepared':raise ValueError('Lifecycle operation is not prepared')
    now=snapshot(token)
    if any(state[key]!=value for key,value in now.items()):raise ValueError('Witness changed after preparation')
    state['phase']='switching';save(token,state)
    command(['systemd-run','--unit',timer(token),'--on-active=180s','/usr/bin/python3',str(folder(token)/'recover.py')])
    command(['docker','stop','--time','20',CONTAINER])
    command(['docker','rename',CONTAINER,state['old_container']])
    state['switched']=True;save(token,state)
    if state['operation']=='native':
        state['native_replaced']=True;save(token,state)
        if NATIVE.exists():shutil.rmtree(NATIVE)
        copy_state(DATA,NATIVE)
        import pwd
        user=command(['systemctl','show','corosync-qnetd','--property=User','--value'])
        account=pwd.getpwnam(user or 'root')
        for path in [NATIVE,*NATIVE.rglob('*')]:os.chown(path,account.pw_uid,account.pw_gid)
        if shutil.which('restorecon'):command(['restorecon','-R',str(NATIVE)])
        command(['systemctl','start','corosync-qnetd'])
    else:launch_docker(state['candidate_image'],migration=token)
    for _ in range(45):
        ready=subprocess.run(['corosync-qnetd-tool','-s'],capture_output=True).returncode==0 if state['operation']=='native' else bool(container_state() and docker_status(container_state())['active'])
        if ready:break
        time.sleep(1)
    else:raise ValueError('Candidate witness did not become ready')
    cert=(NATIVE/'nssdb/qnetd-cacert.crt') if state['operation']=='native' else CERT
    if hashlib.sha256(cert.read_bytes()).hexdigest()!=state['ca_fingerprint']:raise ValueError('Candidate CA differs')
    state['phase']='verifying';save(token,state);return state

def commit(token):
    state=load(token)
    if state['phase']!='verifying':raise ValueError('Operation is not awaiting verification')
    cert=NATIVE/'nssdb/qnetd-cacert.crt' if state['operation']=='native' else CERT
    if hashlib.sha256(cert.read_bytes()).hexdigest()!=state['ca_fingerprint']:raise ValueError('Witness CA changed before commit')
    if state['operation']=='native':
        command(['corosync-qnetd-tool','-s']);command(['systemctl','enable','corosync-qnetd'])
        mode='native'
    else:
        if not docker_status(container_state())['active']:raise ValueError('Candidate witness stopped')
        mode='docker'
        # Keep subsequent native-to-Docker conversions on the verified updated image.
        command(['docker','tag',state['candidate_image'],'roxywi-qnetd:'+RECIPE[:20]])
    if mode=='native' and DATA.exists():os.replace(DATA,folder(token)/'docker-retained')
    receipt=ROOT/'mode.json'
    with tempfile.NamedTemporaryFile(mode='w',dir=ROOT,delete=False) as stream:
        path=pathlib.Path(stream.name)
        try:
            json.dump(dict(mode=mode,lifecycle=token,ca_fingerprint=state['ca_fingerprint']),stream);stream.flush();os.fsync(stream.fileno());path.chmod(0o600);os.replace(path,receipt)
        finally:path.unlink(missing_ok=True)
    state['phase']='committed';save(token,state)
    subprocess.run(['systemctl','stop',timer(token)+'.timer'],capture_output=True,timeout=15)
    # Keep the stopped previous container, image and private snapshots for explicit recovery/audit.
    return state
'''
REMOTE = RECOVER_CODE + '\nRECOVER_CODE='+repr(RECOVER_CODE)+'\n'+HELPERS+r'''
os.umask(0o077)
lock=open('/run/lock/roxywi-qnetd.lock','a')
try:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    data=json.load(sys.stdin);action=data['action']
    if action=='plan':
        unfinished=pending();result={'pending':unfinished} if unfinished else {'pending':[],'source':snapshot()}
    elif action=='prepare':result=prepare(data['token'],data['source'],data['operation'])
    elif action=='switch':result=switch(data['token'])
    elif action=='commit':result=commit(data['token'])
    elif action=='recover':result=recover(data['token'])
    else:raise ValueError('Unknown witness lifecycle action')
    print(json.dumps({'data':result}))
except ValueError as exc:print(json.dumps({'error':str(exc)}))
except BaseException:print(json.dumps({'error':'Witness lifecycle step failed; read its journal and use Recover original witness'}))
'''


def call(server, action, **data):
    result=json.loads(Remote(server).run(['python3','-c',REMOTE],data=json.dumps(dict(action=action,**data)),timeout=1200))
    if result.get('error'):raise RoxywiValidationError(result['error'])
    return result['data']


def plan(server_id, group_id, operation):
    from app.modules.pacemaker.qdevice import witness_server
    if operation not in ('native','image-upgrade'):raise RoxywiValidationError('Unknown witness operation')
    server=witness_server(server_id,group_id);host=call(server,'plan')
    if host.get('pending'):
        for item in host['pending']:witness_migration.attachments(server,group_id,item['clusters'])
        return dict(server=server.hostname,pending=host['pending'],eligible=False)
    clusters=witness_migration.attachments(server,group_id,host['source']['clusters'])
    witness_migration.verify(clusters,server.ip)
    data=dict(operation=operation,source=host['source'],server_id=server_id,
              identity=dict(ip=server.ip,port=server.port,cred_id=server.cred_id),
              clusters=[dict(id=c.id,name=c.name,members=c.servers) for c in clusters])
    return dict(data,server=server.hostname,pending=[],eligible=True,plan_digest=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest())


def execute(server_id,group_id,operation,digest,user_id=0):
    from app.modules.pacemaker.qdevice import witness_server
    server=witness_server(server_id,group_id);current=plan(server_id,group_id,operation)
    if not current.get('eligible') or current['plan_digest']!=digest:raise RoxywiConflictError('Witness lifecycle plan changed; review it again')
    clusters=witness_migration.attachments(server,group_id,current['source']['clusters']);token=uuid4().hex
    with ExitStack() as stack:
        locks=[(c,stack.enter_context(service.locked(c))) for c in clusters]
        # Image preparation can take longer than a normal cluster action.
        from datetime import timedelta
        from app.modules.common.time import utc_now
        from app.modules.db.db_model import PacemakerCluster
        for cluster,lock in locks:
            if cluster.active_task_id:
                from app.modules.db.db_model import InstallationTasks
                active=InstallationTasks.get_or_none(InstallationTasks.id==cluster.active_task_id)
                if active and active.status not in ('completed','failed'):raise RoxywiConflictError('An attached cluster operation is pending')
            PacemakerCluster.update(lock_until=utc_now()+timedelta(minutes=25)).where((PacemakerCluster.id==cluster.id)&(PacemakerCluster.lock_token==lock)).execute()
        try:
            call(server,'prepare',token=token,source=current['source'],operation=operation)
            witness_migration.verify(clusters,server.ip)
            for c,lock in locks:service.renew_lock(c,lock)
            call(server,'switch',token=token)
            witness_migration.wait_verify(clusters,server.ip)
            result=call(server,'commit',token=token)
            for cluster in clusters:service.event(cluster,user_id,'witness-'+operation,'completed')
            return dict(phase=result['phase'],token=token,ca_fingerprint=result['ca_fingerprint'],version=result['candidate_version'])
        except Exception as failure:
            try:
                restored=call(server,'recover',token=token)
                if restored['phase']=='rolled-back':witness_migration.wait_verify(clusters,server.ip)
            except Exception:raise RoxywiValidationError('Witness operation failed; use Recover original witness and inspect every attached cluster') from failure
            raise RoxywiValidationError('Witness operation failed; original witness restored and node votes verified') from failure


def recover(server_id,group_id,token):
    from app.modules.pacemaker.qdevice import witness_server
    server=witness_server(server_id,group_id);host=call(server,'plan')
    entry=next((item for item in host.get('pending',[]) if item['token']==token),None)
    if not entry:raise RoxywiValidationError('No unfinished witness lifecycle operation with this identity')
    clusters=witness_migration.attachments(server,group_id,entry['clusters'])
    with ExitStack() as stack:
        for cluster in clusters:stack.enter_context(service.locked(cluster))
        result=call(server,'recover',token=token);witness_migration.wait_verify(clusters,server.ip)
    return dict(phase=result['phase'],token=token,ca_fingerprint=result['ca_fingerprint'])
