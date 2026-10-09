import os
import stat

import pytest

from app.modules.roxywi import waf_rule_file as remote


REQUEST_ID = 'a' * 64


@pytest.fixture
def rule_files(tmp_path):
    root = tmp_path / 'proxy with spaces' / 'waf'
    (root / 'rules').mkdir(parents=True)
    entrypoint = root / 'modsecurity.conf'
    entrypoint.write_bytes(b"# Don't change customer settings\nSecRuleEngine On\n")
    return entrypoint, root / 'rules/customer-rule.conf'


def include(path):
    return 'Include "' + str(path).replace('\\', '\\\\').replace('"', '\\"') + '"'


def test_creation_is_idempotent_and_keeps_customer_configuration(rule_files):
    entrypoint, rule = rule_files
    original = entrypoint.read_bytes()
    remote.create_rule(entrypoint, rule, REQUEST_ID)
    first = entrypoint.read_bytes()
    remote.create_rule(entrypoint, rule, REQUEST_ID)
    assert entrypoint.read_bytes() == first == original + (include(rule) + '\n').encode()
    assert rule.read_text() == f'# Roxy-WI rule creation: {REQUEST_ID}\n'
    assert not list(entrypoint.parent.rglob('.roxywi-waf-*'))


def test_interrupted_include_write_is_atomic_and_can_resume(rule_files, monkeypatch):
    entrypoint, rule = rule_files
    original = entrypoint.read_bytes()
    replace = remote.os.replace

    def disk_error(*args):
        raise OSError('synthetic replace failure')

    monkeypatch.setattr(remote.os, 'replace', disk_error)
    with pytest.raises(OSError, match='synthetic'):
        remote.create_rule(entrypoint, rule, REQUEST_ID)
    assert entrypoint.read_bytes() == original
    assert rule.is_file()  # An empty marked file is safe to resume after partial failure.
    assert not list(entrypoint.parent.rglob('.roxywi-waf-*'))
    monkeypatch.setattr(remote.os, 'replace', replace)
    remote.create_rule(entrypoint, rule, REQUEST_ID)
    assert entrypoint.read_text().count('customer-rule.conf') == 1


@pytest.mark.parametrize('content', ['', '# existing\n', f'# Roxy-WI rule creation: {"b" * 64}\n'])
def test_unrelated_files_are_never_adopted(rule_files, content):
    entrypoint, rule = rule_files
    rule.write_text(content)
    original = entrypoint.read_bytes()
    with pytest.raises(remote.RuleConflict):
        remote.create_rule(entrypoint, rule, REQUEST_ID)
    assert rule.read_text() == content
    assert entrypoint.read_bytes() == original


@pytest.mark.parametrize('pattern', ['*.conf', 'customer-*.conf', '[cC]ustomer-rule.conf'])
def test_matching_include_glob_is_not_duplicated(rule_files, pattern):
    entrypoint, rule = rule_files
    entrypoint.write_text(include(rule.parent / pattern) + '\n')
    original = entrypoint.read_bytes()
    remote.create_rule(entrypoint, rule, REQUEST_ID)
    assert entrypoint.read_bytes() == original
    assert rule.is_file()


@pytest.mark.parametrize('conflict', ['disabled', 'duplicates', 'relative_glob'])
def test_conflicting_includes_cause_no_file_changes(rule_files, conflict):
    entrypoint, rule = rule_files
    content = {'disabled': '#' + include(rule), 'duplicates': include(rule) + '\n' + include(rule),
               'relative_glob': 'Include rules/*.conf'}[conflict]
    entrypoint.write_text(content)
    with pytest.raises(remote.RuleConflict):
        remote.create_rule(entrypoint, rule, REQUEST_ID)
    assert not rule.exists()
    assert entrypoint.read_text() == content


def test_concurrent_external_entrypoint_edit_is_not_overwritten(rule_files, monkeypatch):
    entrypoint, rule = rule_files
    copy = remote.shutil.copy2

    def edit_during_copy(*args):
        result = copy(*args)
        entrypoint.write_text('# concurrently edited by administrator\n')
        return result

    monkeypatch.setattr(remote.shutil, 'copy2', edit_during_copy)
    with pytest.raises(remote.RuleConflict):
        remote.create_rule(entrypoint, rule, REQUEST_ID)
    assert entrypoint.read_text() == '# concurrently edited by administrator\n'


@pytest.mark.parametrize('original', [b'SecRuleEngine On', b'SecRuleEngine On\r\n', b''])
def test_existing_newline_convention_is_preserved(rule_files, original):
    entrypoint, rule = rule_files
    entrypoint.write_bytes(original)
    remote.create_rule(entrypoint, rule, REQUEST_ID)
    ending = b'\r\n' if b'\r\n' in original else b'\n'
    separator = b'' if not original or original.endswith(b'\n') else ending
    assert entrypoint.read_bytes() == original + separator + include(rule).encode() + ending


@pytest.mark.skipif(os.name != 'posix', reason='Unix permissions and symlinks')
def test_entrypoint_permissions_and_ownership_are_preserved(rule_files):
    entrypoint, rule = rule_files
    entrypoint.chmod(0o640)
    before = entrypoint.stat()
    remote.create_rule(entrypoint, rule, REQUEST_ID)
    after = entrypoint.stat()
    assert (after.st_uid, after.st_gid, stat.S_IMODE(after.st_mode)) == (before.st_uid, before.st_gid, 0o640)
    assert stat.S_IMODE(rule.stat().st_mode) == 0o644


@pytest.mark.skipif(os.name != 'posix', reason='Unix symlinks')
@pytest.mark.parametrize('target', ['entrypoint', 'rule', 'rules_directory'])
def test_symlinks_are_not_followed(rule_files, tmp_path, target):
    entrypoint, rule = rule_files
    outside = tmp_path / 'outside'
    if target == 'rules_directory':
        outside.mkdir()
        rule.parent.rmdir()
        rule.parent.symlink_to(outside, target_is_directory=True)
    else:
        outside.write_text('# must not change\n')
        link = entrypoint if target == 'entrypoint' else rule
        link.unlink(missing_ok=True)
        link.symlink_to(outside)
    with pytest.raises(remote.RuleConflict):
        remote.create_rule(entrypoint, rule, REQUEST_ID)
    if outside.is_file():
        assert outside.read_text() == '# must not change\n'
    else:
        assert not list(outside.iterdir())
