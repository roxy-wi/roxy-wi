import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def smoke(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'container_health_smoke.py'
    spec = importlib.util.spec_from_file_location('container_health_smoke', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clock = [0]

    def sleep(seconds):
        clock[0] += seconds

    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))
    return module


def test_startup_requires_consecutive_successes(smoke):
    results = iter([True, False, True, True, True])
    calls = []

    def probe():
        calls.append(True)
        return next(results)

    smoke.wait_for(probe, 'web startup', consecutive=3)
    assert len(calls) == 5


def test_startup_wait_has_a_deadline(smoke):
    with pytest.raises(AssertionError, match='Timed out: web startup'):
        smoke.wait_for(lambda: False, 'web startup', timeout=6, consecutive=3)


def test_broker_outage_checks_web_beyond_cached_sample_lifetime(smoke, monkeypatch):
    samples = []
    monkeypatch.setattr(smoke, 'probe', lambda _: samples.append(smoke.time.monotonic()) or True)
    smoke.assert_web_stays_ready('test-web')
    assert len(samples) > 1
    assert samples[-1] - samples[0] > 15


def test_broker_outage_does_not_retry_away_a_web_failure(smoke, monkeypatch):
    samples = []

    def probe(_):
        samples.append(smoke.time.monotonic())
        return len(samples) == 1

    monkeypatch.setattr(smoke, 'probe', probe)
    with pytest.raises(AssertionError, match='must not require RabbitMQ'):
        smoke.assert_web_stays_ready('test-web')
    assert len(samples) == 2


def test_failed_probe_reports_its_original_response(smoke, monkeypatch, capsys):
    commands = []

    def docker(*args, **kwargs):
        commands.append(args)
        return subprocess.CompletedProcess(args, 1, 'HTTP 503: {"database": "check pending"}', '')

    monkeypatch.setattr(smoke, 'docker', docker)
    assert not smoke.probe('test-web')
    assert len(commands) == 1
    assert 'HTTP 503: {"database": "check pending"}' in capsys.readouterr().out
