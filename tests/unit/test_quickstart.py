import base64
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest
from cryptography.fernet import Fernet


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('roxywi_quickstart', ROOT / 'docker' / 'quickstart.py')
quickstart = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quickstart)


def test_generated_secrets_are_valid_private_and_persistent(tmp_path):
    path = tmp_path / '.env.quickstart'
    assert quickstart.prepare_environment(path)
    original = path.read_bytes()
    values = dict(line.split('=', 1) for line in original.decode().splitlines())
    cipher = Fernet(values['ROXYWI_SECRET_PHRASE'].encode())
    encrypted = cipher.encrypt(b'saved credential')
    assert len(base64.urlsafe_b64decode(values['ROXYWI_SECRET_PHRASE'])) == 32
    assert len(values['ROXYWI_SECRET_KEY']) >= 32
    assert len(values['ROXYWI_RABBITMQ_PASSWORD']) >= 12
    assert not quickstart.prepare_environment(path)
    assert path.read_bytes() == original
    assert cipher.decrypt(encrypted) == b'saved credential'
    if os.name == 'posix':
        assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('invalid', ['ROXYWI_VERSION=quickstart\n',
                                    ''.join(f'{key}=\n' for key in quickstart.KEYS)])
def test_incomplete_environment_is_not_replaced(tmp_path, invalid):
    path = tmp_path / '.env.quickstart'
    path.write_text(invalid, encoding='utf-8')
    original = path.read_bytes()
    with pytest.raises(RuntimeError, match='Restore the existing secrets'):
        quickstart.prepare_environment(path)
    assert path.read_bytes() == original


def test_concurrent_initialization_cannot_overwrite_secrets(tmp_path):
    path = tmp_path / '.env.quickstart'

    def create():
        try:
            return quickstart.prepare_environment(path)
        except (FileExistsError, RuntimeError):
            # A concurrent writer may still be writing; a retry can read it later.
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(lambda _: create(), range(8))) == 1
    original = path.read_bytes()
    assert not quickstart.prepare_environment(path)
    assert path.read_bytes() == original


def test_shell_secrets_cannot_override_quickstart(monkeypatch):
    for key in quickstart.KEYS:
        monkeypatch.setenv(key, 'production-value')
    monkeypatch.setenv('DOCKER_HOST', 'test-docker-endpoint')
    calls = []
    monkeypatch.setattr(quickstart.subprocess, 'run', lambda args, **kwargs: calls.append((args, kwargs)))
    quickstart.run(quickstart.compose('config', '--quiet'))
    args, options = calls[0]
    assert not set(quickstart.KEYS) & set(options['env'])
    assert options['env']['DOCKER_HOST'] == 'test-docker-endpoint'
    assert options['check'] is True
    assert args[args.index('--project-name') + 1] == 'roxywi-quickstart'
    assert args[args.index('--env-file') + 1] == str(quickstart.ENV_FILE)


@pytest.mark.parametrize('version', ['2.24.4', 'v2.39.0', '5.0.0'])
def test_compose_supports_port_override(monkeypatch, version):
    monkeypatch.setattr(quickstart, 'run', lambda *a, **kw: subprocess.CompletedProcess([], 0, version))
    quickstart.check_compose_version()


@pytest.mark.parametrize('version', ['2.24.3', '1.29.2', 'unknown'])
def test_unsupported_compose_fails_before_startup(monkeypatch, version):
    monkeypatch.setattr(quickstart, 'run', lambda *a, **kw: subprocess.CompletedProcess([], 0, version))
    with pytest.raises(RuntimeError, match='2.24.4'):
        quickstart.check_compose_version()


def test_stop_keeps_volumes_and_environment(tmp_path, monkeypatch):
    path = tmp_path / '.env.quickstart'
    quickstart.prepare_environment(path)
    original = path.read_bytes()
    monkeypatch.setattr(quickstart, 'ENV_FILE', path)
    monkeypatch.setattr(quickstart, 'check_compose_version', lambda: None)
    monkeypatch.setattr(quickstart.sys, 'argv', ['quickstart.py', 'stop'])
    calls = []
    monkeypatch.setattr(quickstart, 'run', lambda args: calls.append(args))
    quickstart.main()
    assert len(calls) == 1
    assert calls[0][-1] == 'down'
    assert '--volumes' not in calls[0]
    assert path.read_bytes() == original
