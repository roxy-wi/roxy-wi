"""Exercise the bundled service playbook through the real local Ansible runner."""
import json
import os
from pathlib import Path
import socket
import subprocess
import threading

import pytest

from app.modules.service import installation


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Ansible requires a POSIX control node')
ROLES = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles'


def test_service_preflight_is_read_only_and_redacts_secrets(tmp_path, monkeypatch):
    if not Path('/run/systemd/system').is_dir():
        pytest.skip('The playbook targets native systemd hosts')
    if subprocess.run(['sudo', '-n', 'true'], capture_output=True).returncode:
        pytest.skip('Native package checks require passwordless sudo')
    private = tmp_path / 'ansible'
    monkeypatch.setattr(installation, 'ANSIBLE_PRIVATE_DATA_DIR', str(private))
    monkeypatch.setattr(installation, 'ANSIBLE_INVENTORY_DIR', str(private / 'inventory'))
    monkeypatch.setattr(installation, 'ANSIBLE_ROLE_SEARCH_PATHS', (str(ROLES),))
    monkeypatch.setattr(installation, '_ANSIBLE_PLAYBOOKS', {
        'roxywi_service': str(ROLES / 'roxywi_service.yml'),
    })
    monkeypatch.setattr(installation.sql, 'get_setting', lambda _: '')
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(1)
    stopped = threading.Event()
    def accept():
        while not stopped.is_set():
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            with connection:
                pass
    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    secret = 'preflight-secret-{{ 123 + 456 }}'
    inventory = {'server': {'hosts': {'localhost': {
        'ansible_connection': 'local', 'ansible_become': True,
        'roxywi_install': {
            'component': 'socket', 'stage': 'check', 'application_path': str(ROLES.parents[3]),
            'rabbit_host': '127.0.0.1', 'rabbit_port': listener.getsockname()[1],
            'environment': {'SOCKET_RABBITMQ_PASSWORD': secret},
        },
    }}}}
    try:
        stats = installation.run_ansible_locally(inventory, 'roxywi_service')
    finally:
        stopped.set()
        thread.join(timeout=3)
        listener.close()
    assert not stats['failures'] and not stats['dark']
    assert not any(stats['changed'].values())
    facts = stats['artifact_data']['roxywi_service']
    assert facts['unit'] == 'roxy-wi-socket' and facts['hostname']
    assert secret not in json.dumps(stats)
    assert list((private / 'inventory').iterdir()) == []
    for artifact in (private / 'artifacts').rglob('*.json'):
        assert secret not in artifact.read_text()
