"""Use the selected HAProxy/proxy namespace for managed-container operations."""
import json
from pathlib import Path
import requests

from flask import g, has_request_context

from app.modules.connectors import containers
from app.modules.db.db_model import Server
from app.modules.db import service as service_sql
from app.modules.pacemaker.remote import Remote
from app.modules.service import container_settings, haproxy_runtime


HTTP_PROBE = '''import base64,json,sys
from urllib.request import build_opener,HTTPRedirectHandler,ProxyHandler,Request
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
data=json.load(sys.stdin)
request=Request('http://127.0.0.1:'+str(int(data['port']))+'/'+data['path'].lstrip('/'),
    headers={'Authorization':'Basic '+base64.b64encode((data['user']+':'+data['password']).encode()).decode()})
with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=5) as response:
    value=response.read(1024*1024+1)
    if len(value)>1024*1024:raise ValueError('Statistics response exceeded its limit')
    print(value.decode(),end='')
'''


def managed_server(address):
    query = Server.select().where(Server.ip == str(address).strip('[]'))
    if has_request_context() and getattr(g, 'user_params', None) and int(g.user_params.get('role', 4)) != 1:
        query = query.where(Server.group_id == str(g.user_params['group_id']))
    matches = list(query.limit(2))
    if len(matches) != 1:
        raise ValueError('Select one registered server in the current group')
    return matches[0]


def namespace_probe(server, service, source, payload, *, timeout=20):
    data = dict(runtime=container_settings.runtime(server.server_id, service),
                name=container_settings.name(server.server_id, service), payload=payload)
    script = containers.embedded() + ('import json,sys\ndata=json.load(sys.stdin)\n'
        'print(module.in_network(data["runtime"],data["name"],'+repr(source)+',data["payload"]),end="")\n')
    return Remote(server).run(['python3', '-c', script], data=json.dumps(data), timeout=timeout)


def execute_runtime_command(server, port, command, **options):
    node = managed_server(server)
    if service_sql.select_service_setting(node.server_id, 'haproxy', 'dockerized') != '1':
        return haproxy_runtime.execute_runtime_command(server, port, command, **options)
    # Validate the same protocol envelope before crossing SSH. Private payloads
    # are handled by the separate certificate transport, never this stats path.
    if options.get('payload') is not None or not command or any(c in command for c in '\x00\r\n') or not 1 <= int(port) <= 65535:
        raise ValueError('Invalid managed Runtime API request')
    source = Path(haproxy_runtime.__file__).read_text() + '\nimport json,sys\nprint(execute_runtime_command(**json.load(sys.stdin)),end="")\n'
    data = dict(server='127.0.0.1', port=int(port), command=command, timeout=min(float(options.get('timeout', 5)), 10),
                response_limit=min(int(options.get('response_limit', 1024*1024)), 1024*1024))
    return namespace_probe(node, 'haproxy', source, data)


def http_stats(server, service, port, path, user, password):
    if service not in ('nginx', 'apache') or not 1 <= int(port) <= 65535 or any(c in path for c in '\x00\r\n'):
        raise ValueError('Invalid proxy statistics request')
    return namespace_probe(server, service, HTTP_PROBE, dict(port=int(port), path=path, user=user, password=password))


def statistics_response(address, service, port, path, user, password):
    server = managed_server(address)
    if service_sql.select_service_setting(server.server_id, service, 'dockerized') != '1':
        address = '[' + server.ip + ']' if ':' in server.ip else server.ip
        return requests.get('http://' + str(address) + ':' + str(int(port)) + '/' + path.lstrip('/'),
                            auth=(user, password), timeout=5, allow_redirects=False)
    text = http_stats(server, service, port, path, user, password)
    response = requests.Response()
    response.status_code, response.encoding = 200, 'utf-8'
    response._content = text.encode()
    return response


STATE_WRITER = '''import fcntl,json,os,pathlib,shutil,sys,tempfile
data=json.load(sys.stdin)
root=pathlib.Path(data['root']).resolve();path=pathlib.Path(data['path'])
if not path.is_absolute() or path.is_symlink() or root not in path.resolve().parents:
    raise ValueError('Server state must stay inside the managed HAProxy directory')
if len(data['content'].encode())>1024*1024:raise ValueError('State response exceeded its limit')
mounts=json.loads(module.subprocess.run(module.argv(data['runtime'],['inspect','--format','{{json .Mounts}}',data['name']]),check=True,capture_output=True,text=True,timeout=10).stdout)
if not any(m.get('Type')=='bind' and m.get('RW') and pathlib.Path(m['Source']).resolve() in path.resolve().parents for m in mounts):
    raise ValueError('Server state requires a writable persistent directory mount')
with open('/var/lock/roxywi-haproxy-config.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    if path.is_symlink() or root not in path.resolve().parents:raise ValueError('Server state path changed')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        if path.exists():
            shutil.copystat(path,tmp)
            metadata=path.stat();os.chown(tmp,metadata.st_uid,metadata.st_gid)
        with os.fdopen(fd,'w') as stream:
            stream.write(data['content']);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
'''


def save_server_state(server, root, path, content):
    data = dict(root=root, path=path, content=content, name=container_settings.name(server.server_id, 'haproxy'),
                runtime=container_settings.runtime(server.server_id, 'haproxy'))
    Remote(server).run(['python3', '-c', containers.embedded() + STATE_WRITER], data=json.dumps(data), timeout=30)
