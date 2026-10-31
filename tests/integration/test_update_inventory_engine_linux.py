"""Opt-in real engine qualification; also runnable with system Python 3.9 on EL.

ROXYWI_TEST_CONTAINER_INVENTORY=1 ROXYWI_TEST_INVENTORY_ENGINE=podman \
    python3 tests/integration/test_update_inventory_engine_linux.py -v

Fixtures test artifact metadata/state, not monitoring or Auto Start behavior.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('ROXYWI_TEST_CONTAINER_INVENTORY') == '1',
                     'Enable ROXYWI_TEST_CONTAINER_INVENTORY=1 on an isolated Linux engine host')
class InventoryEngineQualification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = os.environ.get('ROXYWI_TEST_INVENTORY_ENGINE', 'podman')
        if cls.engine not in ('docker', 'podman') or not shutil.which(cls.engine):
            raise unittest.SkipTest('Requested engine is unavailable')
        cls.project = 'roxywi-inventory-probe-' + uuid.uuid4().hex[:10]
        cls.image = 'localhost/' + cls.project + ':9.8.7'
        cls.unversioned = 'localhost/' + cls.project + ':unversioned'
        cls.temporary = tempfile.TemporaryDirectory(prefix=cls.project)
        cls.root = Path(cls.temporary.name).resolve()
        cls.containers = []
        collector_path = Path(__file__).resolve().parents[2] / 'docker/collect_service_inventory.py'
        spec = importlib.util.spec_from_file_location('inventory_engine_collector', collector_path)
        cls.collector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.collector)
        cls.addClassCleanup(cls.cleanup)
        (cls.root/'Dockerfile').write_text(
            'FROM docker.io/library/busybox:1.36.1\nARG VERSION\n'
            'LABEL org.opencontainers.image.version=$VERSION\nCMD ["sleep","600"]\n')
        (cls.root/'Dockerfile.unversioned').write_text(
            'FROM docker.io/library/busybox:1.36.1\nCMD ["sleep","600"]\n')
        cls.cli('build', '-t', cls.image, '--build-arg', 'VERSION=9.8.7', str(cls.root))
        cls.cli('build', '-t', cls.unversioned, '-f', str(cls.root/'Dockerfile.unversioned'), str(cls.root))

    @classmethod
    def cli(cls, *args):
        result = subprocess.run([cls.engine, *args], text=True, capture_output=True, timeout=180)
        if result.returncode:
            raise AssertionError('Engine command failed: '+str(args[:2])+'\n'+result.stderr[-2000:])
        return result.stdout

    @classmethod
    def cleanup(cls):
        for name in cls.containers:
            subprocess.run([cls.engine, 'rm', '-f', name], capture_output=True)
        for image in (cls.image, cls.unversioned):
            subprocess.run([cls.engine, 'image', 'rm', image], capture_output=True)
        cls.temporary.cleanup()

    def create(self, service, versioned=True, unrelated=False):
        name = self.project + '-' + service + '-' + uuid.uuid4().hex[:6]
        self.cli('run','-d','--name',name,'--network','none','--memory','16m',
                 '--label','com.docker.compose.project='+('unrelated' if unrelated else self.project),
                 '--label','com.docker.compose.service='+service,
                 '-e','INVENTORY_TEST_PRIVATE=must-not-publish',
                 self.image if versioned else self.unversioned)
        self.containers.append(name)
        return name

    def record(self, name):
        records = self.collector.collect_containers(self.engine)
        return next(item for item in records if item.get('container') == name)

    def test_running_then_stopped_container_preserves_deployed_version(self):
        name = self.create('keep_alive')
        record = self.record(name)
        self.assertEqual(record['service'], 'roxy-wi-keep_alive')
        self.assertEqual(record['version'], '9.8.7')
        self.assertTrue(record['running'])
        self.cli('stop','--time','1',name)
        stopped = self.record(name)
        self.assertEqual(stopped['version'], '9.8.7')
        self.assertFalse(stopped['running'])

    def test_unversioned_artifact_is_not_a_bootstrap_version(self):
        record = self.record(self.create('prometheus-exporter', versioned=False))
        self.assertEqual(record['service'], 'roxy-wi-prometheus-exporter')
        self.assertIsNone(record['version'])
        self.assertTrue(record['running'])

    def test_published_snapshot_never_contains_container_environment(self):
        name = self.create('metrics')
        output = self.root/'runtime'/'inventory.json'
        self.collector.publish(output, self.collector.collect_containers(self.engine))
        raw = output.read_text()
        self.assertNotIn('must-not-publish', raw)
        self.assertNotIn('INVENTORY_TEST_PRIVATE', raw)
        snapshot = json.loads(raw)
        self.assertTrue(snapshot['complete'])
        self.assertTrue(any(item.get('container') == name for item in snapshot['services']))
        self.assertEqual(output.stat().st_mode & 0o777, 0o640)

    def test_unrelated_compose_service_is_not_a_roxy_worker(self):
        name = self.create('checker', unrelated=True)
        records = self.collector.collect_containers(self.engine)
        self.assertFalse(any(item.get('container') == name for item in records))


if __name__ == '__main__':
    unittest.main()
