from pathlib import Path
import shlex
import socket
from types import SimpleNamespace

import pytest
from flask import g

from app.modules.config import runtime
from app.modules.service import haproxy as haproxy_service
from app.modules.service import haproxy_runtime


class FakeRuntimeSocket:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = b''
        self.shutdown_mode = None
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendall(self, data):
        self.sent += data

    def shutdown(self, mode):
        self.shutdown_mode = mode

    def recv(self, _size):
        return self.responses.pop(0) if self.responses else b''


@pytest.mark.security
def test_runtime_client_sends_one_line_without_netcat(monkeypatch):
    connection = FakeRuntimeSocket([b'backend-a\n', b'backend-b\n'])
    connections = []
    monkeypatch.setattr(
        haproxy_runtime.socket,
        'create_connection',
        lambda address, timeout: connections.append((address, timeout)) or connection,
    )

    response = haproxy_runtime.execute_runtime_command(
        '192.0.2.20', 1999, 'show backend', timeout=3
    )

    assert response == 'backend-a\nbackend-b\n'
    assert connection.sent == b'show backend\n'
    assert connection.shutdown_mode == socket.SHUT_WR
    assert connections == [(('192.0.2.20', 1999), 3)]


@pytest.mark.security
def test_runtime_client_rejects_command_separator_newline(monkeypatch):
    monkeypatch.setattr(
        haproxy_runtime.socket,
        'create_connection',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('socket must not open')),
    )

    with pytest.raises(ValueError, match='one non-empty line'):
        haproxy_runtime.execute_runtime_command(
            '192.0.2.20', 1999, 'show info\nshutdown sessions server',
        )


@pytest.mark.security
def test_runtime_client_limits_response_size(monkeypatch):
    connection = FakeRuntimeSocket([b'oversized'])
    monkeypatch.setattr(haproxy_runtime.socket, 'create_connection', lambda *args, **kwargs: connection)

    with pytest.raises(RuntimeError, match='too large'):
        haproxy_runtime.execute_runtime_command(
            '192.0.2.20', 1999, 'show info', response_limit=4
        )


@pytest.mark.security
def test_runtime_client_sends_certificate_payload_with_terminator(monkeypatch):
    connection = FakeRuntimeSocket([b'Transaction created'])
    monkeypatch.setattr(haproxy_runtime.socket, 'create_connection', lambda *args, **kwargs: connection)
    payload = '-----BEGIN CERTIFICATE-----\nY2VydA==\n-----END CERTIFICATE-----\n'
    haproxy_runtime.execute_runtime_command('192.0.2.20', 1999, 'set ssl cert /tls/site.pem', payload=payload)
    assert connection.sent == ('set ssl cert /tls/site.pem <<\n' + payload + '\n').encode()


@pytest.mark.security
@pytest.mark.parametrize('command,payload', [
    ('show info', 'certificate'),
    ('set ssl cert /tls/site.pem; shutdown sessions server', 'certificate'),
    ('set ssl cert /tls/site.pem', 'certificate\n\nshutdown sessions server'),
    ('set ssl cert /tls/site.pem', 'certificate\r\n\r\nshow info'),
])
def test_runtime_certificate_payload_cannot_introduce_another_command(monkeypatch, command, payload):
    monkeypatch.setattr(haproxy_runtime.socket, 'create_connection',
                        lambda *args, **kwargs: pytest.fail('Invalid payload opened a socket'))
    with pytest.raises(ValueError):
        haproxy_runtime.execute_runtime_command('192.0.2.20', 1999, command, payload=payload)


@pytest.mark.security
def test_unix_socket_runtime_command_quotes_user_input(app, monkeypatch):
    commands = []
    monkeypatch.setattr(haproxy_service.server_sql, 'get_server_by_ip', lambda _: SimpleNamespace(server_id=1))
    from app.modules.db import service as service_sql
    monkeypatch.setattr(service_sql, 'select_service_setting', lambda *args: '0')
    backend = "backend one'; touch /tmp/pwned"
    settings = {
        'server_state_file': '/var/lib/roxy wi/server.state',
        'haproxy_sock': '/run/haproxy admin.sock',
    }
    monkeypatch.setattr(
        haproxy_service.sql,
        'get_setting',
        lambda setting, **kwargs: settings[setting],
    )
    monkeypatch.setattr(
        haproxy_service.server_mod,
        'ssh_command',
        lambda server, command, **kwargs: commands.append((server, command, kwargs)) or 'runtime output',
    )

    with app.test_request_context('/runtimeapi/action/192.0.2.20'):
        g.user_params = {'group_id': 7}
        response = haproxy_service.runtime_command('192.0.2.20', 'show', backend, '')

    assert response == 'runtime output'
    server, command, kwargs = commands[0]
    send_command, socket_command = command.split(' | ', 1)
    assert server == '192.0.2.20'
    assert shlex.split(send_command) == ['printf', '%s\\n', f'show {backend}']
    assert shlex.split(socket_command) == ['sudo', 'socat', 'stdio', '/run/haproxy admin.sock']
    assert kwargs == {'show_log': '1'}


@pytest.fixture()
def haproxy_config(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.config_common, 'get_config_dir', lambda _service: str(tmp_path))
    config_path = tmp_path / 'haproxy.cfg'
    config_path.write_text(
        'global\n'
        '    maxconn 4000\n'
        '\n'
        'defaults\n'
        '    mode http\n'
        '\n'
        'frontend public\n'
        '    bind :443\n'
        '    maxconn 2000\n'
        '\n'
        'backend api\n'
        '    server api-1 10.0.0.10:8080 check maxconn 100\n',
        encoding='utf-8',
    )
    return config_path


@pytest.mark.security
def test_runtime_config_edits_do_not_invoke_sed(haproxy_config):
    runtime.set_section_maxconn(str(haproxy_config), 'global', '', 5000)
    runtime.set_section_maxconn(str(haproxy_config), 'frontend', 'public', 2500)
    runtime.set_server_maxconn(str(haproxy_config), 'api', 'api-1', 150)

    config = haproxy_config.read_text(encoding='utf-8')
    assert 'maxconn 5000' in config
    assert 'maxconn 2500' in config
    assert 'server api-1 10.0.0.10:8080 check maxconn 150' in config


@pytest.mark.security
def test_runtime_list_path_cannot_escape_group_directory(tmp_path):
    group_directory = tmp_path / 'lists' / '7' / 'white'
    group_directory.mkdir(parents=True)

    assert runtime._list_file_path(str(tmp_path), 7, 'white/allowed.lst') == group_directory / 'allowed.lst'

    invalid_names = (
        'allowed.lst',
        '../other-group.lst',
        'white/../../other-group.lst',
        'white\\..\\other-group.lst',
        'other/allowed.lst',
        'white/not-a-list.txt',
        'white/name with spaces.lst',
    )
    for invalid_name in invalid_names:
        with pytest.raises(ValueError):
            runtime._list_file_path(str(tmp_path), 7, invalid_name)


@pytest.mark.security
def test_runtime_config_path_cannot_escape_config_directory(tmp_path, monkeypatch):
    config_directory = tmp_path / 'configs'
    config_directory.mkdir()
    monkeypatch.setattr(runtime.config_common, 'get_config_dir', lambda _service: str(config_directory))

    allowed = config_directory / 'haproxy.cfg'
    assert runtime._runtime_config_path(str(allowed)) == allowed.resolve()

    for invalid_path in (
        tmp_path / 'haproxy.cfg',
        config_directory / '..' / 'outside.cfg',
        config_directory / 'name with spaces.cfg',
    ):
        with pytest.raises(ValueError):
            runtime._runtime_config_path(str(invalid_path))


@pytest.mark.security
def test_runtime_module_has_no_legacy_local_shell_execution():
    source = Path(runtime.__file__).read_text(encoding='utf-8')

    assert 'subprocess_execute' not in source
    assert '|nc ' not in source
    assert 'sed -' not in source
