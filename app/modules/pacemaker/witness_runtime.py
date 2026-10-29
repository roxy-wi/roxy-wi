"""Engine selection and systemd supervision for the fixed managed qnetd recipe.

The source runs on the SSH host with the existing witness runtime. The stable
container name is retained across reviewed image refreshes and NSS migrations.
"""
SOURCE = r'''
ENGINE_FILE = ROOT / 'engine.json'
ENGINE = json.loads(ENGINE_FILE.read_text())['engine'] if ENGINE_FILE.is_file() else 'docker'
if ENGINE not in ('docker', 'podman'): raise ValueError('Invalid recorded witness engine')
WITNESS_UNIT = pathlib.Path('/etc/systemd/system/roxywi-qnetd.service')
UNIT_MARKER = '# Managed by Roxy-WI witness runtime\n'
SUPERVISOR = r"""import json, subprocess, sys
name='roxywi-qnetd'
record=json.loads(subprocess.check_output(['podman','inspect',name]))[0]
if record.get('Config',{}).get('Labels',{}).get('org.roxy-wi.role')!='qnetd':
    raise SystemExit('Refusing an unmanaged witness container')
if not record['State'].get('Running'):
    subprocess.run(['podman','start',name],check=True)
result=subprocess.run(['podman','wait',name],capture_output=True,text=True,check=True)
code=int(result.stdout.strip())
sys.exit(code if 0<=code<=255 else 1)
"""

def ensure_engine():
    if not shutil.which(ENGINE) or (ENGINE == 'podman' and not shutil.which('nft')):
        install_packages('witness-' + ENGINE)
        if ENGINE == 'docker':
            subprocess.run(['systemctl','enable','--now','docker'],check=True,capture_output=True,timeout=60)
    if not shutil.which(ENGINE): raise ValueError('The selected witness engine is unavailable after package installation')
    if ENGINE == 'podman' and not shutil.which('nft'):
        raise ValueError('Podman witness image builds require the nftables userspace tool')

def select_engine(engine):
    global ENGINE
    if engine not in ('docker','podman'): raise ValueError('Select Docker or Podman')
    if ROOT.is_symlink() or ENGINE_FILE.is_symlink(): raise ValueError('Refusing symlinked witness state')
    if engine == ENGINE == 'docker' and not ENGINE_FILE.exists(): return
    if engine != ENGINE:
        ensure_no_pending()
        if DATA.exists() or container_state():
            raise ValueError('Existing container witness requires a reviewed engine migration; it cannot be replaced by installation')
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    if ROOT.stat().st_uid != 0 or ROOT.stat().st_mode & 0o077:
        raise ValueError('Witness state must be private and owned by root')
    with tempfile.NamedTemporaryFile(mode='w',dir=ROOT,delete=False) as stream:
        temporary=pathlib.Path(stream.name)
        try:
            json.dump({'engine':engine},stream);stream.flush();os.fsync(stream.fileno())
            temporary.chmod(0o600);os.replace(temporary,ENGINE_FILE)
        finally:temporary.unlink(missing_ok=True)
    ENGINE=engine

def ensure_supervisor():
    if ENGINE != 'podman': return
    if WITNESS_UNIT.is_symlink() or (WITNESS_UNIT.exists() and not WITNESS_UNIT.read_text().startswith(UNIT_MARKER)):
        raise ValueError('Witness supervisor name belongs to an unmanaged systemd unit')
    helper=ROOT/'supervise.py'
    if helper.is_symlink(): raise ValueError('Refusing symlinked witness helper')
    helper.write_text(SUPERVISOR);helper.chmod(0o600)
    text=UNIT_MARKER+'[Unit]\nDescription=Roxy-WI Podman quorum witness\nAfter=network-online.target\nWants=network-online.target\n'
    text+='[Service]\nType=simple\nExecStart=/usr/bin/python3 '+str(helper)+'\nExecStop=/usr/bin/podman stop --time 20 roxywi-qnetd\n'
    text+='Restart=on-failure\nRestartSec=5\nTimeoutStopSec=45\n[Install]\nWantedBy=multi-user.target\n'
    WITNESS_UNIT.write_text(text);WITNESS_UNIT.chmod(0o644)
    subprocess.run(['systemctl','daemon-reload'],check=True,capture_output=True,timeout=30)
    subprocess.run(['systemctl','enable','roxywi-qnetd.service'],check=True,capture_output=True,timeout=30)

def disable_supervisor():
    if WITNESS_UNIT.exists():
        if WITNESS_UNIT.is_symlink() or not WITNESS_UNIT.read_text().startswith(UNIT_MARKER):
            raise ValueError('Refusing an unmanaged witness supervisor')
        subprocess.run(['systemctl','disable','--now','roxywi-qnetd.service'],check=True,capture_output=True,timeout=60)

_engine_command = command
def command(args, timeout=30):
    if args[0] == 'podman':
        if args[1] == 'build' and '--format=docker' not in args:
            args=[*args[:2],'--format=docker',*args[2:]]
        if args[1] in ('stop','rm','rename') and CONTAINER in args[2:]:
            if WITNESS_UNIT.exists():
                if WITNESS_UNIT.is_symlink() or not WITNESS_UNIT.read_text().startswith(UNIT_MARKER):
                    raise ValueError('Refusing to stop an unmanaged witness supervisor')
                subprocess.run(['systemctl','stop','roxywi-qnetd.service'],check=True,capture_output=True,timeout=60)
                if args[1] == 'rm': disable_supervisor()
        if args[1] == 'start' and args[2:] == [CONTAINER]:
            container_state()  # Verify recipe ownership and persistent NSS mount first.
            ensure_supervisor()
            return _engine_command(['systemctl','start','roxywi-qnetd.service'],timeout=60)
    return _engine_command(args,timeout=timeout)
'''
