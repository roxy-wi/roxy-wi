"""Fast read-only inspection must not hide runtime errors or expose environment."""
from types import SimpleNamespace

import pytest

from app.scripts import tool_status


@pytest.fixture
def host(monkeypatch):
    calls = []
    responses = {}
    monkeypatch.setattr(tool_status.shutil, 'which', lambda command: command if command in responses else None)
    def run(arguments, **kwargs):
        calls.append(arguments)
        assert 0 < kwargs['timeout'] <= 5
        rc, stdout, stderr = responses[arguments[0]]
        return SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)
    monkeypatch.setattr(tool_status.subprocess, 'run', run)
    return responses, calls


@pytest.mark.parametrize('engine', ['docker', 'podman'])
def test_container_status_only_requests_nonsecret_fields(host, engine):
    responses, calls = host
    responses[engine] = (0, '{"image":"ghcr.io/roxy-wi/roxy-wi-checker:5.1.0","running":true}', '')
    assert tool_status.inspect_service('checker') == dict(
        engine=engine, installed=True, version='ghcr.io/roxy-wi/roxy-wi-checker:5.1.0', state='active')
    assert calls[0][-1] == 'roxy-wi-checker' and '--format' in calls[0]
    assert '.Env' not in ' '.join(calls[0])


@pytest.mark.parametrize('manager,output,component', [
    ('rpm', '3.8.1', 'keep_alive'), ('dpkg-query', 'installed\t3.8.1', 'keep_alive'),
])
def test_native_package_and_boot_service(host, manager, output, component):
    responses, calls = host
    responses.update({manager: (0, output, ''), 'systemctl': (0, 'active\n', '')})
    result = tool_status.inspect_service(component)
    assert result == dict(engine='native', installed=True, version='3.8.1', state='active')
    assert calls[0][-1] == ('roxy-wi-keep-alive' if manager == 'dpkg-query' else 'roxy-wi-keep_alive')


def test_missing_container_falls_back_to_missing_package(host):
    responses, _ = host
    responses.update(docker=(1, '', 'Error: No such object: roxy-wi-checker'),
                     rpm=(1, 'package roxy-wi-checker is not installed', ''),
                     systemctl=(4, 'inactive\n', ''))
    assert tool_status.inspect_service('checker') == dict(
        engine='native', installed=False, version='', state='inactive')


def test_removed_debian_package_is_not_installed(host):
    responses, _ = host
    responses.update({'dpkg-query': (0, 'config-files\t5.1.0', ''), 'systemctl': (4, 'inactive', '')})
    assert not tool_status.inspect_service('checker')['installed']


def test_runtime_failure_is_not_treated_as_absent_service(host):
    responses, _ = host
    responses['docker'] = (1, '', 'Cannot connect to Docker daemon')
    with pytest.raises(RuntimeError, match='command_failed'):
        tool_status.inspect_service('checker')


def test_multiple_runtimes_are_not_silently_selected(host):
    responses, _ = host
    responses.update({engine: (0, '{"image":"image:1","running":false}', '') for engine in ('docker', 'podman')})
    with pytest.raises(RuntimeError, match='engine_conflict'):
        tool_status.inspect_service('checker')


def test_package_database_error_is_not_absence(host):
    responses, _ = host
    responses['rpm'] = (1, '', 'rpmdb open failed')
    with pytest.raises(RuntimeError, match='command_failed'):
        tool_status.inspect_service('checker')
