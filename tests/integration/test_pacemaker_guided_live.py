"""Opt-in native validation of guided drafts on disposable registered clusters.

Set ROXYWI_PACEMAKER_GUIDED_LIVE=1 and ROXYWI_PACEMAKER_GUIDED_CONFIG to
a mode-0600 JSON file using the HTTP lab schema documented in
corosync-pacemaker-testing.md. This suite creates reviewed drafts and invokes
the actual managed-host crm_verify/crm_simulate path. Applying and restoring
them requires the separate ROXYWI_PACEMAKER_GUIDED_APPLY_LIVE=1 opt-in. Each
configured cluster must have a standalone lab Dummy and fencing resource.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import stat
import time
import xml.etree.ElementTree as ET
from uuid import uuid4

import pytest

from tests.integration.test_pacemaker_workflows_live import Lab


pytestmark = pytest.mark.skipif(os.environ.get('ROXYWI_PACEMAKER_GUIDED_LIVE') != '1',
    reason='Requires explicitly enabled disposable guided-editor lab qualification')


@pytest.fixture(scope='module')
def guided_lab():
    path = Path(os.environ['ROXYWI_PACEMAKER_GUIDED_CONFIG'])
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        pytest.fail('The live qualification configuration must have mode 0600')
    lab = Lab(path)
    yield lab
    lab.http.close()


@pytest.mark.parametrize('kind', ['topology', 'location-rule', 'collection', 'operation', 'bundle', 'meta'])
def test_guided_drafts_validate_on_actual_cluster_without_changing_live_cib(guided_lab, kind):
    lab = guided_lab
    for ident, cluster in lab.clusters.items():
        prefix = f'/pacemaker/api/{ident}'
        catalog = lab.call(prefix + '/guided')['data']
        before = lab.digest(ident)
        if before != catalog['base_digest']:
            pytest.fail('Lab cluster changed during discovery; retry after the other operation finishes')
        dummy = next((row for row in catalog['resources'] if row['agent'].endswith(':Dummy') and not row['parent']), None)
        fence = next((row for row in catalog['resources'] if row['agent'].startswith('stonith:')), None)
        if dummy is None or fence is None:
            pytest.fail('Prepare a standalone lab Dummy and a fencing device before qualification')
        token = 'roxy-lab-guided-' + uuid4().hex[:12]
        now = datetime.now(timezone.utc)
        if kind == 'topology':
            data = dict(node=cluster['members'][0]['name'], levels=[dict(index=1, devices=[fence['id']])])
        elif kind == 'location-rule':
            data = dict(id=token, resource=dummy['id'], score='100', conditions=[
                dict(attribute='#uname', value=cluster['members'][0]['name']),
                dict(kind='date', start=(now-timedelta(hours=1)).isoformat(), end=(now+timedelta(hours=1)).isoformat())])
        elif kind == 'collection':
            data = dict(id=token, kind='group', members=[dummy['id']])
        elif kind == 'operation':
            existing = next((row for row in catalog['operations'] if row['resource'] == dummy['id'] and row['name'] == 'monitor'), None)
            data = dict(existing, timeout='25s') if existing else dict(resource=dummy['id'], name='monitor', interval='17s', timeout='15s')
        elif kind == 'bundle':
            data = dict(id=token, engine='podman', image='docker.io/library/alpine:3.21', network='host')
        else:
            data = dict(resource=dummy['id'], values={'resource-stickiness': '100'})
        queued = lab.call(prefix + '/guided', dict(base_digest=before, kind=kind, data=data))
        change = lab.call(prefix + '/changes/' + str(queued['id']))['data']
        assert change['status'] == 'draft'
        lab.wait(prefix, lab.call(prefix + '/changes/' + str(queued['id']) + '/validate', {}))
        assert lab.call(prefix + '/changes/' + str(queued['id']))['data']['status'] == 'validated'
        assert lab.digest(ident) == before
        lab.healthy(ident)


def configuration_digest(xml):
    root = ET.fromstring(xml)
    value = ET.canonicalize(ET.tostring(root.find('configuration'), encoding='unicode'), strip_text=True)
    return hashlib.sha256(value.encode()).hexdigest()


def settle(lab, ident, resource=None):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        state = lab.healthy(ident)
        matches = [row for row in state['resources'] if row['target_id'] == resource]
        if not state['failures'] and (resource is None or matches and all(row['active'] == 'true' and row['failed'] != 'true' for row in matches)):
            return
        time.sleep(2)
    pytest.fail('The applied lab workload did not become healthy; inspect its GUI journal')


@pytest.mark.skipif(os.environ.get('ROXYWI_PACEMAKER_GUIDED_APPLY_LIVE') != '1',
    reason='Applying and restoring live CIB changes requires a second explicit opt-in')
@pytest.mark.parametrize('kind', ['topology', 'location-rule', 'collection', 'operation', 'bundle', 'meta'])
def test_guided_apply_and_reviewed_restore_on_disposable_cluster(guided_lab, kind):
    lab = guided_lab
    for ident, cluster in lab.clusters.items():
        prefix = f'/pacemaker/api/{ident}'
        catalog = lab.call(prefix + '/guided')['data']
        original = lab.call(prefix + '/config')['data']
        if original['digest'] != catalog['base_digest']:
            pytest.fail('Cluster changed during discovery; no live test was applied')
        dummy = next((row for row in catalog['resources'] if row['agent'].endswith(':Dummy') and not row['parent']), None)
        fence = next((row for row in catalog['resources'] if row['agent'].startswith('stonith:')), None)
        if dummy is None or fence is None:
            pytest.fail('Prepare a standalone lab Dummy and a fencing device')
        token = 'roxy-lab-applied-' + uuid4().hex[:12]
        now = datetime.now(timezone.utc)
        if kind == 'topology':
            data = dict(node=cluster['members'][0]['name'], levels=[dict(index=1, devices=[fence['id']])])
        elif kind == 'location-rule':
            data = dict(id=token, resource=dummy['id'], score='100', conditions=[
                dict(attribute='#uname', value=cluster['members'][0]['name']),
                dict(kind='date', start=(now-timedelta(hours=1)).isoformat(), end=(now+timedelta(hours=1)).isoformat())])
        elif kind == 'collection':
            data = dict(id=token, kind='group', members=[dummy['id']])
        elif kind == 'operation':
            existing = next((row for row in catalog['operations'] if row['resource'] == dummy['id'] and row['name'] == 'monitor'), None)
            data = dict(existing, timeout='27s') if existing else dict(resource=dummy['id'], name='monitor', interval='17s', timeout='15s')
        elif kind == 'bundle':
            data = dict(id=token, engine='podman', image='docker.io/library/alpine:3.21',
                network='host', run_command='/bin/sleep 3600')
        else:
            data = dict(resource=dummy['id'], values={'resource-stickiness': '100'})
        queued = lab.call(prefix + '/guided', dict(base_digest=original['digest'], kind=kind, data=data))
        change_id = queued['id']
        change = lab.call(prefix + '/changes/' + str(change_id))['data']
        expected = configuration_digest(change['xml'])
        if expected == original['digest']:
            pytest.fail('The live fixture would not change configuration; select another disposable fixture')
        # CIBs can contain fencing credentials. Keep recovery only beside the
        # operator's private lab file, outside the checkout and test output.
        recovery = Path(os.environ['ROXYWI_PACEMAKER_GUIDED_CONFIG']).parent / (token + '.recovery.xml')
        descriptor = os.open(recovery, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(original['xml'])
        try:
            lab.wait(prefix, lab.call(prefix + f'/changes/{change_id}/validate', {}))
            lab.wait(prefix, lab.call(prefix + f'/changes/{change_id}/apply', {}))
            if lab.digest(ident) != expected:
                pytest.fail('The applied configuration differs from the reviewed candidate')
            settle(lab, ident, token if kind == 'bundle' else dummy['id'])
        finally:
            observed = lab.digest(ident)
            if observed == expected:
                restore = lab.call(prefix + f'/changes/{change_id}/restore', {})['id']
                lab.wait(prefix, lab.call(prefix + f'/changes/{restore}/validate', {}))
                lab.wait(prefix, lab.call(prefix + f'/changes/{restore}/apply', {}))
            elif observed != original['digest']:
                pytest.fail('Concurrent configuration change: recovery retained in the private lab directory; review manually')
            if lab.digest(ident) != original['digest']:
                pytest.fail('Original configuration was not restored; inspect the private recovery and GUI journal')
            settle(lab, ident, dummy['id'])
            if kind == 'bundle':
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    if not any(row['target_id'] == token for row in lab.healthy(ident)['resources']):
                        break
                    time.sleep(2)
                else:
                    pytest.fail('The temporary bundle was not removed after restoring the original CIB')
            recovery.unlink()
