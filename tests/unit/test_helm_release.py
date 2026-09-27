"""Exercise the release guard used by Actions before any registry write."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which('bash')


@unittest.skipUnless(BASH, 'Release metadata validation requires Bash')
class HelmReleaseMetadata(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        workflow = yaml.safe_load((ROOT / '.github/workflows/container.yml').read_text())
        steps = workflow['jobs']['build-and-sqlite-smoke']['steps']
        script = next(step['run'] for step in steps if step.get('id') == 'chart')
        self.script = self.root / 'metadata.sh'
        with self.script.open('w', encoding='utf-8', newline='\n') as stream:
            stream.write(script)

    def validate(self, *, tag='v9.1.0', version='9.1.0', app_version='9.1.0',
                 name='roxy-wi-charts', publish=True):
        chart = {'name': name, 'version': version, 'appVersion': app_version}
        (self.root / 'Chart.yaml').write_text(yaml.safe_dump(chart), encoding='utf-8')
        output = self.root / 'output'
        output.unlink(missing_ok=True)
        result = subprocess.run([BASH, '-euo', 'pipefail', str(self.script)], capture_output=True,
            text=True, timeout=10, env={**os.environ, 'CHART_DIR': str(self.root),
                'CHART_NAME': 'roxy-wi-charts', 'GITHUB_REF_NAME': tag,
                'PUBLISH_HELM': str(publish).lower(), 'GITHUB_OUTPUT': str(output)})
        return result, output.read_text() if output.exists() else ''

    def test_matching_stable_release(self):
        result, output = self.validate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, 'version=9.1.0\n')

    def test_branch_build_packages_without_a_release_tag(self):
        result, output = self.validate(tag='master', publish=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, 'version=9.1.0\n')

    def test_invalid_stable_tags_are_rejected(self):
        for tag in ('v9.1', 'v09.1.0', 'v9.1.0-rc.1', 'v9.1.0+build', 'v9.1.0; echo unsafe'):
            with self.subTest(tag=tag):
                result, output = self.validate(tag=tag)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('vMAJOR.MINOR.PATCH', result.stderr)
                self.assertEqual(output, '')

    def test_chart_and_application_versions_must_match_tag(self):
        for overrides in ({'version': '9.2.0'}, {'app_version': '9.0.0'}):
            with self.subTest(overrides=overrides):
                result, output = self.validate(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('must match release tag', result.stderr)
                self.assertEqual(output, '')

    def test_empty_metadata_is_rejected(self):
        for overrides in ({'version': ''}, {'app_version': ''}):
            with self.subTest(overrides=overrides):
                result, output = self.validate(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('must be set', result.stderr)
                self.assertEqual(output, '')

    def test_package_name_must_match_oci_address(self):
        result, output = self.validate(name='roxy-wi')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('configured OCI address', result.stderr)
        self.assertEqual(output, '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
