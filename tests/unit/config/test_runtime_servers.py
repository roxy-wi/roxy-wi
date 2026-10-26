import pytest

from app.modules.config import runtime


@pytest.mark.parametrize('reply', [
    '',
    "IP changed from '192.0.2.1' to '2001:db8::1', port changed from '80' to '81' by 'stats socket command'\n",
    "no need to change the addr, port changed from '80' to '81' by 'stats socket command'\n",
    "IP changed from '192.0.2.1' to '2001:db8::1', no need to change the port by 'stats socket command'\n",
    "no need to change the addr, no need to change the port by 'stats socket command'\n",
])
def test_address_change_accepts_haproxy_success_and_keeps_independent_check_port(monkeypatch, reply):
    commands = []
    monkeypatch.setattr(runtime, 'execute_runtime_command', lambda *args: commands.append(args) or reply)
    runtime.change_ip_and_port('192.0.2.10', 'web', 'one', '2001:db8::1', 81, sock_port=1999)
    assert commands == [('192.0.2.10', 1999, 'set server web/one addr 2001:db8::1 port 81')]


@pytest.mark.parametrize('reply', [
    'Permission denied', 'No such server.', 'Unknown command. Please enter one of the following commands only :',
    "IP changed from '192.0.2.1' to '192.0.2.2', can't change <port> by 'stats socket command'",
])
def test_address_change_does_not_accept_error_or_partial_response(monkeypatch, reply):
    monkeypatch.setattr(runtime, 'execute_runtime_command', lambda *args: reply)
    with pytest.raises(RuntimeError, match='rejected'):
        runtime.change_ip_and_port('192.0.2.10', 'web', 'one', '192.0.2.2', 81, sock_port=1999)


@pytest.mark.parametrize('failed_step', [0, 1, 2])
@pytest.mark.parametrize('failure', ['reject', 'timeout'])
def test_add_stops_at_first_failure_without_retry_or_enable(monkeypatch, failed_step, failure):
    commands = []
    def execute(*args):
        commands.append(args[2])
        if len(commands) - 1 == failed_step:
            if failure == 'timeout':
                raise TimeoutError('lost reply')
            return 'No such server.'
        return 'New server registered.\n' if len(commands) == 1 else ''
    monkeypatch.setattr(runtime, 'execute_runtime_command', execute)
    with pytest.raises((RuntimeError, TimeoutError)):
        runtime.add_server('192.0.2.10', 'web', 'new', '2001:db8::1', 81, True, 82, sock_port=1999)
    assert len(commands) == failed_step + 1
    assert commands[0] == 'add server web/new [2001:db8::1]:81 check port 82'


def test_add_accepts_notice_and_enables_checks_before_traffic(monkeypatch):
    commands = []
    def execute(*args):
        commands.append(args[2])
        return '[NOTICE] (123) : New server registered.\n' if len(commands) == 1 else ''
    monkeypatch.setattr(runtime, 'execute_runtime_command', execute)
    response = runtime.add_server('192.0.2.10', 'web', 'new', '192.0.2.2', 80, True, 81, sock_port=1999)
    assert response == '[NOTICE] (123) : New server registered.'
    assert commands == ['add server web/new 192.0.2.2:80 check port 81',
                        'enable health web/new', 'set server web/new state ready']


def test_runtime_resolves_inherited_server_defaults_in_file_order():
    sources = [
        'defaults base\n default-server inter 2s rise 3\n'.splitlines(keepends=True),
        ('defaults child from base\n default-server fall 4\n'
         'defaults other\n default-server inter 9s\n'
         'backend web from child\n default-server observe layer7\n').splitlines(keepends=True),
    ]
    assert runtime.server_default_options(sources, 'web').split() == [
        'inter', '2s', 'rise', '3', 'fall', '4', 'observe', 'layer7']


def test_runtime_preserves_quoted_hash_and_escapes_spaces_in_default_options():
    sources = ['backend web\n default-server ca-file "/certs/team #1/no-check.pem" # comment\n'.splitlines(keepends=True)]
    assert runtime.server_default_options(sources, 'web') == r'ca-file /certs/team\ #1/no-check.pem'


def test_runtime_config_helpers_preserve_other_servers_and_managed_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.config_common, 'get_config_dir', lambda _service: str(tmp_path))
    path = tmp_path / 'haproxy.cfg'
    path.write_text('backend web\n server one 192.0.2.1:80 port 81 check # keep\n'
                    ' server one-extra 192.0.2.2:80\n'
                    '# END Roxy-WI MANAGED backend web do not edit it directly\n'
                    '# BEGIN Roxy-WI MANAGED ring logs do not edit it directly\nring logs\n', encoding='utf-8')
    runtime.replace_server_address(str(path), 'web', 'one', '2001:db8::1', 443)
    assert 'server one [2001:db8::1]:443 port 81 check # keep' in path.read_text()
    runtime.insert_server(str(path), 'web', 'server new 192.0.2.3:80')
    text = path.read_text()
    assert text.index('server new ') < text.index('# END') < text.index('ring logs')
    runtime.delete_server(str(path), 'web', 'one')
    assert 'server one ' not in path.read_text()
    assert 'server one-extra 192.0.2.2:80' in path.read_text()


def test_maxconn_insertion_keeps_managed_marker_and_final_newline(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.config_common, 'get_config_dir', lambda _service: str(tmp_path))
    path = tmp_path / 'haproxy.cfg'
    path.write_text('global\n# END Roxy-WI MANAGED global do not edit it directly', encoding='utf-8')
    runtime.set_section_maxconn(str(path), 'global', '', 500)
    assert path.read_text() == 'global\n    maxconn 500\n# END Roxy-WI MANAGED global do not edit it directly'
