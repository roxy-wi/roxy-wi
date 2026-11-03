"""Synthetic HAProxy hosts; only SSH and Runtime API cross-process I/O is replaced."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.db.db_model import Setting
from app.modules.service import haproxy_lists as lists
from app.modules.service.haproxy_list_models import ListIdentity, entries
from app.scripts import haproxy_lists as files


@pytest.fixture
def list_hosts(product, monkeypatch):
    Setting.update(value='/etc/haproxy').where(Setting.param == 'haproxy_dir').execute()
    Setting.update(value='/etc/haproxy/haproxy.cfg').where(Setting.param == 'haproxy_config_path').execute()
    state = SimpleNamespace(nodes={}, calls=[], fail_file=set(), reject_commit=set(), lose_commit=set())

    def add(node, *, loaded=True):
        for parameter in ('haproxy_dir', 'haproxy_config_path', 'haproxy_sock_port'):
            template = Setting.get(Setting.param == parameter, Setting.group_id == 1)
            Setting.get_or_create(param=parameter, group_id=int(node.group_id), defaults={
                'value': template.value, 'section': template.section, 'desc': template.desc})
        root = product.root / ('host-' + str(node.server_id))
        (root / 'black').mkdir(parents=True)
        (root / 'black/allowed.lst').write_text('192.0.2.1\n', encoding='utf-8')
        state.nodes[node.ip] = SimpleNamespace(root=root, loaded=loaded, pid=100 + node.server_id,
            active=['192.0.2.1'], versions={}, next_version=0,
            config='frontend public\n    acl blocked src -f /etc/haproxy/black/allowed.lst\n' if loaded else 'frontend public\n')
        return state.nodes[node.ip]

    state.add = add
    add(product.server)
    local = lists.local_path(1, ListIdentity(color='black', name='allowed.lst'))
    files.write_file(local, '192.0.2.1\n')
    state.local = local
    monkeypatch.setattr(lists.haproxy_files, 'discover_sources', lambda *args, **kwargs:
        {'state': 'ready', 'files': ['/etc/haproxy/haproxy.cfg']})
    monkeypatch.setattr(lists.common, 'logging', lambda *args, **kwargs: None)

    def remote(self, argv, *, data, **kwargs):
        data = json.loads(data)
        host = state.nodes[self.server.ip]
        state.calls.append((self.server.ip, 'file:' + data['operation']))
        if data['operation'] == 'inspect':
            result = dict(runtime_root='/etc/haproxy', configs={'/etc/haproxy/haproxy.cfg': host.config},
                          files=[{'color': path.parent.name, 'name': path.name} for path in host.root.glob('*/*.lst')])
            if 'name' in data:
                result['content'] = files.read_file(host.root / data['color'] / data['name'])
            return json.dumps(result)
        if self.server.ip in state.fail_file:
            raise OSError('Synthetic SSH failure')
        if data.get('expected_configs', {}).get('/etc/haproxy/haproxy.cfg') != files.digest(host.config):
            return json.dumps({'error': 'changed'})
        data.update(root=str(host.root), expected_configs={})
        return json.dumps(files.change_file(data))

    def runtime(address, port, command, **kwargs):
        host = state.nodes[address]
        state.calls.append((address, command))
        if command == 'show info':
            return f'Pid: {host.pid}\nUptime_sec: 100\nVersion: 3.2.0\n'
        if command == 'show acl':
            return '# id (file) description\n' + ('0 (/etc/haproxy/black/allowed.lst) pattern loaded from file\n' if host.loaded else '')
        if command == 'show map':
            return '# id (file) description\n'
        if command.startswith('show acl '):
            tokens = command.split()
            values = host.versions[tokens[2][1:]] if tokens[2].startswith('@') else host.active
            return '\n'.join(f'0x{number:x} {value}' for number, value in enumerate(values, 1))
        if command.startswith('prepare acl'):
            host.next_version += 1
            version = str(host.next_version)
            host.versions[version] = []
            return 'New version created: ' + version + '\n'
        if command.startswith('add acl'):
            for item in command.split(';'):
                tokens = item.split()
                host.versions[tokens[2][1:]].append(tokens[-1])
            return '\n'
        if command.startswith('commit acl'):
            if address in state.reject_commit:
                return 'Transaction rejected\n'
            host.active = host.versions[command.split()[2][1:]][:]
            if address in state.lose_commit:
                raise TimeoutError('Synthetic response lost after application')
            return '\n'
        raise AssertionError(command)

    monkeypatch.setattr(lists.Remote, 'run', remote)
    monkeypatch.setattr(lists, 'execute_runtime_command', runtime)
    return state
