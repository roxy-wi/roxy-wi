import pytest

from app.modules.service import common


@pytest.mark.parametrize('exporter,output,version', [
    ('haproxy', 'haproxy_exporter, version 0.15.0 (branch: HEAD, revision: abc)\n', '0.15.0'),
    ('nginx', 'nginx-prometheus-exporter has version 1.5.1 built with go1.24\n', '1.5.1'),
    ('apache', 'apache_exporter, version 1.0.11 (branch: HEAD)\n', '1.0.11'),
    ('node', 'node_exporter, version 1.12.0 (branch: HEAD)\n  build date: 20261001\n', '1.12.0'),
    ('keepalived', 'keepalived_exporter 0.5.0\n', '0.5.0'),
    ('keepalived', 'keepalived_exporter, version v0.5.0 (branch: HEAD)\n', 'v0.5.0'),
    ('ha_cluster', 'ha_cluster_exporter, version 1.4.3 (branch: HEAD)\n', '1.4.3'),
    ('node', 'node_exporter, version 1.12.0-rc.1 (branch: HEAD)\n', '1.12.0-rc.1'),
])
def test_exporter_check_returns_only_version(monkeypatch, exporter, output, version):
    def ssh(server_ip, command, **kwargs):
        assert server_ip == '192.0.2.11'
        assert kwargs['rc'] == 1  # A failed command must not look like a missing exporter.
        assert '|head' not in command and '|awk' not in command
        return output

    monkeypatch.setattr(common.server_mod, 'ssh_command', ssh)
    assert common.get_exp_version('192.0.2.11', exporter) == version


@pytest.mark.parametrize('exporter', ['haproxy', 'nginx', 'apache', 'node', 'keepalived', 'ha_cluster'])
def test_missing_exporter_has_explicit_result(monkeypatch, exporter):
    monkeypatch.setattr(common.server_mod, 'ssh_command', lambda *args, **kwargs: 'no\n')
    assert common.get_exp_version('192.0.2.11', exporter) == 'no'


@pytest.mark.parametrize('output', ['', 'No', 'bash: line 1: node_exporter: command not found',
                                 'Permission denied', '<html>Sign in</html>', 'version unknown'])
def test_unrecognized_output_is_a_failed_check_not_a_version(monkeypatch, output):
    monkeypatch.setattr(common.server_mod, 'ssh_command', lambda *args, **kwargs: output)
    with pytest.raises(ValueError, match='Cannot determine exporter version'):
        common.get_exp_version('192.0.2.11', 'node')


def test_ssh_failure_is_not_reported_as_missing_exporter(monkeypatch):
    def ssh(*args, **kwargs):
        raise TimeoutError('SSH timed out')

    monkeypatch.setattr(common.server_mod, 'ssh_command', ssh)
    with pytest.raises(TimeoutError):
        common.get_exp_version('192.0.2.11', 'node')
