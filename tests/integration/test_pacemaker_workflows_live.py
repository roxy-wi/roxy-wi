"""Opt-in HTTP qualification of disposable, already registered roxy-lab clusters.

Enable ROXYWI_PACEMAKER_WORKFLOWS_LIVE=1 and point
ROXYWI_PACEMAKER_WORKFLOWS_CONFIG at a private JSON file. See
docs/corosync-pacemaker-testing.md. These tests change witness trust, restart
cluster daemons and briefly stop application resources; ordinary CI skips them.
"""
import ipaddress
import json
import os
import stat
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests

pytestmark = pytest.mark.skipif(
    os.environ.get('ROXYWI_PACEMAKER_WORKFLOWS_LIVE') != '1',
    reason='Requires explicit disposable roxy-lab HTTP workflow qualification',
)


class Lab:
    def __init__(self, path):
        try:
            config = json.loads(path.read_text())
        except (OSError, ValueError):
            pytest.fail('Cannot read the private live workflow configuration', pytrace=False)
        endpoint = urlsplit(config['base_url'])
        if endpoint.scheme not in ('http', 'https') or endpoint.username or endpoint.password:
            pytest.fail('Use an HTTP(S) lab URL without embedded credentials')
        try:
            private = ipaddress.ip_address(endpoint.hostname).is_private
        except ValueError:
            private = False
        if not private or config.get('confirmation') != 'disposable-roxy-lab':
            pytest.fail('Live workflow tests require a private endpoint and disposable-roxy-lab confirmation')
        self.settings = {key: value for key, value in config.items() if key not in ('username', 'password')}
        self.base = config['base_url'].rstrip('/')
        self.http = requests.Session()
        self.http.trust_env = False
        if config.get('ca_bundle'):
            self.http.verify = str(config['ca_bundle'])
        try:
            result = self.http.post(self.base + '/login', json={
                'login': config['username'], 'pass': config['password'], 'next': '/pacemaker',
            }, timeout=30)
        except requests.RequestException:
            pytest.fail('Lab login endpoint is unavailable; inspect connectivity without logging credentials', pytrace=False)
        if result.status_code != 200 or not self.http.cookies.get('csrf_access_token'):
            pytest.fail('Lab login failed; check the private credentials file', pytrace=False)
        self.http.headers.update({'X-CSRF-TOKEN': self.http.cookies['csrf_access_token'], 'Accept': 'application/json'})
        self.servers = {row['id']: row for row in self.call('/pacemaker/api/servers')['data']}
        all_clusters = {row['id']: row for row in self.call('/pacemaker/api')['data']}
        self.clusters = {}
        if not config['clusters']:
            pytest.fail('Configure at least one dedicated lab cluster')
        for ident in config['clusters']:
            cluster = all_clusters[ident]
            if not cluster['name'].startswith('roxy-lab') or any(
                not member['name'].startswith('roxy-lab-') for member in cluster['members']
            ):
                pytest.fail('Refusing a cluster/member without the dedicated roxy-lab name prefix')
            self.clusters[ident] = cluster
            self.healthy(ident)
        self.member_ids = {member['server_id'] for cluster in self.clusters.values() for member in cluster['members']}
        for ident in config.get('exporter_nodes', []):
            if ident not in self.member_ids:
                pytest.fail('Exporter target is not a checked lab member')
        witnesses = set(config.get('rotate_witnesses', []))
        if config.get('docker_witness'):
            witnesses.add(config['docker_witness'])
        if config.get('witness_move'):
            witnesses.update(config['witness_move'].values())
        for ident in witnesses:
            if ident in self.member_ids or not self.servers[ident]['name'].startswith('roxy-lab-'):
                pytest.fail('Refusing a witness without a separate dedicated roxy-lab server')

    def call(self, path, body=None):
        response = self.http.get(self.base + path, timeout=180) if body is None else self.http.post(
            self.base + path, json=body, timeout=180)
        if response.status_code >= 400:
            pytest.fail(f'Lab API returned HTTP {response.status_code} for {path}')
        return response.json()

    def wait(self, prefix, queued):
        deadline = time.monotonic() + 1500
        while time.monotonic() < deadline:
            state = self.call(prefix + '/tasks/' + str(queued['task_id']))['data']
            if state['status'] == 'failed':
                pytest.fail(f'Operation {state["id"]} failed; inspect its bounded GUI error and cluster state')
            if state['status'] == 'completed':
                return state
            time.sleep(1)
        pytest.fail('Lab operation exceeded the deadline; inspect its journal before retrying')

    def healthy(self, ident):
        state = self.call(f'/pacemaker/api/{ident}/status')['data']
        assert state['quorate']
        assert all(node['online'] == 'true' and node['unclean'] != 'true' for node in state['nodes'])
        return state

    def digest(self, ident):
        return self.call(f'/pacemaker/api/{ident}/config')['data']['digest']

    def witness(self, ident):
        return self.call(f'/pacemaker/api/witness/{ident}')['data']

    def install_witness(self, ident, docker):
        self.wait('/pacemaker/api/witness', self.call('/pacemaker/api/witness/install', {
            'server_id': ident, 'docker': docker,
        }))

    def checked_plan(self, plan):
        assert plan['eligible']
        if any(cluster['id'] not in self.clusters for cluster in plan.get('clusters', [])):
            pytest.fail('Declare every cluster attached to the selected witness before a live migration')
        return plan

    def trust(self, source, target, rotate=False):
        root = f'/pacemaker/api/witness/{source}'
        plan = self.checked_plan(self.call(root + f'/trust/{target}?rotate={int(rotate)}')['data'])
        self.wait('/pacemaker/api/witness', self.call(root + '/trust', {
            'target_id': target, 'rotate_ca': rotate, 'plan_digest': plan['plan_digest'], 'confirm': plan['server'],
        }))
        assert self.witness(target)['active']


@pytest.fixture(scope='module')
def lab():
    path = Path(os.environ['ROXYWI_PACEMAKER_WORKFLOWS_CONFIG'])
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        pytest.fail('The private live workflow configuration must have mode 0600')
    result = Lab(path)
    yield result
    result.http.close()


def test_exporter_and_all_daemon_restart_policies(lab):
    original_digests = {ident: lab.digest(ident) for ident in lab.clusters}
    for ident, cluster in lab.clusters.items():
        before = lab.digest(ident)
        prefix = f'/pacemaker/api/{ident}'
        original = cluster['corosync_settings'].get('autostart_policy', 'default')
        try:
            for policy in ('on-failure', 'no', 'default'):
                lab.wait(prefix, lab.call(prefix + '/autostart', {'policy': policy, 'confirm': cluster['name']}))
                observed = lab.call(prefix + '/autostart')['data']
                assert all(unit['restart'] == policy if policy != 'default' else not unit['managed']
                           for node in observed['nodes'] for unit in node['units'])
        finally:
            lab.wait(prefix, lab.call(prefix + '/autostart', {'policy': original, 'confirm': cluster['name']}))
        assert lab.digest(ident) == before
    for ident in lab.settings.get('exporter_nodes', []):
        ip = lab.servers[ident]['ip']
        queued = lab.call('/install/exporter/ha_cluster', {
            'server_ip': ip, 'exporter_v': '1.4.3', 'listen_address': ip, 'port': 9664,
        })
        deadline = time.monotonic() + 600
        for task in queued['tasks_ids']:
            while time.monotonic() < deadline:
                state = lab.call('/install/task-status/' + str(task))
                assert state['status'] != 'failed'
                if state['status'] == 'completed':
                    break
                time.sleep(1)
            else:
                pytest.fail('Exporter installation did not finish before its deadline')
        state = lab.call('/install/exporter/ha_cluster/status/' + ip)['data']
        assert state['active'] and state['pacemaker_available'] and state['corosync_available']
        assert 'ha_cluster_corosync_quorate' in state['metrics']
    assert {ident: lab.digest(ident) for ident in lab.clusters} == original_digests


def test_docker_image_refresh_and_native_round_trip(lab):
    witness = lab.settings.get('docker_witness')
    if not witness:
        pytest.skip('No disposable Docker witness configured')
    before = lab.witness(witness)
    assert before['mode'] == 'docker' and before['active']
    root = f'/pacemaker/api/witness/{witness}'
    refreshed_image = None
    for operation in ('image-upgrade', 'native'):
        plan = lab.checked_plan(lab.call(root + '/lifecycle/' + operation)['data'])
        lab.wait('/pacemaker/api/witness', lab.call(root + '/lifecycle/' + operation, {
            'plan_digest': plan['plan_digest'], 'confirm': plan['server'],
        }))
        state = lab.witness(witness)
        assert state['active'] and state['ca_fingerprint'] == before['ca_fingerprint']
        if operation == 'image-upgrade':
            refreshed_image = state['image_id']
    plan = lab.checked_plan(lab.call(root + '/migration')['data'])
    lab.wait('/pacemaker/api/witness', lab.call(root + '/migration', {
        'plan_digest': plan['plan_digest'], 'confirm': plan['server'],
    }))
    after = lab.witness(witness)
    assert after['active'] and after['mode'] == 'docker' and after['ca_fingerprint'] == before['ca_fingerprint']
    assert after['image_id'] == refreshed_image


def test_ca_rotation_on_native_and_docker_witnesses(lab):
    if not lab.settings.get('rotate_witnesses'):
        pytest.skip('No disposable witness CA rotation configured')
    for witness in lab.settings.get('rotate_witnesses', []):
        before = lab.witness(witness)
        lab.trust(witness, witness, rotate=True)
        assert lab.witness(witness)['ca_fingerprint'] != before['ca_fingerprint']
    for ident in lab.clusters:
        lab.healthy(ident)


def test_cross_host_witness_move_and_return(lab):
    move = lab.settings.get('witness_move')
    if not move:
        pytest.skip('No disposable source/target witness pair configured')
    source, target = move['source'], move['target']
    before = lab.witness(source)
    target_state = lab.witness(target)
    if not target_state['active']:
        lab.install_witness(target, target_state['mode'] == 'docker')
    lab.trust(source, target)
    assert not lab.witness(source)['active']
    lab.install_witness(source, before['mode'] == 'docker')
    lab.trust(target, source)
    after = lab.witness(source)
    assert after['active'] and after['ca_fingerprint'] == before['ca_fingerprint']
    assert not lab.witness(target)['active']


def test_planned_transport_maintenance_and_explicit_resume(lab):
    ident = lab.settings.get('transport_cluster')
    if not ident:
        pytest.skip('No disposable transport-maintenance cluster configured')
    cluster = lab.clusters[ident]
    prefix = f'/pacemaker/api/{ident}'
    before = lab.healthy(ident)
    availability = {node['name']: node['standby'] for node in before['nodes']}
    running = {resource['id'] for resource in before['resources'] if resource['active'] == 'true'}
    token = cluster['corosync_settings'].get('token', 1500)
    lab.wait(prefix, lab.call(prefix + '/transport/quiesce', {'confirm': cluster['name']}))
    try:
        plan = lab.call(prefix + f'/transport?token={token}')['data']
        assert plan['eligible']
        lab.wait(prefix, lab.call(prefix + '/transport', {
            'token': token, 'plan_digest': plan['plan_digest'], 'confirm': cluster['name'],
        }))
        state = lab.healthy(ident)
        assert all(node['standby'] == 'true' for node in state['nodes'])
        assert all(resource['active'] != 'true' for resource in state['resources']
                   if not resource['resource_agent'].startswith('stonith:'))
        assert state['quorum_details']['votes'] > 0
    finally:
        pending = lab.call(prefix + '/transport')['data'].get('pending')
        if pending:
            lab.wait(prefix, lab.call(prefix + '/transport/recover', {'confirm': cluster['name']}))
        lab.wait(prefix, lab.call(prefix + '/transport/resume', {'confirm': cluster['name']}))
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        state = lab.healthy(ident)
        active = {resource['id'] for resource in state['resources'] if resource['active'] == 'true'}
        if {node['name']: node['standby'] for node in state['nodes']} == availability and running <= active:
            return
        time.sleep(1)
    pytest.fail('Node availability did not return to the state recorded before maintenance')
