#!/usr/bin/env python3
"""Deploy the Roxy-WI controller with native Podman Quadlet units.

Run as the system administrator for system units or as the owning login account
for rootless units. This never controls an engine belonging to another user.
"""
import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request
from urllib.error import URLError

ROOT=Path(__file__).resolve().parents[1]
PREFIX='# Managed by Roxy-WI Quadlet deployment\n'
ROLES=('web','scheduler','service-events','operations')
IMAGE='localhost/roxy-wi:podman'
VOLUMES=('roxywi-app-data','roxywi-broker-data','roxywi-tls-data','roxywi-tls-config')
SECRET_NAMES={'secret_key':'roxywi-secret-key','secret_phrase':'roxywi-secret-phrase',
              'broker_password':'roxywi-broker-password'}


def deployment_id(directory):
    return hashlib.sha256(str(Path(directory).resolve()).encode()).hexdigest()


def endpoint(value):
    parsed=urlsplit(value)
    if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or
            parsed.fragment or parsed.path not in ('','/') or re.search(r'[\s{};\\]',value)):
        raise ValueError('Use an HTTPS origin without credentials, path, query or fragment')
    _port=parsed.port
    return value.rstrip('/')


def image_name(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9./_:@-]{0,255}',value):
        raise ValueError('Invalid OCI image reference')
    return value


def unit_value(value):
    if any(c in str(value) for c in '\x00\r\n'):
        raise ValueError('Invalid unit value')
    # Volume= is a Quadlet scalar, not a shell argument. Its generator performs
    # systemd argv quoting; quotes here would become literal mount characters.
    return str(value).replace('%','%%')


def units(directory,image=IMAGE,public_url='https://localhost:8443',bind='127.0.0.1:8443'):
    image=image_name(image);public_url=endpoint(public_url)
    address=urlsplit('//'+bind)
    if address.username or address.password or address.path or address.query or address.fragment or not address.hostname:
        raise ValueError('Use an explicit bind IP address and port')
    ipaddress.ip_address(address.hostname)
    if address.port is None or not 1<=address.port<=65535:
        raise ValueError('Invalid bind port')
    directory=Path(directory).resolve()
    label='Label=org.roxy-wi.deployment='+deployment_id(directory)
    common=['Network=roxywi.network','Volume=roxywi-app.volume:/var/lib/roxy-wi:U,z',
            'Volume='+unit_value(str(directory/'roxy-wi.cfg')+':/etc/roxy-wi/roxy-wi.cfg:ro,z'),
            'Secret=roxywi-secret-key,type=env,target=ROXYWI_SECRET_KEY',
            'Secret=roxywi-secret-phrase,type=env,target=ROXYWI_SECRET_PHRASE',
            'Secret=roxywi-broker-password,type=env,target=ROXYWI_RABBITMQ_PASSWORD',
            'Environment=ROXYWI_DEPLOYMENT_MODE=quadlet',
            'Environment=ROXYWI_CONFIG_FILE=/etc/roxy-wi/roxy-wi.cfg','Environment=ROXYWI_AUTO_MIGRATE=0',
            'Environment=ROXYWI_DATABASE_ENGINE=sqlite','Environment=ROXYWI_DB_PATH=/var/lib/roxy-wi/roxy-wi.db',
            'Environment=ROXYWI_RABBITMQ_HOST=roxywi-broker','Environment=ROXYWI_RABBITMQ_USER=roxy-wi',
            'Environment=ROXYWI_RABBITMQ_VHOST=/','Environment=ROXYWI_CACHE_TYPE=NullCache',
            'Environment=ROXYWI_LOG_CONSOLE=1','Environment=ROXYWI_LOG_FILE_ENABLED=0',
            'Environment=ROXYWI_PUBLIC_URL='+public_url,'DropCapability=ALL','NoNewPrivileges=true','RunInit=true',label]
    result={'roxywi.network':PREFIX+'[Network]\nNetworkName=roxywi-backend\n'+label+'\n',
            'roxywi-app.volume':PREFIX+'[Volume]\nVolumeName=roxywi-app-data\n',
            'roxywi-broker.volume':PREFIX+'[Volume]\nVolumeName=roxywi-broker-data\n',
            'roxywi-tls-data.volume':PREFIX+'[Volume]\nVolumeName=roxywi-tls-data\n',
            'roxywi-tls-config.volume':PREFIX+'[Volume]\nVolumeName=roxywi-tls-config\n'}
    for role in ('migrate',*ROLES):
        oneshot=role=='migrate'
        dependencies='' if oneshot else 'Requires=roxywi-migrate.service roxywi-broker.service\nAfter=roxywi-migrate.service roxywi-broker.service\n'
        container=['Image='+image,'ContainerName=roxywi-'+role,'PodmanArgs=--network-alias=roxywi-'+role,
                   'Exec='+role,'StopTimeout='+('1800' if role=='operations' else '300'),*common,'HealthCmd=none' if oneshot else 'HealthCmd=python /var/www/haproxy-wi/roxy_wi.py healthcheck --role '+role,
                   'HealthInterval=30s','HealthTimeout=5s','HealthRetries=3']
        service='Type=oneshot\nRemainAfterExit=yes\nTimeoutStartSec=600\nTimeoutStopSec=360\n' if oneshot else 'Restart=on-failure\nRestartSec=5s\nTimeoutStartSec=600\nTimeoutStopSec='+('1860' if role=='operations' else '360')+'\n'
        result['roxywi-'+role+'.container']=PREFIX+'[Unit]\nDescription=Roxy-WI '+role+'\n'+dependencies+'[Container]\n'+'\n'.join(container)+'\n[Service]\n'+service+('' if oneshot else '[Install]\nWantedBy='+('multi-user.target' if os.geteuid()==0 else 'default.target')+'\n')
    result['roxywi-broker.container']=PREFIX+'''[Unit]
Description=Roxy-WI broker
[Container]
Image=docker.io/library/rabbitmq:4-management
ContainerName=roxywi-broker
HostName=roxywi-broker
StopTimeout=120
Network=roxywi.network
PodmanArgs=--network-alias=roxywi-broker
Volume=roxywi-broker.volume:/var/lib/rabbitmq:U,z
'''+label+'''
Secret=roxywi-broker-password,type=env,target=RABBITMQ_DEFAULT_PASS
Environment=RABBITMQ_DEFAULT_USER=roxy-wi
Environment=RABBITMQ_DEFAULT_VHOST=/
HealthCmd=docker-entrypoint.sh rabbitmq-diagnostics -q ping
HealthInterval=10s
HealthTimeout=5s
HealthRetries=12
[Service]
Restart=on-failure
RestartSec=5s
TimeoutStartSec=600
TimeoutStopSec=180
'''
    result['roxywi-tls.container']=PREFIX+'''[Unit]
Description=Roxy-WI HTTPS endpoint
Requires=roxywi-web.service
After=roxywi-web.service
[Container]
Image=docker.io/library/caddy:2-alpine
ContainerName=roxywi-tls
StopTimeout=30
Network=roxywi.network
PublishPort='''+bind+''':443
Volume=roxywi-tls-data.volume:/data:U,z
Volume=roxywi-tls-config.volume:/config:U,z
Volume='''+unit_value(str(directory/'Caddyfile')+':/etc/caddy/Caddyfile:ro,Z')+'\n'+label+'''
[Service]
Restart=on-failure
RestartSec=5s
TimeoutStartSec=600
TimeoutStopSec=90
[Install]
WantedBy='''+('multi-user.target' if os.geteuid()==0 else 'default.target')+'\n'
    for name in tuple(result):
        if name.endswith('.volume'):
            result[name]+=label+'\n'
    return result


def write(path,content,mode=0o600,managed=False):
    if path.is_symlink():
        raise ValueError('Refusing to replace a symlink: '+str(path))
    if path.exists() and managed and not path.read_text().startswith(PREFIX):
        raise ValueError('An unmanaged unit already exists: '+str(path))
    temporary=path.with_name('.'+path.name+'.'+secrets.token_hex(6))
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            os.chmod(temporary,mode);stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def secret_record(name,show=False):
    exists=subprocess.run(['podman','secret','exists',name],capture_output=True,timeout=20)
    if exists.returncode==1:return None
    if exists.returncode!=0:raise ValueError('Cannot verify Podman secret ownership')
    args=['podman','secret','inspect',*(['--showsecret'] if show else []),name]
    records=json.loads(subprocess.run(args,check=True,capture_output=True,text=True,timeout=30).stdout)
    if len(records)!=1 or records[0].get('Spec',{}).get('Name')!=name:
        raise ValueError('Cannot identify the controller secret')
    return records[0]


def controller_secrets(directory,gpg_fingerprint=None,create=False):
    """Persist only public metadata; secret values go to the encrypted driver."""
    directory=Path(directory)
    manifest=directory/'secrets.json'
    if manifest.is_symlink():raise ValueError('The secrets manifest must not be a symlink')
    for name in ('app.env','broker.env'):
        if (directory/name).exists() or (directory/name).is_symlink():
            raise ValueError('Legacy plaintext secrets require a reviewed migration; refusing to replace encryption keys')
    metadata=json.loads(manifest.read_text()) if manifest.exists() else None
    if metadata is not None:
        if (set(metadata)!={'format','key','complete'} or metadata['format']!=1 or
                not isinstance(metadata['complete'],bool)):
            raise ValueError('Legacy plaintext secrets require a reviewed migration; refusing to replace encryption keys')
        if gpg_fingerprint is not None and gpg_fingerprint.upper()!=metadata['key']:
            raise ValueError('Restore the original GPG key; controller secrets cannot be silently rekeyed')
        gpg_fingerprint=metadata['key']
    if not isinstance(gpg_fingerprint,str) or not re.fullmatch(r'(?:[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})',gpg_fingerprint):
        raise ValueError('Provide --gpg-fingerprint with the encryption-capable GPG fingerprint of the Podman owner')
    gpg_fingerprint=gpg_fingerprint.upper()
    encrypted=directory/'encrypted-secrets'
    if encrypted.is_symlink():raise ValueError('The encrypted secret store must not be a symlink')
    if create:
        encrypted.mkdir(exist_ok=True,mode=0o700)
    if encrypted.exists() and (encrypted.stat().st_uid!=os.geteuid() or encrypted.stat().st_mode&0o077):
        raise ValueError('The encrypted secret store must be owned and private (0700)')
    expected={'root':str(encrypted.resolve()),'key':gpg_fingerprint}
    records={key:secret_record(name) for key,name in SECRET_NAMES.items()}
    # A missing manifest must not adopt pre-existing secrets or regenerate keys.
    if metadata is None:
        if not create or any(record is not None for record in records.values()):
            raise ValueError('Restore the original controller secret manifest and encrypted secrets')
        metadata={'format':1,'key':gpg_fingerprint,'complete':False}
        write(manifest,json.dumps(metadata))
    if not create and not metadata['complete']:
        raise ValueError('Restore the complete original encrypted controller secrets before starting')
    for record in records.values():
        if record is not None:
            spec=record.get('Spec',{})
            if (spec.get('Driver',{}).get('Name')!='pass' or spec.get('Driver',{}).get('Options')!=expected or
                    spec.get('Labels',{}).get('org.roxy-wi.deployment')!=deployment_id(directory)):
                raise ValueError('A controller secret belongs to another deployment or an unencrypted driver')
    for key,name in SECRET_NAMES.items():
        record=records[key]
        if record is None:
            if not create or metadata['complete']:
                raise ValueError('Restore the original encrypted controller secrets before starting')
            value=(base64.urlsafe_b64encode(os.urandom(32)).decode() if key=='secret_phrase'
                   else secrets.token_urlsafe(48))
            command(['podman','secret','create','--driver=pass','--driver-opts=root='+expected['root'],
                     '--driver-opts=key='+gpg_fingerprint,'--label=org.roxy-wi.deployment='+deployment_id(directory),name,'-'],
                    input=value,text=True,capture_output=True,timeout=30)
        record=secret_record(name,show=True)
        spec=record.get('Spec',{}) if record else {}
        if (spec.get('Driver',{}).get('Name')!='pass' or spec.get('Driver',{}).get('Options')!=expected or
                spec.get('Labels',{}).get('org.roxy-wi.deployment')!=deployment_id(directory)):
            raise ValueError('A controller secret belongs to another deployment or an unencrypted driver')
        value=record.get('SecretData')
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_=-]{32,128}',value):
            raise ValueError('Cannot decrypt the original controller secret with the owning GPG key')
        if key=='secret_phrase' and len(base64.urlsafe_b64decode(value))!=32:
            raise ValueError('Restore the original application encryption key')
    if create and not metadata['complete']:
        metadata['complete']=True
        write(manifest,json.dumps(metadata))


def prepare(directory,unit_directory,gpg_fingerprint=None,**options):
    directory,unit_directory=Path(directory),Path(unit_directory)
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    if directory.is_symlink() or directory.stat().st_uid!=os.geteuid() or directory.stat().st_mode&0o077:
        raise ValueError('Deployment state must be an owned private directory (0700)')
    rendered=units(directory,**options)
    unit_directory.mkdir(parents=True,exist_ok=True)
    for name in rendered:
        path=unit_directory/name
        if path.is_symlink() or (path.exists() and not path.read_text().startswith(PREFIX)):
            raise ValueError('An unmanaged unit already exists: '+str(path))
    controller_secrets(directory,gpg_fingerprint,create=True)
    if (directory/'roxy-wi.cfg').is_symlink():raise ValueError('The application configuration must not be a symlink')
    if not (directory/'roxy-wi.cfg').exists():
        write(directory/'roxy-wi.cfg',(ROOT/'docker/roxy-wi.docker.cfg').read_text(),0o644)
    hostname=urlsplit(options.get('public_url','https://localhost:8443')).hostname
    host='['+hostname+']' if ':' in hostname else hostname
    if not (directory/'Caddyfile').exists():
        write(directory/'Caddyfile','https://'+host+':443 {\n tls internal\n reverse_proxy roxywi-web:8080\n}\n')
    elif (directory/'Caddyfile').is_symlink():
        raise ValueError('The HTTPS configuration must not be a symlink')
    for name,content in rendered.items():write(unit_directory/name,content,0o644,managed=True)
    return rendered


def command(arguments,**kwargs):
    return subprocess.run(arguments,check=True,**kwargs)


def verify_resources(directory):
    """Do not attach another deployment's data or silently replace its keys."""
    expected=deployment_id(directory)
    for kind,names in (('network',('roxywi-backend',)),('volume',VOLUMES),('container',tuple('roxywi-'+role for role in ('migrate',*ROLES,'broker','tls')))):
        for name in names:
            exists=subprocess.run(['podman',kind,'exists',name],capture_output=True,timeout=20)
            if exists.returncode==1:continue
            if exists.returncode!=0:raise ValueError('Cannot determine existing Podman resource ownership')
            record=json.loads(command(['podman',kind,'inspect',name],capture_output=True,text=True,timeout=20).stdout)[0]
            labels=record.get('Labels',record.get('labels',{})) if kind in ('volume','network') else record.get('Config',{}).get('Labels',{})
            if (labels or {}).get('org.roxy-wi.deployment')!=expected:
                raise ValueError('Existing '+kind+' '+name+' belongs to another or unmanaged deployment')
            if not (Path(directory)/'secrets.json').is_file():
                raise ValueError('Existing controller data requires its original deployment secrets; restore them before starting')
            controller_secrets(directory)


def verify_manager(manager,unit_directory):
    for role in ('migrate',*ROLES,'broker','tls'):
        result=subprocess.run([*manager,'show','roxywi-'+role+'.service','--property=LoadState,SourcePath'],capture_output=True,text=True,timeout=15)
        fields=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
        if fields.get('LoadState')=='not-found':continue
        if result.returncode or fields.get('LoadState')!='loaded':raise ValueError('Cannot verify the controller systemd manager')
        if Path(fields.get('SourcePath','')).resolve()!=(Path(unit_directory)/('roxywi-'+role+'.container')).resolve():
            raise ValueError('A controller service name belongs to an unmanaged systemd unit')


def probe_https(public_url):
    # Read the public evaluation CA, never its private key, and verify the actual
    # HTTPS endpoint with it. Do not install a CA in the host trust store.
    ca=command(['podman','exec','roxywi-tls','cat','/data/caddy/pki/authorities/local/root.crt'],capture_output=True,text=True,timeout=10).stdout
    if len(ca)>65536:raise ValueError('Unexpected HTTPS trust certificate')
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=ca)
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=build_opener(ProxyHandler({}),HTTPSHandler(context=context),NoRedirect())
    with opener.open(Request(endpoint(public_url)+'/health/ready'),timeout=5) as response:
        return response.status==200


def verify_init_runtime(image):
    """Check the host's configured init helper before creating controller state."""
    name='roxywi-init-probe-'+secrets.token_hex(8)
    try:
        result=subprocess.run(['podman','run','--pull=never','--rm','--name',name,
            '--network=none','--init','--cap-drop=all','--security-opt=no-new-privileges',
            '--entrypoint=/bin/true',image_name(image)],capture_output=True,text=True,timeout=30)
        if result.returncode:
            if 'catatonit' in result.stderr.lower() or 'init binary' in result.stderr.lower():
                raise ValueError('Podman init helper is missing; install catatonit on Debian or the init helper configured by your Podman package')
            raise ValueError('Podman cannot start the selected controller image with --init; inspect the host runtime and init helper')
    except subprocess.TimeoutExpired:
        raise ValueError('Podman init preflight timed out; inspect the host runtime before starting the controller') from None
    finally:
        subprocess.run(['podman','rm','--force','--ignore',name],capture_output=True,timeout=15)


def wait_ready(timeout=300,public_url=None):
    deadline=time.monotonic()+timeout
    consecutive=0
    while time.monotonic()<deadline:
        ready=True
        for role in ROLES:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('Controller readiness timed out; persistent data and secrets were retained')
            try:
                result=subprocess.run(['podman','exec','roxywi-'+role,'python','/var/www/haproxy-wi/roxy_wi.py',
                                       'healthcheck','--role',role],capture_output=True,timeout=min(20,remaining))
                ready=ready and result.returncode==0
            except subprocess.TimeoutExpired:ready=False
        if public_url:
            try:ready=probe_https(public_url) and ready
            except (ValueError,OSError,URLError,subprocess.SubprocessError):ready=False
        consecutive=consecutive+1 if ready else 0
        if consecutive>=3:return
        time.sleep(2)
    raise ValueError('Controller readiness timed out; inspect status and logs. Persistent data and secrets were retained')


def main():
    root=os.geteuid()==0
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','start','upgrade','stop','status','logs','password'))
    parser.add_argument('--directory',type=Path,default=Path('/var/lib/roxy-wi-quadlet') if root else Path.home()/'.local/share/roxy-wi-quadlet')
    parser.add_argument('--unit-directory',type=Path,default=Path('/etc/containers/systemd') if root else Path.home()/'.config/containers/systemd')
    parser.add_argument('--gpg-fingerprint',help='Encryption-capable GPG fingerprint; required for first prepare')
    parser.add_argument('--image')
    parser.add_argument('--public-url')
    parser.add_argument('--bind')
    parser.add_argument('--build',action='store_true')
    args=parser.parse_args()
    manager=['systemctl',*([] if root else ['--user'])]
    try:
        if args.action in ('prepare','start','upgrade'):
            if not Path('/sys/fs/cgroup/cgroup.controllers').is_file():raise ValueError('Quadlet deployment requires cgroup v2')
            version=command(['podman','--version'],capture_output=True,text=True).stdout
            match=re.search(r'(\d+)\.(\d+)',version)
            if not match or tuple(map(int,match.groups()))<(4,9):raise ValueError('Podman 4.9 or newer with Quadlet is required')
            settings_path=args.directory/'settings.json'
            if args.directory.exists() and (args.directory.is_symlink() or args.directory.stat().st_uid!=os.geteuid() or args.directory.stat().st_mode&0o077):
                raise ValueError('Deployment state must be an owned private directory (0700)')
            if settings_path.is_symlink():raise ValueError('Deployment settings must not be a symlink')
            verify_resources(args.directory)
            verify_manager(manager,args.unit_directory)
            saved=json.loads(settings_path.read_text()) if settings_path.exists() else None
            if args.action in ('start','upgrade') and saved is None:
                raise ValueError('Run prepare before starting or upgrading a controller')
            changing=args.build or any(value is not None for value in (args.image,args.public_url,args.bind))
            if saved is not None and args.action!='upgrade' and changing:
                raise ValueError('Use upgrade to change a prepared deployment image or options')
            settings=dict(saved) if saved is not None else dict(image=IMAGE,public_url='https://localhost:8443',bind='127.0.0.1:8443')
            settings.update({key:value for key,value in dict(image=args.image,public_url=args.public_url,bind=args.bind).items() if value is not None})
            active=any(subprocess.run([*manager,'is-active','--quiet','roxywi-'+role+'.service'],capture_output=True).returncode==0 for role in ROLES)
            if args.action=='prepare' and active:
                raise ValueError('Use upgrade to prepare changes to an active controller')
            if saved is None or args.action=='upgrade':
                if args.build:command(['podman','build','--format=docker','-t',image_name(settings['image']),'-f',str(ROOT/'docker/Dockerfile'),str(ROOT)])
                image_id=command(['podman','image','inspect','--format','{{.Id}}',image_name(settings['image'])],capture_output=True,text=True).stdout.strip()
            else:
                image_id=settings.get('image_id','')
            if not isinstance(image_id,str) or not re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}',image_id):
                raise ValueError('No verified immutable controller image ID; use upgrade to select an image and run its migrations')
            settings['image_id']=image_id
            if args.action!='prepare':verify_init_runtime(image_id)
            # Stop the old deployment and its completed migration before replacing
            # units or the image pin. Interrupted upgrades cannot leave a new
            # image coupled to an active old RemainAfterExit migration.
            if args.action=='upgrade':
                command([*manager,'stop','roxywi-tls.service',*['roxywi-'+role+'.service' for role in reversed(ROLES)],'roxywi-migrate.service'])
            prepare(args.directory,args.unit_directory,gpg_fingerprint=args.gpg_fingerprint,image=image_id,public_url=settings['public_url'],bind=settings['bind'])
            write(settings_path,json.dumps(settings))
            command([*manager,'daemon-reload'])
            if args.action=='prepare':return
            if args.action=='start' and not active:
                # An independently stopped controller can retain a completed
                # migration oneshot. Reset it so this exact image is migrated.
                command([*manager,'stop','roxywi-migrate.service'])
            verify_resources(args.directory)
            command([*manager,'start','roxywi-migrate.service'])
            command([*manager,'start','roxywi-web.service','roxywi-scheduler.service','roxywi-service-events.service','roxywi-operations.service','roxywi-tls.service'])
            wait_ready(public_url=settings['public_url'])
            print('Controller and HTTPS readiness verified: '+endpoint(settings['public_url']))
        elif args.action=='stop':
            verify_resources(args.directory);verify_manager(manager,args.unit_directory)
            command([*manager,'stop','roxywi-tls.service',*['roxywi-'+role+'.service' for role in reversed(ROLES)],'roxywi-migrate.service','roxywi-broker.service'])
        elif args.action=='status':command([*manager,'status','roxywi-*.service','--no-pager'])
        elif args.action=='logs':command(['journalctl',*([] if root else ['--user']),'-u','roxywi-*.service','--no-pager','-n','100'])
        elif args.action=='password':
            verify_resources(args.directory)
            command(['podman','exec','roxywi-web','cat','/var/lib/roxy-wi/bootstrap-admin-password'])
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        parser.exit(1,'Quadlet deployment failed: '+str(error)+'\n')


if __name__=='__main__':main()
