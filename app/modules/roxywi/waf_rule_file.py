"""Standalone remote rule file operations, executed under a host-side flock.

An empty, marked file can survive an interrupted request. Only the identical
request may resume it; existing user files are never adopted or overwritten.
The catalog is updated by the caller after this operation succeeds.
"""

import fnmatch
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import sys
import tempfile


WAF_MODES = ('On', 'Off', 'DetectionOnly')


class RuleConflict(Exception):
    """The requested file belongs to another rule or was changed externally."""


def _unlink(path: Path) -> None:
    # Keep the standalone helper compatible with Python 3.6 on managed hosts.
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _replace_config(path: Path, original: bytes, content: bytes) -> None:
    # Work in the same filesystem and retain mode, ownership and xattrs (SELinux).
    fd, temporary = tempfile.mkstemp(prefix='.roxywi-waf-', dir=path.parent)
    os.close(fd)
    temporary = Path(temporary)
    try:
        shutil.copy2(path, temporary)
        if os.name == 'posix':
            metadata = path.stat()
            os.chown(temporary, metadata.st_uid, metadata.st_gid)
        with temporary.open('wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink() or path.read_bytes() != original:
            raise RuleConflict('The WAF configuration changed during update')
        os.replace(temporary, path)
    finally:
        _unlink(temporary)


def _validate_location(entrypoint: Path, rule: Path) -> None:
    if (entrypoint.name not in ('modsecurity.conf', 'waf.conf')
            or rule.parent != entrypoint.parent / 'rules'
            or not re.fullmatch(r'[A-Za-z0-9._-]+\.conf', rule.name)):
        raise ValueError('Invalid WAF rule path')
    if rule.parent.is_symlink() or not rule.parent.is_dir():
        raise RuleConflict('The WAF rules directory must be a directory, not a link')


def _read_config(path: Path) -> bytes:
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise RuleConflict('The WAF configuration must be a regular file')
    return path.read_bytes()


def _mode_directive(config: Path):
    if config.name != 'modsecurity.conf' or config.parent.name != 'waf':
        raise ValueError('Invalid WAF mode configuration path')
    original = _read_config(config)
    lines = original.decode('utf-8').splitlines(keepends=True)
    matches = []
    continued, depth = False, 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if continued:
            continued = stripped.endswith('\\')
            continue
        if re.match(r'^[ \t]*SecRuleEngine(?:\s|$)', line, re.IGNORECASE):
            match = re.fullmatch(
                r'(?P<prefix>[ \t]*SecRuleEngine[ \t]+)(?P<quote>[\'\"]?)'
                r'(?P<mode>On|Off|DetectionOnly)(?P=quote)(?P<suffix>[ \t]*(?:#[^\r\n]*)?(?:\r?\n)?)',
                line, re.IGNORECASE,
            )
            if depth or not match:
                raise RuleConflict('The WAF mode directive must be a single global directive')
            matches.append((index, match))
        continued = stripped.endswith('\\')
        if stripped.startswith('</'):
            depth -= 1
        elif stripped.startswith('<') and not stripped.endswith('/>'):
            depth += 1
    if len(matches) != 1:
        raise RuleConflict('The WAF configuration must contain exactly one active SecRuleEngine directive')
    index, match = matches[0]
    mode = next(value for value in WAF_MODES if value.lower() == match['mode'].lower())
    return original, lines, index, match, mode


def read_mode(config: Path) -> str:
    """Read the explicit mode in the file, not the mode loaded by a process."""
    return _mode_directive(config)[-1]


def set_mode(config: Path, mode: str) -> None:
    if mode not in WAF_MODES:
        raise ValueError('Unsupported WAF mode')
    original, lines, index, match, current = _mode_directive(config)
    if current == mode:
        return
    lines[index] = match['prefix'] + match['quote'] + mode + match['quote'] + match['suffix']
    _replace_config(config, original, ''.join(lines).encode('utf-8'))


def _include(line: str):
    match = re.fullmatch(r'([ \t]*)(#[# \t]*)?(Include[ \t]+[^\r\n]*)([\r\n]*)', line, re.IGNORECASE)
    if not match:
        return None
    indent, comment, directive, ending = match.groups()
    try:
        tokens = shlex.split(directive, comments=True)
    except ValueError as exc:
        raise RuleConflict('Cannot parse an Include directive') from exc
    if len(tokens) != 2:
        if comment:
            return None  # A prose comment, not a disabled Include.
        raise RuleConflict('Unsupported Include directive')
    return {'indent': indent, 'disabled': bool(comment), 'directive': directive,
            'ending': ending, 'path': os.path.normpath(tokens[1])}


def _sources(entrypoint: Path) -> dict:
    sources = {entrypoint: _read_config(entrypoint)}
    if entrypoint.name == 'waf.conf':
        # NGINX loads its base settings from modsecurity.conf. Older Roxy-WI
        # versions also appended custom rules there; keep their existing order.
        base = entrypoint.with_name('modsecurity.conf')
        references = 0
        for line in sources[entrypoint].decode('utf-8').splitlines(keepends=True):
            include = _include(line)
            if not include or include['disabled']:
                continue
            path = include['path']
            if path == str(base):
                references += 1
            elif fnmatch.fnmatchcase(str(base), path) or (not os.path.isabs(path) and Path(path).name == base.name):
                raise RuleConflict('Ambiguous reference to the base WAF configuration')
        if references > 1:
            raise RuleConflict('The base WAF configuration is included more than once')
        if references:
            sources[base] = _read_config(base)
    return sources


def _references(sources: dict, rule: Path) -> list:
    references = []
    for source, content in sources.items():
        for index, line in enumerate(content.decode('utf-8').splitlines(keepends=True)):
            include = _include(line)
            if not include:
                continue
            path = include['path']
            if not os.path.isabs(path):
                if ((not include['disabled'] and any(char in path for char in '*?['))
                        or Path(path).name == rule.name):
                    raise RuleConflict('Relative Include paths require manual configuration')
            elif fnmatch.fnmatchcase(str(rule), path):
                references.append((source, index, include))
    return references


def _append_include(entrypoint: Path, original: bytes, rule: Path) -> None:
    escaped = str(rule).replace('\\', '\\\\').replace('"', '\\"')
    argument = str(rule) if re.fullmatch(r'[A-Za-z0-9/._-]+', str(rule)) else f'"{escaped}"'
    ending = b'\r\n' if b'\r\n' in original else b'\n'
    separator = b'' if not original or original.endswith(b'\n') else ending
    content = original + separator + f'Include {argument}'.encode('utf-8') + ending
    _replace_config(entrypoint, original, content)


def create_rule(entrypoint: Path, rule: Path, request_id: str) -> None:
    _validate_location(entrypoint, rule)
    if not re.fullmatch(r'[0-9a-f]{64}', request_id):
        raise ValueError('Invalid rule creation request identifier')
    sources = _sources(entrypoint)
    marker = f'# Roxy-WI rule creation: {request_id}\n'.encode('ascii')
    if rule.is_symlink() or (rule.exists() and (not rule.is_file() or rule.read_bytes() != marker)):
        raise RuleConflict('The rule file already exists')

    references = _references(sources, rule)
    includes = sum(not include['disabled'] for _, _, include in references)
    disabled = any(include['disabled'] and include['path'] == str(rule) for _, _, include in references)
    if includes > 1 or (disabled and not includes):
        raise RuleConflict('The rule has conflicting Include directives')

    if not rule.exists():
        fd, temporary = tempfile.mkstemp(prefix='.roxywi-waf-', dir=rule.parent)
        temporary = Path(temporary)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(marker)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o644)
            # link is exclusive: a concurrent creator must never be overwritten.
            os.link(temporary, rule)
        finally:
            _unlink(temporary)

    if not includes:
        _append_include(entrypoint, sources[entrypoint], rule)


def switch_rule(entrypoint: Path, rule: Path, enabled: int) -> None:
    if enabled not in (0, 1):
        raise ValueError('Rule state must be 0 or 1')
    _validate_location(entrypoint, rule)
    sources = _sources(entrypoint)
    references = _references(sources, rule)
    if any(include['path'] != str(rule) for _, _, include in references):
        raise RuleConflict('A wildcard Include cannot be changed for an individual rule')
    if len({source for source, _, _ in references}) > 1:
        raise RuleConflict('The rule is referenced in more than one configuration file')
    if enabled and (rule.is_symlink() or not rule.is_file()):
        raise RuleConflict('Cannot enable a missing or linked rule file')
    if not references:
        if enabled:
            _append_include(entrypoint, sources[entrypoint], rule)
        return

    source = references[0][0]
    original = sources[source]
    lines = original.decode('utf-8').splitlines(keepends=True)
    # Keep the existing active position when possible. Disable duplicate exact
    # references in this file without changing other rules or the rule content.
    primary = next((index for _, index, include in references if not include['disabled']), references[0][1])
    for _, index, include in references:
        if enabled and index == primary:
            lines[index] = include['indent'] + include['directive'] + include['ending']
        elif not include['disabled']:
            lines[index] = include['indent'] + '# ' + include['directive'] + include['ending']
    content = ''.join(lines).encode('utf-8')
    if content != original:
        _replace_config(source, original, content)


def main() -> None:
    try:
        if sys.argv[1] == 'read-mode':
            result = {'status': 'ok', 'mode': read_mode(Path(sys.argv[2]))}
        elif sys.argv[1] == 'set-mode':
            set_mode(Path(sys.argv[2]), sys.argv[3])
            result = {'status': 'ok', 'mode': sys.argv[3]}
        elif sys.argv[1] == 'toggle':
            enabled = int(sys.argv[4])
            switch_rule(Path(sys.argv[2]), Path(sys.argv[3]), enabled)
            result = {'status': 'ok', 'enabled': enabled}
        else:
            create_rule(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
            result = {'status': 'ok'}
    except RuleConflict:
        print(json.dumps({'status': 'conflict'}))
    else:
        print(json.dumps(result))


if __name__ == '__main__':
    main()
