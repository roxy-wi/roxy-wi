import json
from types import SimpleNamespace

import pytest

from app.modules.pacemaker.platforms import SOURCE, DETECT


def runtime(distro='debian', version='13', container=False, split_agents=False):
    files = {'/etc/os-release': f'ID={distro}\nVERSION_ID="{version}"\n',
             '/proc/sys/net/ipv4/tcp_max_syn_backlog': '8192'}
    calls = []
    class Path:
        def __init__(self, value):
            self.value = str(value)
        def read_text(self):
            return files[self.value]
        def exists(self):
            return self.value in files or (container and self.value == '/.dockerenv')
        def is_dir(self):
            return self.value == '/run/systemd/system'
        def with_suffix(self, suffix):
            return Path(self.value.rsplit('.', 1)[0] + suffix)
        def write_text(self, value):
            files[self.value] = value
        def chmod(self, mode):
            calls.append(('chmod', self.value, mode))
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=b'Package: resource-agents-base' if split_agents else b'')
    def replace(source, target):
        files[target.value] = files.pop(source.value)
    namespace = {}
    exec(SOURCE, namespace)
    namespace.update(pathlib=SimpleNamespace(Path=Path), shutil=SimpleNamespace(which=lambda tool: '/usr/bin/' + tool),
                     subprocess=SimpleNamespace(run=run, DEVNULL=-3), os=SimpleNamespace(environ={}, replace=replace))
    return namespace, files, calls


@pytest.mark.parametrize('distro,version,manager,qualified', [
    ('debian', '13', 'apt-get', True), ('debian', '12', 'apt-get', False),
    ('ubuntu', '22.04', 'apt-get', False), ('ubuntu', '24.04', 'apt-get', False),
    ('rhel', '9.6', 'dnf', False), ('rocky', '9.6', 'dnf', False),
    ('rocky', '9.8', 'dnf', True),
    ('almalinux', '8.10', 'dnf', False), ('ol', '8.10', 'dnf', False), ('centos', '9', 'dnf', False),
])
def test_native_package_profiles(distro, version, manager, qualified):
    code, _files, calls = runtime(distro, version)
    result = code['install_packages']('cluster')
    assert result['qualified'] is qualified
    command = next(args for args in calls if isinstance(args, list) and 'install' in args)
    assert command[0] == manager
    assert 'pacemaker' in command and 'corosync' in command
    assert ('pacemaker-cli-utils' in command) == (manager == 'apt-get')


@pytest.mark.parametrize('distro,version', [('rhel', '7.9'), ('debian', '10'), ('ubuntu', '18.04'), ('opensuse-leap', '15.6')])
def test_unsupported_bootstrap_is_rejected_before_mutation(distro, version):
    code, _files, calls = runtime(distro, version)
    with pytest.raises(SystemExit, match='No automatic installation profile'):
        code['install_packages']('cluster')
    assert not calls


def test_ubuntu_resource_agent_split():
    code, _files, calls = runtime('ubuntu', '24.04', split_agents=True)
    code['install_packages']('cluster')
    command = next(args for args in calls if isinstance(args, list) and 'install' in args)
    assert 'resource-agents-base' in command and 'resource-agents-extra' in command
    assert 'resource-agents' not in command


@pytest.mark.parametrize('role,package', [('witness', 'corosync-qnetd'), ('qdevice', 'corosync-qdevice')])
@pytest.mark.parametrize('distro,version', [('debian', '13'), ('rocky', '9.6')])
def test_quorum_roles_do_not_install_a_cluster(role, package, distro, version):
    code, _files, calls = runtime(distro, version)
    code['install_packages'](role)
    command = next(args for args in calls if isinstance(args, list) and 'install' in args)
    assert command[-1] == package
    assert 'pacemaker' not in command and 'corosync' not in command


@pytest.mark.parametrize('distro,version',[('debian','13'),('rocky','9.8')])
def test_podman_witness_includes_the_build_network_userspace_tool(distro,version):
    code,_files,calls=runtime(distro,version)
    code['install_packages']('witness-podman')
    command=next(args for args in calls if isinstance(args,list) and 'install' in args)
    assert 'podman' in command and 'nftables' in command
    assert not any(isinstance(args,list) and args[0]=='systemctl' for args in calls)


def test_cluster_in_a_container_is_refused_before_installing():
    code, _files, calls = runtime(container=True)
    with pytest.raises(SystemExit, match='Cluster daemons must run on the host'):
        code['install_packages']('cluster')
    assert not calls


def test_syn_protection_persists_only_explicit_tcp_tunables_and_preserves_larger_backlog():
    code, files, calls = runtime()
    code['enable_syn_flood_protection']()
    saved = files['/etc/sysctl.d/90-roxywi-syn-flood.conf']
    assert 'tcp_syncookies = 1' in saved and 'tcp_max_syn_backlog = 8192' in saved
    assert 'rp_filter' not in saved
    assert len([args for args in calls if args[0] == 'sysctl']) == 3
    assert all('--system' not in args for args in calls)


def test_ha_provider_choice_keeps_existing_keepalived_guards(client, authenticated, monkeypatch):
    from app.modules.roxywi import common
    monkeypatch.setattr(common, 'return_user_subscription', lambda: SimpleNamespace(user_status=0, user_plan='user'))
    response = client.get('/ha/cluster', headers=authenticated[1])
    assert response.status_code == 200
    assert 'id="ha-provider"' in response.text
    assert 'data-url="/ha/cluster"' in response.text and 'data-url="/pacemaker"' in response.text
    response = client.get('/pacemaker', headers=authenticated[1])
    assert response.status_code == 200 and 'id="ha-provider"' in response.text
    assert 'pcmk-bootstrap-syn' in response.text


def test_platform_endpoint_is_scoped_and_rejects_viewers(client, authenticated, monkeypatch):
    from app.modules.db.db_model import Server
    from app.modules.pacemaker.remote import Remote
    server = Server.create(hostname='platform-test', ip='192.0.2.240', group_id='1')
    calls = []
    def run(_self, args):
        calls.append(args)
        return json.dumps({'supported': True, 'id': 'debian', 'version': '13', 'manager': 'apt-get', 'qualified': True})
    monkeypatch.setattr(Remote, 'run', run)
    try:
        assert client.get(f'/pacemaker/api/platform/{server.server_id}', headers=authenticated[1]).status_code == 200
        assert calls == [['python3', '-c', DETECT]]
        authenticated[0]['group_id'] = 2
        assert client.get(f'/pacemaker/api/platform/{server.server_id}', headers=authenticated[1]).status_code == 404
        authenticated[0]['role'] = 4
        assert client.get(f'/pacemaker/api/platform/{server.server_id}', headers=authenticated[1]).status_code == 403
        assert len(calls) == 1
    finally:
        server.delete_instance()


def test_legacy_target_python_is_refused_before_installing():
    code, _files, calls = runtime('almalinux', '8.10')
    code['sys'] = SimpleNamespace(version_info=(3, 6, 8))
    with pytest.raises(SystemExit, match='Python 3.8 or newer'):
        code['install_packages']('cluster')
    assert not calls


@pytest.mark.parametrize('distro,version,split,package', [
    ('debian', '13', True, 'fence-agents-pve'), ('debian', '11', False, 'fence-agents'),
    ('rocky', '9.8', False, 'fence-agents-pve'),
])
def test_optional_proxmox_agent_uses_available_native_package(distro, version, split, package):
    code, _files, calls = runtime(distro, version, split_agents=split)
    code['install_packages']('cluster', fence_pve=True)
    command = next(args for args in calls if isinstance(args, list) and 'install' in args)
    assert package in command


@pytest.mark.parametrize('broken', [False, True])
def test_proxmox_agent_repair_is_narrow_backed_up_and_idempotent(tmp_path, broken):
    from pathlib import Path
    import os
    agent = tmp_path / 'fence_pve'
    library = tmp_path / 'fencing.py'
    backups = tmp_path / 'backups'
    library.write_text('# installed native fencing library')
    original = 'import sys\nsys.path.append("' + ('@FENCEAGENTSLIBDIR@' if broken else '/usr/share/fence') + '")\n'
    agent.write_text(original)
    agent.chmod(0o751)
    source = SOURCE.replace('/usr/sbin/fence_pve', str(agent)).replace('/usr/share/fence/fencing.py', str(library)).replace('/var/lib/roxy-wi/fence-agents', str(backups))
    namespace = {}
    exec(source, namespace)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout='<resource-agent name="fence_pve"/>', returncode=0)
    namespace['subprocess'] = SimpleNamespace(run=run)
    namespace['shutil'] = SimpleNamespace(which=lambda _name: None)
    assert namespace['repair_fence_pve']() is broken
    assert namespace['repair_fence_pve']() is False
    assert agent.stat().st_mode & 0o777 == 0o751
    assert '@FENCEAGENTSLIBDIR@' not in agent.read_text()
    saved = list(backups.glob('*.orig'))
    assert len(saved) == (1 if broken else 0)
    if broken:
        assert saved[0].read_text() == original
        assert saved[0].stat().st_mode & 0o777 == 0o600
    assert calls == [[str(agent), '--action', 'metadata']] * 2


def test_unknown_proxmox_packaging_defect_is_refused_without_writing(tmp_path):
    agent = tmp_path / 'fence_pve'
    original = 'import sys\nsys.path.insert(0, "@FENCEAGENTSLIBDIR@")\n'
    agent.write_text(original)
    namespace = {}
    exec(SOURCE.replace('/usr/sbin/fence_pve', str(agent)), namespace)
    with pytest.raises(SystemExit, match='Unknown fence_pve packaging defect'):
        namespace['repair_fence_pve']()
    assert agent.read_text() == original


@pytest.mark.parametrize('split_cli', [False, True])
def test_docker_witness_installs_split_cli_when_available(split_cli):
    code, _files, calls = runtime('debian','13',split_agents=split_cli)
    code['install_packages']('witness-docker')
    command=next(args for args in calls if isinstance(args,list) and 'install' in args)
    assert any(package == 'docker.io' for package in command)
    assert ('docker-cli' in command) is split_cli
    assert 'corosync' not in command and 'pacemaker' not in command
