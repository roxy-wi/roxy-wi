"""Host-managed recovery of cluster daemons; never independently restart resources."""
import json
from typing import Literal
from pydantic import Field
from app.modules.pacemaker.schemas import StrictModel
from app.modules.pacemaker import service
from app.modules.pacemaker.remote import Remote
from app.modules.db.db_model import PacemakerCluster,Server
from app.modules.roxywi.exception import RoxywiValidationError

class Policy(StrictModel):
    policy: Literal['on-failure','no','default']
    coordinate_proxy_autostart: bool = Field(default=True,strict=True)
    confirm: str

SOURCE=r'''
import fcntl,hashlib,json,os,pathlib,subprocess,sys,tempfile
PREFIX='# Managed by Roxy-WI: cluster daemon recovery\n'
data=json.load(sys.stdin)
if pathlib.Path('/etc/pve').exists():raise SystemExit('Refusing to configure a Proxmox host')
def command(args):return subprocess.run(args,capture_output=True,text=True,check=True,timeout=30).stdout.strip()
def read():
    result=[]
    for unit in ('corosync','pacemaker','corosync-qdevice'):
        values=dict(line.split('=',1) for line in command(['systemctl','show',unit,'--property=LoadState,Restart,RestartUSec,ActiveState']).splitlines() if '=' in line)
        if values.get('LoadState')!='loaded':
            if unit!='corosync-qdevice':raise SystemExit('Required cluster unit unavailable')
            continue
        path=pathlib.Path('/etc/systemd/system')/(unit+'.service.d')/'90-roxywi-autostart.conf'
        text=path.read_text() if path.exists() else None
        if text is not None and not text.startswith(PREFIX):raise SystemExit('Unmanaged restart policy will not be overwritten')
        result.append({'unit':unit,'restart':values['Restart'],'delay':values['RestartUSec'],'active':values['ActiveState'],
                       'managed':text is not None,'source':text,'digest':hashlib.sha256((text or '').encode()).hexdigest()})
    return result
lock=open('/run/lock/roxywi-autostart.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
previous=read()
if data['action']=='read':print(json.dumps(previous));raise SystemExit(0)
if data['action'] not in ('set','restore'):raise SystemExit('Invalid restart-policy action')
policy=data.get('policy')
if data['action']=='set' and policy not in ('on-failure','no','default'):raise SystemExit('Invalid restart policy')
if data['action']=='set' and data['digests']!={item['unit']:item['digest'] for item in previous}:raise SystemExit('Restart policy changed after review')
try:
    for item in previous:
        path=pathlib.Path('/etc/systemd/system')/(item['unit']+'.service.d')/'90-roxywi-autostart.conf'
        text=next((old['source'] for old in data['previous'] if old['unit']==item['unit']),None) if data['action']=='restore' else None if policy=='default' else PREFIX+'[Unit]\nStartLimitIntervalSec=300\nStartLimitBurst=3\n[Service]\nRestart='+policy+'\nRestartSec=10s\n'
        if text is None:path.unlink(missing_ok=True);continue
        if not text.startswith(PREFIX):raise SystemExit('Invalid managed restart policy')
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False,prefix='.roxywi-') as stream:
            stage=pathlib.Path(stream.name)
            try:
                stream.write(text);stream.flush();os.fsync(stream.fileno());stage.chmod(0o644);os.replace(stage,path)
            finally:stage.unlink(missing_ok=True)
    command(['systemctl','daemon-reload'])
    result=read()
    if data['action']=='set' and policy!='default' and any(item['restart']!=policy for item in result):raise SystemExit('Effective restart policy differs')
    print(json.dumps(result))
except BaseException:
    # The controller restores the captured per-node policy after a failed/unknown write.
    raise
'''


def owned_services(xml):
    from app.modules.pacemaker.xml import configuration
    result=set()
    for resource in configuration(xml).findall('.//primitive'):
        kind=resource.get('class');name=resource.get('type','').lower().removesuffix('.service')
        if kind in ('systemd','ocf'):
            mapped={'haproxy':'haproxy','nginx':'nginx','apache':'apache','apache2':'apache','httpd':'apache','keepalived':'keepalived'}.get(name)
            if mapped:result.add(mapped)
    return result


def conflicts(cluster,xml=None):
    if xml is None:_remote,xml=service.connection(cluster)
    managed=owned_services(xml)
    return [{'server_id':member.server_id,'node':member.name,'service':name}
            for member,server in service.members(cluster) for name in sorted(managed)
            if bool(getattr(server,name+'_active',False))]


def assert_unmanaged(server_id,name):
    for cluster in PacemakerCluster.select():
        if server_id in [member['server_id'] for member in json.loads(cluster.servers)]:
            try:_remote,xml=service.connection(cluster)
            except Exception as exc:raise RoxywiValidationError('Cannot verify Pacemaker ownership; inspect the cluster before changing this service') from exc
            if name in owned_services(xml):raise RoxywiValidationError('This service is managed by Pacemaker; use its resource controls and leave proxy Auto Start disabled')


def read_node(server):
    return json.loads(Remote(server).run(['python3','-c',SOURCE],data=json.dumps({'action':'read'})))


def status(cluster):
    return {'nodes':[{'name':member.name,'units':read_node(server)} for member,server in service.members(cluster)],
            'proxy_conflicts':conflicts(cluster)}


def apply(cluster,user_id,data):
    request=Policy.model_validate(data)
    if request.confirm!=cluster.name:raise RoxywiValidationError('Type the cluster name to confirm the restart policy')
    with service.locked(cluster) as token:
        checked=service.members(cluster)
        before={member.server_id:read_node(server) for member,server in checked}
        overlap=conflicts(cluster)
        if overlap and not request.coordinate_proxy_autostart:raise RoxywiValidationError('Disable conflicting proxy Auto Start before assigning recovery to Pacemaker')
        attempted=[]
        try:
            for member,server in checked:
                service.renew_lock(cluster,token);attempted.append((member,server))
                Remote(server).run(['python3','-c',SOURCE],data=json.dumps({'action':'set','policy':request.policy,
                    'digests':{item['unit']:item['digest'] for item in before[member.server_id]}}))
            with PacemakerCluster._meta.database.atomic():
                for item in overlap:
                    Server.update(**{item['service']+'_active':0}).where(Server.server_id==item['server_id']).execute()
                settings=json.loads(cluster.corosync_settings);settings['autostart_policy']=request.policy
                PacemakerCluster.update(corosync_settings=json.dumps(settings)).where(PacemakerCluster.id==cluster.id).execute()
            service.event(cluster,user_id,'autostart-policy:'+request.policy,'completed')
        except Exception as failure:
            restored=True
            for member,server in reversed(attempted):
                try:Remote(server).run(['python3','-c',SOURCE],data=json.dumps({'action':'restore','previous':before[member.server_id]}))
                except Exception:restored=False
            raise RoxywiValidationError('Restart policy failed; previous settings restored' if restored else 'Restart policy outcome is uncertain; read every node policy before retrying') from failure
