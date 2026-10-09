"""Standalone remote rule creation, executed under a host-side flock.

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


class RuleConflict(Exception):
    """The requested file belongs to another rule or was changed externally."""


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
            raise RuleConflict('The WAF entrypoint changed during creation')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def create_rule(entrypoint: Path, rule: Path, request_id: str) -> None:
    if (entrypoint.name not in ('modsecurity.conf', 'waf.conf')
            or rule.parent != entrypoint.parent / 'rules'
            or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9._-]*\.conf', rule.name)
            or not re.fullmatch(r'[0-9a-f]{64}', request_id)):
        raise ValueError('Invalid rule creation arguments')
    if entrypoint.is_symlink() or not stat.S_ISREG(entrypoint.stat().st_mode):
        raise RuleConflict('The WAF entrypoint must be a regular file')
    if rule.parent.is_symlink() or not rule.parent.is_dir():
        raise RuleConflict('The WAF rules directory must be a directory, not a link')

    original = entrypoint.read_bytes()
    marker = f'# Roxy-WI rule creation: {request_id}\n'.encode('ascii')
    if rule.is_symlink() or (rule.exists() and (not rule.is_file() or rule.read_bytes() != marker)):
        raise RuleConflict('The rule file already exists')

    includes = 0
    disabled = False
    for line in original.decode('utf-8').splitlines():
        line = line.strip()
        commented = line.startswith('#')
        directive = line.lstrip('#').strip() if commented else line
        if not re.match(r'(?i)^Include\s', directive):
            continue
        tokens = shlex.split(directive, comments=True)
        if len(tokens) == 2 and tokens[0].lower() == 'include':
            path = tokens[1]
            if not os.path.isabs(path):
                # Relative Include paths depend on the runtime working directory.
                # Do not guess whether a relative glob also includes the new file.
                if not commented and any(char in path for char in '*?['):
                    raise RuleConflict('Relative Include patterns require manual configuration')
                continue
            if commented:
                disabled = disabled or path == str(rule)
            elif fnmatch.fnmatchcase(str(rule), path):
                includes += 1
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
            temporary.unlink(missing_ok=True)

    if not includes:
        escaped = str(rule).replace('\\', '\\\\').replace('"', '\\"')
        argument = str(rule) if re.fullmatch(r'[A-Za-z0-9/._-]+', str(rule)) else f'"{escaped}"'
        ending = b'\r\n' if b'\r\n' in original else b'\n'
        separator = b'' if not original or original.endswith(b'\n') else ending
        content = original + separator + f'Include {argument}'.encode('utf-8') + ending
        _replace_config(entrypoint, original, content)


def main() -> None:
    try:
        create_rule(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
    except RuleConflict:
        print(json.dumps({'status': 'conflict'}))
    else:
        print(json.dumps({'status': 'ok'}))


if __name__ == '__main__':
    main()
