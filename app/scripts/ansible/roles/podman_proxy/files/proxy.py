"""Fixed rootful Quadlet proxy recipes. Executed with a JSON request on stdin."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import time

MARKER = '# Managed by Roxy-WI Podman proxy\n'
STATE = Path('/var/lib/roxy-wi/containers')
UNITS = Path('/etc/containers/systemd')
GENERATOR = Path('/usr/lib/systemd/system-generators/podman-system-generator')


def run(argv, timeout=120):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('Podman provisioning step failed: ' + argv[0] + ' ' + argv[1])
    return result.stdout.strip()


def value(text):
    if any(ord(c) < 32 for c in str(text)):
        raise ValueError('Invalid configuration value')
    # Quadlet Volume= is a scalar: surrounding quotes become part of the
    # source/options. The generator escapes the resulting systemd argv itself.
    return str(text).replace('%', '%%')


def validate(data):
    service = data['service']
    if service not in ('haproxy', 'nginx', 'apache'):
        raise ValueError('Unsupported proxy')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', data['name']):
        raise ValueError('Invalid container name')
    expected = {'haproxy': r'docker.io/haproxytech/haproxy-alpine:\d+\.\d+\.\d+',
                'nginx': r'docker.io/library/nginx:stable-alpine', 'apache': r'docker.io/library/httpd:2.4-alpine'}
    if not re.fullmatch(expected[service], data['image']):
        raise ValueError('Select a supported proxy image')
    data.setdefault('log_directory', '/var/log/' + ('httpd' if service == 'apache' else service))
    for field in ('directory', 'config', 'certificates', 'log_directory'):
        path = Path(data[field])
        if not path.is_absolute() or '..' in path.parts or not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(path)):
            raise ValueError('Invalid persistent proxy path')
        if str(path) != str(path.resolve()):
            raise ValueError('Proxy paths must not use symlinks')
    directory = Path(data['directory'])
    if directory.parent == Path('/') or directory in (Path('/etc'), Path('/var/lib'), Path('/usr/local')):
        raise ValueError('Select a dedicated proxy directory')
    if directory not in Path(data['config']).parents:
        raise ValueError('Proxy configuration must be inside its dedicated directory')
    if data['certificates'] != '/var/lib/roxy-wi/certificates/' + service:
        raise ValueError('Use the dedicated managed certificate directory')
    if data['log_directory'] in ('/var/log', '/etc', '/tmp', '/'):
        raise ValueError('Use a dedicated service log directory')
    for field in ('stats_port', 'runtime_port'):
        if not 1 <= int(data[field]) <= 65535:
            raise ValueError('Invalid proxy port')
    for field in ('stats_user', 'stats_password', 'stats_page'):
        if not isinstance(data[field], str) or not data[field] or re.search(r'[\s{};"\\]', data[field]):
            raise ValueError('Statistics credentials and path must be single safe configuration tokens')
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', data['stats_page']):
        raise ValueError('Invalid statistics path')
    pwd.getpwnam(data['user'])
    return data


def render_unit(data, image_id):
    lines = [MARKER.rstrip(), '[Unit]', 'Description=Roxy-WI ' + data['service'] + ' on Podman',
             'After=network-online.target', 'Wants=network-online.target', '[Container]', 'Image=' + image_id,
             'ContainerName=' + data['name'], 'Network=host', 'Label=org.roxy-wi.proxy=' + data['service'],
             'User=0',
             'Volume=' + value(data['directory'] + ':' + data['directory'] + ':rw,Z'),
             'Volume=' + value(data['certificates'] + ':' + data['certificates'] + ':rw,Z')]
    if data['service'] != 'haproxy':
        log_dir = data.get('log_directory', '/var/log/' + ('httpd' if data['service'] == 'apache' else data['service']))
        lines.append('Volume=' + value(log_dir + ':' + log_dir + ':rw,Z'))
    if data['service'] == 'apache':
        lines.append('Volume=' + value(data['directory'] + ':/usr/local/apache2/conf:rw,Z'))
    executable = {'haproxy': 'haproxy -W -db -f ', 'nginx': 'nginx -g "daemon off;" -c ',
                  'apache': 'httpd -DFOREGROUND -f '}[data['service']]
    lines += ['Exec=' + executable + value(data['config']), '[Service]', 'Restart=on-failure',
              'RestartSec=5', 'TimeoutStartSec=180', 'TimeoutStopSec=300', '[Install]', 'WantedBy=multi-user.target']
    return '\n'.join(lines) + '\n'


def write(path, text, account=None):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    if path.is_symlink():
        raise ValueError('Refusing a symlinked proxy file')
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o640 if account else 0o600)
        if account:
            os.chown(temporary, account.pw_uid, account.pw_gid)
        if path.exists():
            shutil.copystat(path, temporary)  # Preserve SELinux and other extended attributes.
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def nginx_mime_types(data, image_id, directory):
    """The dedicated configuration mount hides the image's stock mime.types."""
    destination = directory / 'mime.types'
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError('Refusing an invalid NGINX MIME configuration file')
    if destination.exists():
        return
    seed = 'roxywi-seed-' + os.urandom(8).hex()
    try:
        run(['podman', 'create', '--name', seed, '--network', 'none', image_id])
        with tempfile.TemporaryDirectory(prefix='roxywi-nginx-types-') as temporary:
            source = Path(temporary) / 'mime.types'
            run(['podman', 'cp', seed + ':/etc/nginx/mime.types', str(source)])
            if source.is_symlink() or not source.is_file() or source.stat().st_size > 1024 * 1024:
                raise ValueError('Invalid MIME configuration in the selected NGINX image')
            write(destination, source.read_text(), pwd.getpwnam(data['user']))
    finally:
        subprocess.run(['podman', 'rm', '-f', seed], capture_output=True, timeout=30)


def configure(data, image_id, directory):
    service = data['service']
    config = directory / Path(data['config']).relative_to(data['directory'])
    runtime_directory = Path(data['directory'])
    user, password, port = data['stats_user'], data['stats_password'], int(data['stats_port'])
    account = pwd.getpwnam(data['user'])
    if service == 'apache':
        # Seed only from the pinned official image; never execute image commands
        # with host configuration mounted during discovery.
        seed = 'roxywi-seed-' + os.urandom(8).hex()
        try:
            run(['podman', 'create', '--name', seed, '--network', 'none', image_id])
            run(['podman', 'cp', seed + ':/usr/local/apache2/conf/.', str(directory)])
        finally:
            subprocess.run(['podman', 'rm', '-f', seed], capture_output=True, timeout=30)
        text = (directory / 'httpd.conf').read_text()
        text = re.sub(r'^\s*ErrorLog\s+.*$', 'ErrorLog ' + data['log_directory'] + '/error.log', text, flags=re.M)
        text = re.sub(r'^\s*CustomLog\s+.*$', 'CustomLog ' + data['log_directory'] + '/access.log combined', text, flags=re.M)
        text += '\nServerName 127.0.0.1\n'
        text = text.replace('#LoadModule status_module', 'LoadModule status_module')
        text = text.replace('#LoadModule authn_socache_module', 'LoadModule authn_socache_module')
        text += ('\nListen ' + str(port) + '\n<VirtualHost *:' + str(port) + '>\n<Location /' + data['stats_page'] + '>\n'
                 'SetHandler server-status\nAuthType Basic\nAuthName "Roxy-WI statistics"\nAuthUserFile ' +
                 json.dumps(str(runtime_directory / 'status_page_passwdfile')) + '\nRequire valid-user\n</Location>\n</VirtualHost>\n')
    elif service == 'nginx':
        nginx_mime_types(data, image_id, directory)
        (directory / 'conf.d').mkdir(exist_ok=True)
        (directory / 'sites-enabled').mkdir(exist_ok=True)
        text = ('worker_processes auto;\npid /var/run/nginx.pid;\nerror_log ' + data['log_directory'] + '/error.log warn;\nevents { worker_connections 1024; }\n'
                'http {\ninclude ' + str(runtime_directory / 'mime.types') + ';\nlog_format main escape=json \'{"timestamp":"$time_iso8601","level":"INFO","process_role":"nginx","message":"$request status=$status","client_ip":"$remote_addr","status":$status,"uri":"$request_uri"}\';\n'
                'access_log ' + data['log_directory'] + '/access.log main;\ninclude ' + str(runtime_directory) + '/conf.d/*.conf;\n'
                'include ' + str(runtime_directory) + '/sites-enabled/*.conf;\nserver { listen ' + str(port) + ';\nlocation /' + data['stats_page'] +
                ' { stub_status; auth_basic "Roxy-WI statistics"; auth_basic_user_file ' + str(runtime_directory / 'status_page_passwdfile') + '; }\n}\n}\n')
    else:
        text = ('# BEGIN Roxy-WI MANAGED global do not edit it directly\nglobal\n log 127.0.0.1 len 8192 local0\n user haproxy\n group haproxy\n maxconn 4000\n'
                ' stats socket *:' + str(int(data['runtime_port'])) + ' level admin\n stats socket /var/run/haproxy.sock mode 600 level admin\n'
                '# END Roxy-WI MANAGED global do not edit it directly\n'
                '# BEGIN Roxy-WI MANAGED defaults do not edit it directly\ndefaults\n mode http\n log global\n timeout connect 10s\n timeout client 1m\n timeout server 1m\n'
                '# END Roxy-WI MANAGED defaults do not edit it directly\n'
                '# BEGIN Roxy-WI MANAGED listen stats do not edit it directly\nlisten stats\n bind *:' + str(port) +
                '\n stats enable\n stats uri /stats\n stats auth ' + user + ':' + password +
                '\n stats admin if TRUE\n http-request use-service prometheus-exporter if { path /metrics }\n'
                '# END Roxy-WI MANAGED listen stats do not edit it directly\n')
    if service != 'haproxy':
        # APR1 is generated through stdin, never a password-bearing process argument.
        hashed = subprocess.run(['openssl', 'passwd', '-apr1', '-stdin'], input=password + '\n',
                                capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        write(directory / 'status_page_passwdfile', user + ':' + hashed + '\n', account)
    write(config, text, account)
    for path in (directory, Path(data['certificates'])):
        path.mkdir(parents=True, exist_ok=True, mode=0o750)
        os.chown(path, account.pw_uid, account.pw_gid)
    Path(data['log_directory']).mkdir(parents=True, exist_ok=True, mode=0o755)
    os.chmod(directory, 0o755)
    for path in directory.rglob('*'):
        if not path.is_symlink():
            os.chown(path, account.pw_uid, account.pw_gid)
            if path.is_dir(): os.chmod(path, 0o755)
    if service != 'haproxy': os.chmod(directory / 'status_page_passwdfile', 0o644)


def prepare_configuration(data, image_id, directory, state, manifest, binding, saved):
    if not saved or saved.get('phase') in ('preparing', 'configuration-staged'):
        directory.mkdir(parents=True, exist_ok=True, mode=0o750)
        if any(directory.iterdir()):
            if (not saved or saved.get('phase') != 'configuration-staged'
                    or not Path(data['config']).is_file()
                    or hashlib.sha256(Path(data['config']).read_bytes()).hexdigest() != saved.get('config_digest')):
                raise ValueError('Proxy configuration changed during preparation; inspect or adopt it instead of overwriting it')
        else:
            write(manifest, json.dumps(dict(binding=binding, image_id=image_id, phase='preparing')))
            with tempfile.TemporaryDirectory(prefix='configuration-', dir=state) as staging:
                prepared = Path(staging) / 'tree'; prepared.mkdir(mode=0o750)
                configure(data, image_id, prepared)
                prepared_main = prepared / Path(data['config']).relative_to(data['directory'])
                write(manifest, json.dumps(dict(binding=binding, image_id=image_id, phase='configuration-staged',
                    config_digest=hashlib.sha256(prepared_main.read_bytes()).hexdigest())))
                os.replace(prepared, directory)
        write(manifest, json.dumps(dict(binding=binding, image_id=image_id, phase='configured')))


def install(data):
    data = validate(data)
    if os.geteuid() != 0: raise ValueError('Managed proxy provisioning requires root')
    if not Path('/sys/fs/cgroup/cgroup.controllers').is_file() or not GENERATOR.is_file():
        raise ValueError('Podman Quadlet with cgroup v2 is required')
    version = re.search(r'(\d+)\.(\d+)', run(['podman', '--version']))
    if not version or tuple(map(int, version.groups())) < (4, 9): raise ValueError('Podman 4.9+ is required')
    state = STATE / data['service']; state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if state.is_symlink() or state.stat().st_uid or state.stat().st_mode & 0o077:
        raise ValueError('Managed proxy state must be a private root-owned directory')
    with (state / '.install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        unit = UNITS / ('roxywi-' + data['service'] + '.container')
        manifest = state / 'manifest.json'
        if unit.is_symlink() or manifest.is_symlink(): raise ValueError('Refusing symlinked deployment state')
        saved = json.loads(manifest.read_text()) if manifest.exists() else None
        binding = {key: data[key] for key in ('service', 'name', 'directory', 'config', 'certificates', 'log_directory')}
        if saved and saved['binding'] != binding: raise ValueError('Deployment paths changed; use service adoption or restore the original binding')
        if unit.exists() and (not saved or not unit.read_text().startswith(MARKER)):
            raise ValueError('An unmanaged Quadlet already exists')
        manager = subprocess.run(['systemctl', 'show', 'roxywi-' + data['service'] + '.service', '--property=SourcePath,LoadState'], capture_output=True, text=True)
        fields = dict(line.split('=', 1) for line in manager.stdout.splitlines() if '=' in line)
        if fields.get('LoadState') == 'loaded' and fields.get('SourcePath') != str(unit):
            raise ValueError('An unmanaged systemd service already exists')
        if fields.get('LoadState') not in ('loaded', 'not-found'):
            raise ValueError('Cannot verify systemd service ownership')
        exists = subprocess.run(['podman', 'container', 'exists', data['name']], capture_output=True)
        if exists.returncode == 0:
            record = json.loads(run(['podman', 'inspect', data['name']]))[0]
            if not saved or record.get('Config', {}).get('Labels', {}).get('org.roxy-wi.proxy') != data['service']:
                raise ValueError('Adopt the existing container in service settings instead of overwriting it')
        elif exists.returncode != 1: raise ValueError('Cannot verify Podman container ownership')
        for native in ({'apache': ('httpd', 'apache2')}.get(data['service'], (data['service'],))):
            if subprocess.run(['systemctl', 'is-active', '--quiet', native], capture_output=True).returncode == 0:
                raise ValueError('Stop or migrate the native proxy explicitly before container installation')
        directory = Path(data['directory'])
        if not saved and directory.exists() and any(directory.iterdir()):
            raise ValueError('Existing proxy configuration requires adoption; provisioning accepts an empty dedicated directory')
        run(['podman', 'pull', data['image']], timeout=600)
        image_id = run(['podman', 'image', 'inspect', '--format', '{{.Id}}', data['image']])
        if not re.fullmatch(r'(sha256:)?[a-f0-9]{64}', image_id): raise ValueError('Cannot pin the proxy image')
        prepare_configuration(data, image_id, directory, state, manifest, binding, saved)
        if data['service'] == 'nginx':
            # Repair this missing dependency on retry without regenerating an
            # already configured proxy tree or overwriting operator edits.
            nginx_mime_types(data, image_id, directory)
        text = render_unit(data, image_id)
        # Validate against the installed generator before installing a host unit.
        with tempfile.TemporaryDirectory(prefix='roxywi-quadlet-check-') as tmp:
            Path(tmp, unit.name).write_text(text)
            generated = subprocess.run([str(GENERATOR), '--dryrun'], env={**os.environ, 'QUADLET_UNIT_DIRS': tmp}, capture_output=True, text=True, timeout=30)
            if generated.returncode or 'failed to' in generated.stderr.lower() or 'unknown key' in generated.stderr.lower():
                raise ValueError('Installed Quadlet generator rejected the proxy unit')
        previous = unit.read_text() if unit.exists() else None
        write(unit, text)
        service = 'roxywi-' + data['service'] + '.service'
        try:
            run(['systemctl', 'daemon-reload']); run(['systemctl', 'restart', service], timeout=200)
            check = {'haproxy': ['haproxy', '-c', '-f', data['config']], 'nginx': ['nginx', '-t', '-c', data['config']],
                     'apache': ['httpd', '-t', '-f', data['config']]}[data['service']]
            for _ in range(3):
                run(['podman', 'exec', data['name'], *check]); time.sleep(1)
            write(manifest, json.dumps(dict(binding=binding, image_id=image_id)))
        except Exception:
            if previous:
                write(unit, previous); run(['systemctl', 'daemon-reload']); run(['systemctl', 'restart', service], timeout=200)
            else:
                subprocess.run(['systemctl', 'stop', service], capture_output=True, timeout=60)
            raise
        if data.get('syn_flood'):
            write(Path('/etc/sysctl.d/90-roxywi-syn.conf'), 'net.ipv4.tcp_syncookies = 1\nnet.ipv4.tcp_max_syn_backlog = 1024\nnet.ipv4.tcp_synack_retries = 3\n')
            run(['sysctl', '-p', '/etc/sysctl.d/90-roxywi-syn.conf'])
        return {'engine': 'podman', 'name': data['name'], 'unit': service, 'image_id': image_id}


if __name__ == '__main__':
    try:
        print(json.dumps(install(json.load(sys.stdin))))
    except Exception as error:
        print(json.dumps({'error': str(error) if isinstance(error, ValueError) else 'Proxy installation failed; inspect the owning systemd journal'}))
        sys.exit(1)
