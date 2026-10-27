"""Explicit maintenance migration from adopted/custom Corosync to managed knet."""
import hashlib
import json
import re
import time
from uuid import uuid4
from app.modules.pacemaker import service,corosync
from app.modules.pacemaker.remote import Remote
from app.modules.pacemaker.schemas import CorosyncCandidate
from app.modules.pacemaker.xml import configuration
from app.modules.db.db_model import PacemakerCluster,Server
from app.modules.roxywi.exception import RoxywiValidationError,RoxywiConflictError

BASE=r'''
import fcntl,hashlib,json,os,pathlib,re,shutil,subprocess,sys,tempfile
ROOT=pathlib.Path('/var/lib/roxy-wi/transport')
CONFIG=pathlib.Path('/etc/corosync/corosync.conf')
def command(args,timeout=45):return subprocess.run(args,capture_output=True,text=True,check=True,timeout=timeout).stdout.strip()
def folder(token):
    if not re.fullmatch(r'[0-9a-f]{32}',token):raise ValueError('Invalid transport identity')
    return ROOT/token
def load(token):return json.loads((folder(token)/'state.json').read_text())
def save(token,state):
    with tempfile.NamedTemporaryFile(mode='w',dir=folder(token),delete=False) as stream:
        path=pathlib.Path(stream.name)
        try:
            json.dump(state,stream);stream.flush();os.fsync(stream.fileno());path.chmod(0o600);os.replace(path,folder(token)/'state.json')
        finally:path.unlink(missing_ok=True)
def timer(token):return 'roxywi-corosync-transport-'+token
def stop_cluster():
    units=['pacemaker','corosync']
    if command(['systemctl','show','corosync-qdevice','--property=LoadState','--value'])=='loaded':units.append('corosync-qdevice')
    command(['systemctl','stop',*units],timeout=90)
def recover(token,force=False):
    state=load(token)
    if state['phase'] in ('committed','rolled-back') and not force:return state
    stop_cluster()
    stage=CONFIG.parent/('.transport-restore-'+token);shutil.copy2(folder(token)/'before.conf',stage);os.replace(stage,CONFIG)
    if shutil.which('restorecon'):command(['restorecon',str(CONFIG)])
    command(['systemctl','start','corosync'])
    # Fail-stop: recovery timers never resume Pacemaker workloads. The web recovery
    # starts Pacemaker only after all original Corosync members are proven quorate.
    state['phase']='rolled-back';save(token,state)
    subprocess.run(['systemctl','stop',timer(token)+'.timer'],capture_output=True,timeout=15)
    return state
'''
REMOTE=BASE+'\nRECOVERY_CODE='+repr(BASE)+r'''
os.umask(0o077)
try:
    if pathlib.Path('/etc/pve').exists():raise ValueError('Refusing a Proxmox host')
    lock=open('/run/lock/roxywi-transport.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    data=json.load(sys.stdin);action=data['action']
    if action=='key':result=hashlib.sha256(pathlib.Path('/etc/corosync/authkey').read_bytes()).hexdigest()
    elif action=='validate':
        with tempfile.TemporaryDirectory(prefix='.roxywi-transport-',dir=CONFIG.parent) as temporary:
            path=pathlib.Path(temporary)/'candidate.conf';path.write_text(data['config']);path.chmod(0o600)
            command(['corosync','-t','-c',str(path)])
        result=True
    else:
        token=data['token'];directory=folder(token)
        if action=='prepare':
            if hashlib.sha256(CONFIG.read_bytes()).hexdigest()!=data['digest']:raise ValueError('Corosync changed after review')
            directory.mkdir(parents=True,mode=0o700);shutil.copy2(CONFIG,directory/'before.conf')
            candidate=directory/'candidate.conf';candidate.write_text(data['config']);candidate.chmod(0o600)
            command(['corosync','-t','-c',str(candidate)])
            state=dict(phase='prepared',digest=data['digest']);save(token,state)
            script=directory/'recover.py';script.write_text(RECOVERY_CODE+'\nlock=open("/run/lock/roxywi-transport.lock","a")\nfcntl.flock(lock,fcntl.LOCK_EX)\nrecover('+repr(token)+')\n');script.chmod(0o600);result=state
        elif action=='arm':
            state=load(token)
            if state['phase']!='prepared':raise ValueError('Transport is not prepared')
            state['phase']='armed';save(token,state)
            command(['systemd-run','--unit',timer(token),'--on-active=240s','/usr/bin/python3',str(directory/'recover.py')]);result=state
        elif action=='stop':stop_cluster();result=load(token)
        elif action=='switch':
            state=load(token)
            if state['phase']!='armed':raise ValueError('Transport recovery already ran')
            if command(['systemctl','show','pacemaker','--property=ActiveState','--value'])!='inactive':raise ValueError('Pacemaker must be stopped before changing transport')
            stage=CONFIG.parent/('.transport-new-'+token);shutil.copy2(directory/'candidate.conf',stage);os.replace(stage,CONFIG)
            if shutil.which('restorecon'):command(['restorecon',str(CONFIG)])
            state['phase']='verifying';save(token,state);result=state
        elif action=='commit':
            state=load(token)
            if state['phase']!='verifying':raise ValueError('Transport recovery already ran; inspect before committing')
            state['phase']='committed';save(token,state)
            subprocess.run(['systemctl','stop',timer(token)+'.timer'],capture_output=True,timeout=15);result=state
        elif action=='recover':result=recover(token,data.get('force',False))
        else:raise ValueError('Unknown transport action')
    print(json.dumps({'data':result}))
except ValueError as exc:print(json.dumps({'error':str(exc)}))
except BaseException:print(json.dumps({'error':'Transport step failed; use the reviewed GUI recovery and inspect the node journal'}))
'''


def call(server,action,**data):
    result=json.loads(Remote(server).run(['python3','-c',REMOTE],data=json.dumps(dict(action=action,**data)),timeout=150))
    if result.get('error'):raise RoxywiValidationError(result['error'])
    return result['data']


def safe_state(cluster,*,stopped=False):
    state=service.status(cluster);_remote,xml=service.connection(cluster);config=configuration(xml)
    if not state['quorate'] or any(n['online']!='true' or n['unclean']=='true' for n in state['nodes']):raise RoxywiValidationError('Every cluster member must be online, clean and quorate')
    properties={p.get('name'):p.get('value') for p in config.findall('./crm_config//nvpair')}
    if properties.get('stonith-enabled','true').lower() in ('false','0','off'):raise RoxywiValidationError('Keep fencing enabled before transport maintenance')
    if properties.get('maintenance-mode','false').lower() in ('true','1','on'):raise RoxywiValidationError('Exit maintenance mode so Pacemaker can stop resources cleanly')
    workloads=[r for r in state['resources'] if not (r['resource_agent'] or '').startswith('stonith:')]
    if any(r['managed']=='false' for r in workloads):raise RoxywiValidationError('Return unmanaged resources to Pacemaker before planned transport maintenance')
    if stopped and (any(n['standby']!='true' for n in state['nodes']) or any(r['active']=='true' or r['role'] not in ('Stopped',None) for r in workloads)):
        raise RoxywiValidationError('Quiesce all nodes and wait until every application resource is stopped before transport migration')
    return state


def plan(cluster,token=1500):
    from app.modules.pacemaker.corosync_text import scalar
    settings=json.loads(cluster.corosync_settings)
    if settings.get('witness_pending'):raise RoxywiConflictError('Recover the unfinished witness trust change before transport migration')
    if settings.get('transport_pending'):return dict(eligible=False,pending=settings['transport_pending'])
    safe_state(cluster)
    checked=service.members(cluster);existing=corosync.read_all(cluster)
    if len({text for _m,_s,text in existing})!=1:raise RoxywiValidationError('Reconcile Corosync drift across nodes before transport migration')
    previous=existing[0][2]
    if any(scalar(previous,('totem',key),optional=True) is not None for key in ('key','keyfile')):raise RoxywiValidationError('A custom authentication key location must be reconciled before managed transport migration')
    digests=[call(server,'key') for _m,server in checked]
    if len(set(digests))!=1:raise RoxywiValidationError('Existing Corosync authentication keys differ across nodes')
    witness_id=settings.get('qdevice_server_id')
    try:host=scalar(previous,('quorum','device','net','host'))
    except ValueError:
        if re.search(r'\bdevice\s*{',previous):raise RoxywiValidationError('Only an existing TLS net witness can be retained by the managed transport wizard')
        host=None
    if host:
        matches=list(Server.select().where((Server.group_id==str(cluster.group_id))&(Server.ip==host)&(Server.enabled==1)))
        if len(matches)!=1:raise RoxywiValidationError('Register the existing witness with its actual IP before migrating transport')
        witness_id=matches[0].server_id
        from app.modules.pacemaker.witness_docker import RUNTIME
        Remote(matches[0]).run(['python3','-c',RUNTIME+'\nensure_no_pending()'])
        if scalar(previous,('quorum','device','net','tls')) not in ('required','on'):raise RoxywiValidationError('The existing witness must require TLS')
        from app.modules.pacemaker.witness_migration import verify
        verify([cluster],host)
    body=CorosyncCandidate(name=cluster.name,members=[m for m,_s in checked],token=token,qdevice_server_id=witness_id)
    candidate=corosync.render(cluster,body,checked)
    for _m,server in checked:call(server,'validate',config=candidate)
    data=dict(cluster_id=cluster.id,members=cluster.servers,base_digest=corosync.fingerprint(previous),key_digest=digests[0],token=token,witness_id=witness_id,candidate=candidate)
    return dict(data,eligible=True,pending=None,previous=previous,plan_digest=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest())


def quiesce(cluster,user_id):
    with service.locked(cluster):
        state=safe_state(cluster);remote,_xml=service.connection(cluster);settings=json.loads(cluster.corosync_settings)
        if settings.get('transport_pending'):raise RoxywiConflictError('Recover the unfinished transport migration first')
        if 'transport_resume' not in settings:
            settings['transport_resume']=[n['name'] for n in state['nodes'] if n['standby']!='true']
            PacemakerCluster.update(corosync_settings=json.dumps(settings)).where(PacemakerCluster.id==cluster.id).execute()
        for member,_server in service.members(cluster):remote.run(['crm_standby','--node',member.name,'--update','on'])
        deadline=time.monotonic()+100
        while True:
            try:safe_state(cluster,stopped=True);break
            except RoxywiValidationError:
                if time.monotonic()>deadline:raise RoxywiValidationError('Resources did not stop cleanly. Inspect them in Resources; node standby is retained')
                time.sleep(2)
        service.event(cluster,user_id,'transport-quiesce','completed')


def resume(cluster,user_id):
    with service.locked(cluster):
        settings=json.loads(cluster.corosync_settings)
        if settings.get('transport_pending'):raise RoxywiConflictError('Recover the unfinished transport migration before resuming resources')
        safe_state(cluster);remote,_xml=service.connection(cluster)
        names=settings.get('transport_resume')
        if names is None:raise RoxywiValidationError('No transport maintenance standby changes are recorded')
        for member,_server in service.members(cluster):
            if member.name in names:remote.run(['crm_standby','--node',member.name,'--update','off'])
        settings.pop('transport_resume',None);PacemakerCluster.update(corosync_settings=json.dumps(settings)).where(PacemakerCluster.id==cluster.id).execute()
        service.event(cluster,user_id,'transport-resume','completed')


def start_members(cluster,witness):
    checked=service.members(cluster)
    for _m,server in checked:Remote(server).run(['systemctl','start','corosync'])
    if witness:
        for _m,server in checked:Remote(server).run(['systemctl','start','corosync-qdevice'])
    from app.modules.pacemaker.quorum import details
    deadline=time.monotonic()+65
    while True:
        try:
            for _m,server in checked:
                text=Remote(server).run(['env','LC_ALL=C','corosync-quorumtool','-s'],allowed=(0,2))
                if not re.search(r'^Quorate:\s+Yes',text,re.M) or not re.search(r'^Nodes:\s+'+str(len(checked))+r'\s*$',text,re.M):raise ValueError('Not every member has regained quorum')
            break
        except Exception:
            if time.monotonic()>deadline:raise RoxywiValidationError('Corosync has not regained quorum; Pacemaker remains stopped until recovery')
            time.sleep(2)
    for _m,server in checked:Remote(server).run(['systemctl','start','pacemaker'])
    service.wait_ready(cluster)
    safe_state(cluster,stopped=True)


def recover(cluster,user_id):
    with service.locked(cluster):
        settings=json.loads(cluster.corosync_settings);pending=settings.get('transport_pending')
        if not pending:raise RoxywiValidationError('No unfinished transport migration exists')
        checked=service.members(cluster)
        if cluster.servers!=pending['members']:raise RoxywiConflictError('Membership changed; restore the recorded registration before recovery')
        identities={str(m.server_id):dict(ip=s.ip,port=s.port,cred_id=s.cred_id) for m,s in checked}
        if identities!=pending['identities']:raise RoxywiConflictError('A node identity changed before recovery')
        # Stop every Pacemaker instance before restoring any old transport file.
        for _m,server in checked:Remote(server).run(['systemctl','stop','pacemaker'],timeout=90)
        for _m,server in checked:call(server,'recover',token=pending['id'],force=True)
        start_members(cluster,pending['previous'].get('qdevice_server_id') or pending.get('witness_id'))
        previous=pending['previous'];previous['transport_resume']=settings.get('transport_resume',[])
        PacemakerCluster.update(corosync_settings=json.dumps(previous)).where(PacemakerCluster.id==cluster.id).execute()
        service.event(cluster,user_id,'transport-recovery','completed')


def execute(cluster,user_id,token,digest):
    with service.locked(cluster) as lease:
        current=plan(cluster,token)
        if not current.get('eligible') or current['plan_digest']!=digest:raise RoxywiConflictError('Transport migration plan changed; review it again')
        safe_state(cluster,stopped=True)
        checked=service.members(cluster);ident=uuid4().hex;settings=json.loads(cluster.corosync_settings)
        # Prepare/syntax-check every host before any service is stopped.
        for _m,server in checked:
            call(server,'prepare',token=ident,digest=current['base_digest'],config=current['candidate']);service.renew_lock(cluster,lease)
        pending=dict(id=ident,members=cluster.servers,previous=settings.copy(),witness_id=current['witness_id'],identities={str(m.server_id):dict(ip=s.ip,port=s.port,cred_id=s.cred_id) for m,s in checked})
        settings['transport_pending']=pending;PacemakerCluster.update(corosync_settings=json.dumps(settings)).where(PacemakerCluster.id==cluster.id).execute()
        try:
            for _m,server in checked:call(server,'arm',token=ident)
            for _m,server in checked:call(server,'stop',token=ident)
            for _m,server in checked:call(server,'switch',token=ident)
            start_members(cluster,current['witness_id'])
            if current['witness_id']:
                from app.modules.pacemaker.witness_migration import wait_verify
                witness=Server.get_by_id(current['witness_id']);wait_verify([cluster],witness.ip)
            for _m,server in checked:call(server,'commit',token=ident)
            settings.pop('transport_pending');settings.update(membership_managed=True,token=token,qdevice_server_id=current['witness_id'])
            PacemakerCluster.update(corosync_settings=json.dumps(settings)).where(PacemakerCluster.id==cluster.id).execute()
            service.event(cluster,user_id,'transport-migration','completed')
        except Exception as exc:raise RoxywiValidationError('Transport migration did not finish. Keep resources in standby and use Recover original transport; host timers restore Corosync while leaving Pacemaker stopped') from exc
