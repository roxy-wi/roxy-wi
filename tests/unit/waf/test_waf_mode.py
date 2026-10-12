import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.modules.roxywi import waf_rule_file as remote


@pytest.fixture
def configuration(tmp_path):
    root = tmp_path / 'custom proxy/waf'
    root.mkdir(parents=True)
    path = root / 'modsecurity.conf'
    path.write_bytes(b'# settings\nSecRuleEngine On\nInclude rules.conf\n')
    return path


@pytest.mark.parametrize('mode', remote.WAF_MODES)
@pytest.mark.parametrize('original', [
    b'SecRuleEngine Off\n', b'\tSecRuleEngine\tOff  # note\r\n',
    b'  secruleengine "Off"', b"SecRuleEngine 'Off'\n",
])
def test_mode_changes_preserve_other_settings_comments_and_format(configuration, original, mode):
    prefix = b'# SecRuleEngine On is documented here\nSecAuditEngine RelevantOnly\n'
    configuration.write_bytes(prefix + original)
    remote.set_mode(configuration, mode)
    assert configuration.read_bytes() == prefix + original.replace(b'Off', mode.encode())
    assert remote.read_mode(configuration) == mode
    modified = configuration.stat().st_mtime_ns
    remote.set_mode(configuration, mode)
    assert configuration.stat().st_mtime_ns == modified
    assert not list(configuration.parent.glob('.roxywi-waf-*'))


@pytest.mark.parametrize('original', [
    b'', b'# SecRuleEngine On\n', b'SecRuleEngine On\nSecRuleEngine Off\n',
    b'SecRuleEngine On\nsecruleengine On\n', b'SecRuleEngine\n', b'SecRuleEngine invalid\n',
    b'SecRuleEngine On unexpected\n', b'SecRuleEngine "On\n', b'SecRuleEngine \\\nOn\n',
    b'<IfModule mod_security2.c>\nSecRuleEngine On\n</IfModule>\n',
    b'SecRule ARGS "@rx test" \\\nSecRuleEngine On\n',
])
def test_ambiguous_missing_or_malformed_mode_never_reports_success(configuration, original):
    configuration.write_bytes(original)
    with pytest.raises(remote.RuleConflict):
        remote.read_mode(configuration)
    with pytest.raises(remote.RuleConflict):
        remote.set_mode(configuration, 'DetectionOnly')
    assert configuration.read_bytes() == original


def test_continuation_text_is_not_treated_as_another_mode_directive(configuration):
    original = b'SecRule ARGS "@rx test" \\\nSecRuleEngine Off\nSecRuleEngine On\n'
    configuration.write_bytes(original)
    remote.set_mode(configuration, 'DetectionOnly')
    assert configuration.read_bytes() == original.replace(b'SecRuleEngine On', b'SecRuleEngine DetectionOnly')


@pytest.mark.parametrize('mode', ['', 'on', 'Invalid', 'On;id', None])
def test_invalid_mode_is_rejected_before_file_access(tmp_path, mode):
    with pytest.raises(ValueError, match='Unsupported WAF mode'):
        remote.set_mode(tmp_path / 'missing', mode)


def test_external_edit_is_not_overwritten(configuration, monkeypatch):
    copy = remote.shutil.copy2

    def change_file(*args):
        result = copy(*args)
        configuration.write_bytes(b'# external edit\nSecRuleEngine Off\n')
        return result

    monkeypatch.setattr(remote.shutil, 'copy2', change_file)
    with pytest.raises(remote.RuleConflict):
        remote.set_mode(configuration, 'DetectionOnly')
    assert configuration.read_bytes() == b'# external edit\nSecRuleEngine Off\n'
    assert not list(configuration.parent.glob('.roxywi-waf-*'))


def test_failed_atomic_replace_preserves_original_and_cleans_temporary_file(configuration, monkeypatch):
    original = configuration.read_bytes()

    def fail(*args):
        raise OSError('synthetic disk failure')

    monkeypatch.setattr(remote.os, 'replace', fail)
    with pytest.raises(OSError, match='synthetic'):
        remote.set_mode(configuration, 'Off')
    assert configuration.read_bytes() == original
    assert not list(configuration.parent.glob('.roxywi-waf-*'))


@pytest.mark.skipif(os.name != 'posix', reason='Unix metadata and symlinks')
def test_metadata_is_preserved_and_linked_configuration_is_rejected(configuration):
    configuration.chmod(0o640)
    before = configuration.stat()
    remote.set_mode(configuration, 'Off')
    after = configuration.stat()
    assert (before.st_mode, before.st_uid, before.st_gid) == (after.st_mode, after.st_uid, after.st_gid)
    original = configuration.with_name('original.conf')
    configuration.rename(original)
    configuration.symlink_to(original)
    with pytest.raises(remote.RuleConflict):
        remote.set_mode(configuration, 'On')
    assert b'SecRuleEngine Off' in original.read_bytes()


def test_standalone_mode_commands_confirm_only_completed_operations(configuration):
    script = str(Path(remote.__file__))
    for arguments in [('set-mode', str(configuration), 'DetectionOnly'), ('read-mode', str(configuration))]:
        result = subprocess.run([sys.executable, script, *arguments], capture_output=True, text=True, timeout=10, check=True)
        assert json.loads(result.stdout) == {'status': 'ok', 'mode': 'DetectionOnly'}
    configuration.write_bytes(b'# mode missing\n')
    result = subprocess.run([sys.executable, script, 'set-mode', str(configuration), 'On'],
                            capture_output=True, text=True, timeout=10, check=True)
    assert json.loads(result.stdout) == {'status': 'conflict'}
