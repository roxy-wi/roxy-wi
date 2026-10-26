"""Stats server edits with real configuration and section persistence, fake SSH."""
import hashlib
from pathlib import Path

import pytest

from app.modules.db.db_model import HaproxySection
from app.modules.service.stats import haproxy_stats_config as stats_config
from app.modules.service.stats import haproxy_stats_servers as servers
from tests.fixtures.haproxy_maxconn import maxconn_host  # noqa: F401


@pytest.fixture
def server_host(maxconn_host, product, monkeypatch):
    state = maxconn_host
    state.records = []
    state.configs[state.linked.ip] += '# replica-specific configuration\n'
    for node in (product.server, state.linked):
        path = '/etc/haproxy/haproxy.cfg'
        state.records.append(HaproxySection.create(
            server_id=node.server_id, type='backend', name='web', config_path=path,
            file_id=hashlib.sha256(path.encode()).hexdigest(), config={
                'type': 'backend', 'name': 'web', 'mode': 'http', 'maxconn': 2000,
                'option': 'option http-keep-alive',
                'backend_servers': [
                    {'name': 'one', 'server': '192.0.2.30', 'port': 8080, 'port_check': 8081,
                     'maxconn': 100, 'backup': False, 'send_proxy': False},
                    {'name': 'two', 'server': '192.0.2.31', 'port': 8080, 'port_check': 8080,
                     'maxconn': 200, 'backup': True, 'send_proxy': False},
                ]}))

    def validate(ip, filename, service, **kwargs):
        assert service == 'haproxy'
        state.validations.append(ip)
        if ip == state.fail_validation:
            raise RuntimeError('private-validation-detail')
        if state.validation_hook:
            state.validation_hook(ip)

    def save(ip, filename, action, service, **kwargs):
        assert action in ('save', 'reload') and service == 'haproxy'
        kwargs['action'] = action
        assert kwargs['expected_sha256'] == hashlib.sha256(state.configs[ip].encode()).hexdigest()
        if ip == state.fail_save:
            raise OSError('private-save-detail')
        content = Path(filename).read_text(encoding='utf-8')
        state.saves.append((ip, content, kwargs))
        state.configs[ip] = content
        if action == 'save':
            return 'Haproxy'
        rows = [r for r in state.rows[ip] if r['type'] != 2 or r['pxname'] != 'web']
        prototype = next(r for r in state.rows[ip] if r['type'] == 2 and r['pxname'] == 'web')
        for line in content.splitlines():
            tokens = line.split()
            if tokens and tokens[0] == 'server':
                rows.append({**prototype, 'svname': tokens[1], 'addr': tokens[2], 'sid': 10 + len(rows)})
        state.rows[ip] = rows
        state.info[ip] = state.info[ip].replace('Pid: 100', 'Pid: 101')
        return 'Haproxy'

    def write(ip, port, command):
        assert int(port) == 1999
        state.writes.append((ip, command))
        if ip == state.fail_runtime:
            if state.reply:
                return state.reply
            raise TimeoutError('private-runtime-detail')
        parts = command.split()
        if parts[:2] == ['add', 'server']:
            assert 'no-check' not in parts, 'HAProxy does not accept no-check for dynamic servers'
            proxy, name = parts[2].split('/')
            prototype = next(r for r in state.rows[ip] if r['type'] == 2 and r['pxname'] == proxy)
            state.rows[ip].append({**prototype, 'svname': name, 'addr': parts[3], 'sid': 10 + len(state.rows[ip])})
            return 'New server registered.\n'
        if 'addr' in parts:
            proxy, name = parts[2].split('/')
            row = next(r for r in state.rows[ip] if r['pxname'] == proxy and r['svname'] == name)
            row['addr'] = servers.runtime.server_endpoint(parts[4], parts[6])
            return "IP changed from '192.0.2.30' to '%s', port changed from '8080' to '%s' by 'stats socket command'\n" % (parts[4], parts[6])
        return ''

    monkeypatch.setattr(servers.runtime, 'execute_runtime_command', write)
    monkeypatch.setattr(stats_config.config, 'validate_candidate_config', validate)
    monkeypatch.setattr(stats_config.config, 'upload_and_restart', save)
    return state
