"""Managed nodes with real Stats parsing and configuration edits, fake transports."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.db.db_model import Server, Setting
from app.modules.service import haproxy_stats, haproxy_stats_maxconn as maxconn
from tests.fixtures.haproxy_stats import INFO, ROWS, stats_csv

CONFIG = ('global\n    maxconn 2000\ndefaults\n    mode http\n'
          'frontend public\n    bind :80\n    maxconn 2000\n'
          'backend web\n    server one 192.0.2.30:8080 check maxconn 100 # maxconn 99 comment\n'
          '    server two 192.0.2.31:8080 check\n')


@pytest.fixture
def maxconn_host(product, monkeypatch):
    linked = Server.create(server_id=33, hostname='Replica', ip='192.0.2.33', group_id=1, cred_id=11, haproxy=1, master=product.server.server_id)
    nodes = (product.server.ip, linked.ip)
    state = SimpleNamespace(linked=linked, rows={ip: [dict(row) for row in ROWS] for ip in nodes},
                            info={ip: INFO + 'Hard_maxconn: 2000\n' for ip in nodes},
                            configs={ip: CONFIG for ip in nodes}, writes=[], saves=[], validations=[],
                            fail_runtime=None, fail_save=None, fail_validation=None, validation_hook=None, reply='')
    Setting.update(value='1999').where(Setting.param == 'haproxy_sock_port', Setting.group_id == 1).execute()
    folder = product.root / 'configs'
    folder.mkdir()
    monkeypatch.setattr(maxconn.config_common, 'get_config_dir', lambda _service: str(folder))
    def read(ip, port, command):
        assert int(port) == 1999
        return stats_csv(state.rows[ip]) if command == 'show stat' else state.info[ip]
    def write(ip, port, command):
        assert int(port) == 1999
        state.writes.append((ip, command))
        if ip == state.fail_runtime:
            if state.reply:
                return state.reply
            raise TimeoutError('private-runtime-detail')
        parts = command.split()
        scope, value = parts[2], int(parts[-1])
        if scope == 'global':
            state.info[ip] = state.info[ip].replace('Maxconn: 2000', f'Maxconn: {value}')
        else:
            for row in state.rows[ip]:
                if (scope == 'frontend' and row['type'] == 0 and row['pxname'] == parts[3]
                        or scope == 'server' and row['type'] == 2 and row['pxname'] + '/' + row['svname'] == parts[3]):
                    row['slim'] = value
        return ''
    def download(ip, filename, *args, **kwargs):
        Path(filename).write_bytes(state.configs[ip].encode('utf-8'))
    def validate(ip, filename, service):
        assert service == 'haproxy'
        state.validations.append(ip)
        if ip == state.fail_validation:
            raise RuntimeError('private-validation-detail')
        if state.validation_hook:
            state.validation_hook(ip)
    def save(ip, filename, action, service, **kwargs):
        assert action == 'save' and service == 'haproxy'
        assert kwargs['expected_sha256'] == hashlib.sha256(state.configs[ip].encode()).hexdigest(), 'Concurrent config change'
        if ip == state.fail_save:
            raise OSError('private-save-detail')
        state.configs[ip] = Path(filename).read_text(encoding='utf-8')
        state.saves.append((ip, filename, kwargs))
        return 'Haproxy'
    monkeypatch.setattr(haproxy_stats, 'execute_runtime_command', read)
    monkeypatch.setattr(maxconn, 'execute_runtime_command', write)
    monkeypatch.setattr(maxconn.config, 'get_config', download)
    monkeypatch.setattr(maxconn.config, 'validate_candidate_config', validate)
    monkeypatch.setattr(maxconn.config, 'upload_and_restart', save)
    return state
