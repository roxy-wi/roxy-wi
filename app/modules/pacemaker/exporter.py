"""Reviewed upstream HA Cluster Exporter release and read-only GUI diagnostics."""
import json
from ipaddress import ip_address
from pydantic import Field
from app.modules.pacemaker.schemas import StrictModel
from app.modules.roxywi.exception import RoxywiValidationError

VERSION='1.4.3'
# SHA-256 digests published by the upstream GitHub release API, reviewed 2026-10-27.
CHECKSUMS={
    'amd64':'2e41e086410b9724d05c74b9acbc2723697b8340552fa1a815661fcf4315487a',
    'arm64':'49cbc253cdfde03081ee540a697652b83312374b209fa7e37f6d8094b890c7f6',
    'ppc64le':'e4700ec729e826ddea9d3882bdb65d81e070fca729e40a06a5058e771829fcaa',
    's390x':'f514e37e839949bba0c6f44f7c3a5a434087c5c6491c308147584f870820906b',
}

class Options(StrictModel):
    listen_address: str
    port: int = Field(default=9664,ge=1024,le=65535,strict=True)


def member_server(server_ip,group_id):
    from app.modules.db.db_model import PacemakerCluster,Server
    from app.modules.pacemaker.adoption import server_for
    server=Server.get_or_none((Server.ip==server_ip)&(Server.group_id==str(group_id)))
    if not server: raise RoxywiValidationError('Select a registered cluster node in the active group')
    server=server_for(server.server_id,group_id)
    ids={item['server_id'] for cluster in PacemakerCluster.select().where(PacemakerCluster.group_id==group_id)
         for item in json.loads(cluster.servers)}
    if server.server_id not in ids: raise RoxywiValidationError('The HA Cluster Exporter belongs on a registered cluster node')
    return server


def inventory(server_ip,version,options=None):
    if version!=VERSION: raise RoxywiValidationError('Select a reviewed HA Cluster Exporter release')
    values=Options.model_validate(options or {'listen_address':server_ip})
    try:
        if '%' in values.listen_address: raise ValueError('Scoped listen addresses are not supported')
        address=str(ip_address(values.listen_address))
    except ValueError as exc: raise RoxywiValidationError('Exporter listen address must be an IP address') from exc
    return {'ha_cluster_exporter_version':VERSION,'ha_cluster_exporter_checksums':CHECKSUMS,
            'ha_cluster_exporter_listen_address':address,'ha_cluster_exporter_port':values.port,
            'service':'Corosync / Pacemaker exporter'}


STATUS = r'''
import ipaddress,json,pathlib,re,subprocess,urllib.request
config=pathlib.Path('/etc/roxy-wi/ha-cluster-exporter.json')
if not config.is_file():
    print(json.dumps({'installed':False}));raise SystemExit(0)
data=json.loads(config.read_text());address=str(ipaddress.ip_address(data['listen_address']));port=int(data['port'])
if not 1024<=port<=65535:raise SystemExit('Invalid exporter configuration')
request_host='127.0.0.1' if address=='0.0.0.0' else '::1' if address=='::' else address
if ':' in request_host:request_host='['+request_host+']'
version=subprocess.run(['/usr/local/bin/ha_cluster_exporter','--version'],capture_output=True,text=True,timeout=10)
result={'installed':True,'active':subprocess.run(['systemctl','is-active','--quiet','ha_cluster_exporter'],capture_output=True).returncode==0,
        'listen_address':address,'port':port,'version':(version.stdout+version.stderr).splitlines()[0]}
try:
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://'+request_host+':'+str(port)+'/metrics',timeout=20) as response:raw=response.read(2*1024*1024).decode()
    names=sorted({line.split('{',1)[0].split(' ',1)[0] for line in raw.splitlines() if line.startswith('ha_cluster_')})
    result.update(metrics_available=bool(names),pacemaker_available=any(name.startswith('ha_cluster_pacemaker_') for name in names),corosync_available=any(name.startswith('ha_cluster_corosync_') for name in names),metrics=names,samples=sum(1 for line in raw.splitlines() if line.startswith('ha_cluster_')))
except Exception:
    result.update(metrics_available=False,pacemaker_available=False,corosync_available=False,metrics=[],samples=0)
print(json.dumps(result))
'''


def status(server_ip,group_id):
    from app.modules.pacemaker.remote import Remote
    return json.loads(Remote(member_server(server_ip,group_id)).run(['python3','-c',STATUS],timeout=40))


def pin_ansible_hosts(server_ips,directory):
    """Pin the key from Roxy-WI's authenticated SSH connection for this one job."""
    import os,tempfile
    from app.modules.server.ssh import ssh_connect
    from app.modules.db.server import get_server_by_ip
    lines=[]
    for address in server_ips:
        server=get_server_by_ip(address)
        if any(char in address for char in ('\n','\r',' ')):raise RoxywiValidationError('Invalid SSH target name')
        with ssh_connect(address,connect_timeout=8,banner_timeout=15) as connection:
            key=connection.ssh.get_transport().get_remote_server_key()
            host=address if int(server.port)==22 else '['+address+']:'+str(int(server.port))
            lines.append(host+' '+key.get_name()+' '+key.get_base64())
    descriptor,path=tempfile.mkstemp(dir=directory,prefix='roxywi-exporter-hosts-',suffix='.pub')
    try:
        with os.fdopen(descriptor,'w') as stream:stream.write('\n'.join(lines)+'\n')
        os.chmod(path,0o600)
        return path
    except BaseException:
        try:os.unlink(path)
        except OSError:pass
        raise
