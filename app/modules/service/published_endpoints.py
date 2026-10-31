"""Bounded routing inventory. Only public endpoint metadata leaves the parser."""
import hashlib
import ipaddress
import json
import re
import shlex
import posixpath
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from app.modules.common.execution_context import group_settings
from app.modules.db import sql,service as service_sql
from app.modules.pacemaker.remote import Remote
from app.modules.service import haproxy,nginx,container_settings
from app.modules.config import haproxy_files
from app.modules.connectors import containers


def domain(value):
    if not isinstance(value,str) or len(value)>253 or any(ord(c)<33 for c in value):raise ValueError('Invalid domain')
    value=value.rstrip('.').encode('idna').decode().lower()
    if not value or len(value)>253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in value.split('.')):
        raise ValueError('Invalid domain')
    return value


def endpoint(value,*,listener=False):
    if not isinstance(value,str) or len(value)>2048 or any(c in value for c in ('\x00','\r','\n','$')):return None
    if value.startswith(('unix:','/','fd@','sockpair@','abns@')):return None
    scheme=None
    try:
        if '://' in value:
            parsed=urlsplit(value)
            if parsed.scheme not in ('http','https') or parsed.username or parsed.password:return None
            host=parsed.hostname;port=parsed.port or (443 if parsed.scheme=='https' else 80);scheme=parsed.scheme
        elif value.isdigit() and listener:host='*';port=int(value)
        else:
            host,separator,port=value.rpartition(':')
            if not separator or not port.isdigit():return None
            host=host.strip('[]') or '*';port=int(port)
        if not 1<=port<=65535 or host is None or '%' in host:return None
        if host not in ('*','0.0.0.0','::'):
            try:host=str(ipaddress.ip_address(host))
            except ValueError:host=domain(host)
        return dict(host=host,port=port,scheme=scheme)
    except (ValueError,UnicodeError):return None


def host_domains(tokens):
    values=[]
    for value in tokens:
        try:values.append(domain(value))
        except (ValueError,UnicodeError):continue
    return sorted(set(values))


def apache_graph(text):
    nodes=[];edges=[];current=None;number=0;conditional=0
    for raw in text.splitlines():
        line=raw.strip()
        if re.match(r'<(?:If|Macro|Define)',line,re.I) or 'balancer://' in line or re.match(r'ProxyPassMatch\b',line,re.I):conditional+=1
        match=re.fullmatch(r'<VirtualHost\s+(.+)>',line,re.I)
        if match:
            number+=1;current=dict(id=f'apache:{number}',type='virtual_server',addresses=match[1].split(),server_names=[],tls=False)
            nodes.append(current);continue
        if line.lower()=='</virtualhost>':current=None;continue
        if current is None:continue
        try:tokens=shlex.split(line,comments=True)
        except ValueError:continue
        if not tokens:continue
        key=tokens[0].lower()
        if key in ('servername','serveralias'):current['server_names'].extend(host_domains(tokens[1:]))
        elif key=='sslengine' and len(tokens)>1:current['tls']=tokens[1].lower()=='on'
        elif key in ('proxypass','balancermember'):
            target=tokens[2] if key=='proxypass' and len(tokens)>2 else tokens[1] if len(tokens)>1 else ''
            if target:
                ident=f'apache:backend:{len(nodes)}';nodes.append(dict(id=ident,type='server',address=target))
                edges.append(dict(source=current['id'],target=ident))
    return dict(nodes=nodes,edges=edges,partial=bool(conditional))


def haproxy_bind_family(options):
    """Read explicit family flags only at recognized bind-option positions."""
    flags=set();index=0
    bare={'ssl','v4v6','v6only','accept-proxy','transparent','defer-accept','tfo','strict-sni','no-tls-tickets'}
    valued={'crt','crt-list','ca-file','verify','alpn','npn','ciphers','ciphersuites',
            'ssl-min-ver','ssl-max-ver','name','interface','namespace'}
    while index<len(options):
        option=options[index]
        if option in bare:
            if option in ('v4v6','v6only'):flags.add(option)
            index+=1
        elif option in valued and index+1<len(options):index+=2
        else:return None  # Unknown argument arity must not promote a value to a flag.
    return 'v6only' if 'v6only' in flags else 'v4v6' if 'v4v6' in flags else None


def parse(service,text):
    if len(text.encode())>2*1024*1024:raise ValueError('Configuration inventory exceeds 2 MiB')
    graph=haproxy.build_dependency_graph(text) if service=='haproxy' else nginx.build_dependency_graph(text) if service=='nginx' else apache_graph(text)
    listener_families={}
    if service=='haproxy':
        current=None;indexed={node['id']:node for node in graph['nodes']};default_mode='tcp';section=''
        for raw in text.splitlines():
            tokens=haproxy._haproxy_line_tokens(raw)
            if not tokens:continue
            if tokens[0] in ('defaults','global','frontend','listen','backend'):
                section=tokens[0];current=indexed.get(section+':'+tokens[1]) if len(tokens)>1 else None
                if current:current.update(server_names=[],tls=False,mode=default_mode)
            elif tokens[0]=='mode' and len(tokens)>1:
                if section=='defaults':default_mode=tokens[1]
                elif current:current['mode']=tokens[1]
            elif current and tokens[0]=='bind' and len(tokens)>1:
                if 'ssl' in tokens[2:]:current['tls']=True
                mode=haproxy_bind_family(tokens[2:])
                for address in tokens[1].split(','):
                    listener_families.setdefault((current['id'],address.strip()),set()).add(mode)
            elif current and tokens[0]=='acl' and len(tokens)>4 and tokens[2].lower() in ('hdr(host)','req.hdr(host)') and tokens[3]=='-i':
                current['server_names'].extend(host_domains(tokens[4:]))
    indexed={node['id']:node for node in graph['nodes']};links={}
    for edge in graph['edges']:links.setdefault(edge['source'],[]).append(edge)
    frontends=[]
    for front in graph['nodes']:
        if front['type'] not in ('frontend','listen','virtual_server'):continue
        listeners=[]
        for address in front.get('addresses',[]):
            value=endpoint(address,listener=True)
            if value:
                if service in ('haproxy','nginx') and value['host']=='*':value['host']='0.0.0.0'
                modes=listener_families.get((front['id'],address),set())
                if value['host']=='::':
                    if 'v6only' in modes:value['address_family']='v6only'
                    elif modes=={'v4v6'}:value['address_family']='v4v6'
                listeners.append(value)
        seen=set();stack=[front['id']];backends=[];unsupported=0;unresolved=0;evidence=[]
        while stack and len(seen)<2048:
            key=stack.pop()
            if key in seen:continue
            seen.add(key);item=indexed.get(key,{})
            unresolved+=item.get('unresolved_routes',0)
            evidence.extend(item.get('unresolved_route_evidence',[])[:max(0,16-len(evidence))])
            if item.get('type')=='server':
                value=endpoint(item.get('address',''))
                if value:backends.append(dict(id=key,**value))
                else:unsupported+=1
            for edge in links.get(key,[]):
                target=indexed.get(edge['target'],{})
                address=edge.get('target_address',target.get('address',''))
                authority=address.split('://',1)[-1].split('/',1)[0]
                dynamic=service!='haproxy' and '$' in authority
                # Other graph providers retain undefined upstream placeholders.
                # Count each referring route, not one node shared by many routes.
                if dynamic or (service!='haproxy' and target.get('type') in ('backend','upstream') and target.get('defined') is False):
                    unresolved+=1
                    if len(evidence)<16:
                        reason='dynamic-backend-expression' if dynamic else 'undefined-backend'
                        evidence.append(dict(directive=edge.get('type','route'),reason=reason,line=None))
                    if dynamic:continue
                stack.append(edge['target'])
        not_inventoried=max(0,len(backends)-64)+len(stack)
        partial=bool(unresolved or unsupported or not_inventoried or front.get('partial') or (service!='haproxy' and graph.get('partial')))
        frontends.append(dict(id=front['id'],name=front.get('display_name',front.get('name',front['id']))[:255],
            domains=host_domains(front.get('server_names',[])),listeners=listeners,tls=bool(front.get('tls')),
            backends=backends[:64],unsupported_backends=unsupported,provenance='discovered',
            not_inventoried=not_inventoried,unresolved_routes=unresolved,partial=partial,
            unresolved_route_evidence=evidence,
            routing='candidate dependencies; conditional routing is not fully evaluated'))
    if len(frontends)>128:raise ValueError('Too many frontends for a bounded inventory')
    return dict(frontends=frontends,partial=bool(graph.get('partial') or any(front['partial'] for front in frontends)),fingerprint=hashlib.sha256(text.encode()).hexdigest())


READ_FILES=r'''
import json,pathlib,sys
data=json.load(sys.stdin);paths=data['paths'];seen=set();parts=[];total=0
def read(path):
    global total
    path=pathlib.Path(path).resolve()
    if path in seen:return
    if len(seen)>=128 or not path.is_file():raise ValueError('Unsupported configuration include')
    seen.add(path);content=path.read_text();total+=len(content.encode())
    if total>2*1024*1024:raise ValueError('Configuration inventory exceeds its limit')
    parts.append(content)
for value in paths:read(value)
print(json.dumps({'text':'\n'.join(parts),'file_count':len(seen)}))
'''


APACHE_FILES=r'''
import json,pathlib,re,shutil,subprocess,sys
data=json.load(sys.stdin);selected=data.get('binding');main=data['main']
def run(args):
    result=subprocess.run(args,check=True,capture_output=True,text=True,timeout=30)
    value=result.stdout+'\n'+result.stderr
    if len(value.encode())>2*1024*1024:raise ValueError('Apache inventory exceeds its limit')
    return value
if selected:
    command=lambda args:module.argv(selected['runtime'],['exec',selected['name'],*args])
    program='httpd'
else:
    command=lambda args:args
    # RHEL's apachectl wrapper rejects configuration inspection arguments.
    program=next((value for value in ('apache2ctl','httpd','apachectl') if shutil.which(value)),None)
    if not program:raise ValueError('Apache configuration tool is unavailable')
dump=run(command([program,'-t','-D','DUMP_INCLUDES','-f',main]))
paths=[]
for line in dump.splitlines():
    match=re.fullmatch(r'\s*\((?:\*|\d+)\)\s+(/.+?)\s*',line)
    if match and match[1] not in paths:paths.append(match[1])
if not paths or len(paths)>128:raise ValueError('Cannot establish bounded Apache includes')
files={};total=0
for path in paths:
    value=run(command(['cat','--',path])) if selected else pathlib.Path(path).read_text()
    total+=len(value.encode())
    if total>2*1024*1024:raise ValueError('Apache files exceed inventory limits')
    files[path]=value
print(json.dumps({'files':files,'root':paths[0]}))
'''


def apache_configuration(files,root):
    """Inline only files confirmed by Apache's own DUMP_INCLUDES output."""
    partial=False;prefix=posixpath.dirname(root)
    main=files[root]
    match=re.search(r'^\s*ServerRoot\s+"?([^"\r\n]+)"?\s*$',main,re.M)
    if match:prefix=match[1].strip()
    def expand(path,parents):
        nonlocal partial
        if path in parents:raise ValueError('Recursive Apache include')
        lines=[]
        for line in files[path].splitlines():
            match=re.match(r'^\s*Include(?:Optional)?\s+(.+?)(?:\s+#.*)?$',line,re.I)
            if not match:lines.append(line);continue
            name=match[1].strip().strip('"').replace('${APACHE_CONFDIR}',prefix)
            name=posixpath.normpath(name if name.startswith('/') else posixpath.join(prefix,name))
            matches=[value for value in files if PurePosixPath(posixpath.normpath(value)).match(name)]
            if not matches and not any(c in name for c in '*?['):partial=True
            lines.extend(expand(value,parents|{path}) for value in matches)
        value='\n'.join(lines)
        if len(value.encode())>2*1024*1024:raise ValueError('Expanded Apache configuration exceeds inventory limits')
        return value
    return expand(root,set()),partial


def binding(server,service):
    if service_sql.select_service_setting(server.server_id,service,'dockerized')!='1':return None
    return dict(runtime=container_settings.runtime(server.server_id,service),name=container_settings.name(server.server_id,service))


def discover(server,service):
    with group_settings(server.group_id):
        selected=binding(server,service)
        if service=='nginx':
            main=sql.get_setting('nginx_config_path')
            if selected and selected['runtime']['owner']!='root':
                code=containers.embedded()+'import json,sys,subprocess\nd=json.load(sys.stdin)\nr=subprocess.run(module.argv(d["runtime"],["exec",d["name"],"nginx","-T","-c",d["main"]]),check=True,capture_output=True,text=True,timeout=30);print(r.stdout)\n'
                text=Remote(server).run(['python3','-c',code],data=json.dumps(dict(selected,main=main)))
            else:
                args=containers.argv(selected['runtime'],['exec',selected['name'],'nginx','-T','-c',main]) if selected else ['nginx','-T','-c',main]
                text=Remote(server).run(args)
            result=parse(service,text);result['running_sources_verified']=False
        else:
            if service=='haproxy':
                found=haproxy_files.discover_sources(server.ip,server.server_id)
                if found['state']=='error' or not found['files']:raise ValueError('Cannot discover HAProxy configuration sources')
                paths=found['files'];verified=found['verified_running']
                raw=json.loads(Remote(server).run(['python3','-c',READ_FILES],data=json.dumps(dict(paths=paths))))
                result=parse(service,raw['text']);result.update(running_sources_verified=verified,file_count=raw['file_count'])
            else:
                code=containers.embedded()+APACHE_FILES
                raw=json.loads(Remote(server).run(['python3','-c',code],data=json.dumps(dict(main=sql.get_setting('apache_config_path'),binding=selected)),timeout=180))
                text,partial=apache_configuration(raw['files'],raw['root'])
                result=parse(service,text);result.update(running_sources_verified=False,file_count=len(raw['files']),partial=partial or result['partial'])
        result.update(service=service,server_id=server.server_id,binding=selected)
        return result
