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


@pytest.mark.parametrize('prefix', ['', '#', '## ', '\t# # '])
@pytest.mark.parametrize('ending', ['\n', '\r\n', ''])
def test_toggle_is_literal_and_idempotent_with_comments_and_line_endings(rule_files, prefix, ending):
    entrypoint, rule = rule_files
    rule.write_text('# customer content\n')
    similar = rule.with_name('customer-ruleXconf')
    unrelated = include(similar) + '\n# prose about Include directives\n'
    directive = include(rule).replace('Include ', 'Include\t') + '  # customer note'
    entrypoint.write_bytes((unrelated + prefix + directive + ending).encode())
    remote.switch_rule(entrypoint, rule, 0)
    disabled = entrypoint.read_bytes()
    remote.switch_rule(entrypoint, rule, 0)
    assert entrypoint.read_bytes() == disabled
    remote.switch_rule(entrypoint, rule, 1)
    enabled = entrypoint.read_bytes()
    indent = '\t' if prefix.startswith('\t') else ''
    assert enabled == (unrelated + indent + directive + ending).encode()
    remote.switch_rule(entrypoint, rule, 1)
    assert entrypoint.read_bytes() == enabled
    assert rule.read_text() == '# customer content\n'


def test_duplicates_in_one_file_are_reduced_to_one_active_include(rule_files):
    entrypoint, rule = rule_files
    rule.write_text('# test\n')
    line = include(rule) + '\n'
    entrypoint.write_text('# ' + line + line + line)
    remote.switch_rule(entrypoint, rule, 1)
    assert entrypoint.read_text() == '# ' + line + line + '# ' + line
    remote.switch_rule(entrypoint, rule, 0)
    assert entrypoint.read_text() == ('# ' + line) * 3
    remote.switch_rule(entrypoint, rule, 1)
    assert entrypoint.read_text() == line + ('# ' + line) * 2


@pytest.mark.parametrize('legacy', [False, True])
def test_nginx_toggles_the_file_that_actually_includes_the_rule(rule_files, legacy):
    base, rule = rule_files
    entrypoint = base.with_name('waf.conf')
    entrypoint.write_text(include(base) + '\n')
    rule.write_text('# test\n')
    source = base if legacy else entrypoint
    unchanged = entrypoint if legacy else base
    untouched = unchanged.read_bytes()
    original = source.read_text()
    source.write_text(original + include(rule) + '\n')
    remote.switch_rule(entrypoint, rule, 0)
    assert source.read_text() == original + '# ' + include(rule) + '\n'
    assert unchanged.read_bytes() == untouched
    remote.switch_rule(entrypoint, rule, 1)
    assert source.read_text() == original + include(rule) + '\n'


def test_nginx_creation_retry_after_upgrade_keeps_legacy_include(rule_files):
    base, rule = rule_files
    remote.create_rule(base, rule, REQUEST_ID)
    entrypoint = base.with_name('waf.conf')
    entrypoint.write_text(include(base) + '\n')
    original = {path: path.read_bytes() for path in (base, entrypoint, rule)}
    remote.create_rule(entrypoint, rule, REQUEST_ID)
    assert {path: path.read_bytes() for path in original} == original


@pytest.mark.parametrize('enabled', [0, 1])
@pytest.mark.parametrize('conflict', ['wildcard', 'two_files', 'relative', 'duplicate_base'])
def test_ambiguous_includes_are_rejected_without_changes(rule_files, enabled, conflict):
    base, rule = rule_files
    entrypoint = base.with_name('waf.conf')
    rule.write_text('# test\n')
    entrypoint.write_text(include(base) + '\n')
    if conflict == 'wildcard':
        base.write_text(include(rule.parent / '*.conf') + '\n')
    elif conflict == 'relative':
        base.write_text('Include rules/' + rule.name + '\n')
    elif conflict == 'two_files':
        base.write_text(include(rule) + '\n')
        entrypoint.write_text(include(base) + '\n' + include(rule) + '\n')
    else:
        entrypoint.write_text((include(base) + '\n') * 2)
    original = {path: path.read_bytes() for path in (base, entrypoint, rule)}
    with pytest.raises(remote.RuleConflict):
        remote.switch_rule(entrypoint, rule, enabled)
    assert {path: path.read_bytes() for path in original} == original


def test_missing_include_can_be_disabled_or_added_but_missing_file_cannot_be_enabled(rule_files):
    entrypoint, rule = rule_files
    original = entrypoint.read_bytes()
    remote.switch_rule(entrypoint, rule, 0)
    assert entrypoint.read_bytes() == original
    with pytest.raises(remote.RuleConflict):
        remote.switch_rule(entrypoint, rule, 1)
    assert entrypoint.read_bytes() == original
    rule.write_text('# restored file\n')
    remote.switch_rule(entrypoint, rule, 1)
    assert entrypoint.read_bytes() == original + (include(rule) + '\n').encode()


def test_toggle_write_failure_keeps_the_original_configuration(rule_files, monkeypatch):
    entrypoint, rule = rule_files
    rule.write_text('# test\n')
    entrypoint.write_text(include(rule) + '\n')
    original = entrypoint.read_bytes()

    def fail(*args):
        raise OSError('synthetic disk failure')

    monkeypatch.setattr(remote.os, 'replace', fail)
    with pytest.raises(OSError, match='synthetic disk failure'):
        remote.switch_rule(entrypoint, rule, 0)
    assert entrypoint.read_bytes() == original
    assert not list(entrypoint.parent.glob('.roxywi-waf-*'))
