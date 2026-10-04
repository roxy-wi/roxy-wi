"""Lossless configuration presentation, independent of Flask and remote I/O.

Section ranges index the original source; they are navigation hints, not a
replacement for the service's configuration validator. File identity travels
with the document so a section name alone never identifies an editing target.
"""

import hashlib
import re
from collections import Counter
from urllib.parse import quote, urlencode


HAPROXY_SECTIONS = {
    'global', 'defaults', 'frontend', 'backend', 'listen', 'peers', 'resolvers',
    'userlist', 'cache', 'http-errors', 'log-forward', 'ring', 'program', 'mailers',
    'fcgi-app', 'traces',
}
FORM_SECTIONS = {'global', 'defaults', 'frontend', 'backend', 'listen', 'peers', 'userlist'}
MANAGED_START = re.compile(r'^# BEGIN Roxy-WI MANAGED (.+?) do not edit it directly\s*$')


def source_lines(text: str) -> list[str]:
    """Split physical lines, retaining terminators (and a missing final newline)."""
    return re.findall(r'[^\n]*\n|[^\n]+$', text)


def haproxy_sections(text: str) -> list[dict]:
    lines = source_lines(text)
    starts = []
    pending_marker = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        marker = MANAGED_START.fullmatch(stripped)
        if marker:
            pending_marker = (index, marker[1])
            continue
        if not stripped or stripped.startswith('#'):
            continue
        tokens = stripped.split()
        kind = tokens[0]
        if kind in HAPROXY_SECTIONS:
            name = tokens[1] if len(tokens) > 1 and not tokens[1].startswith('#') else kind
            identity = kind if kind == name else f'{kind} {name}'
            start = pending_marker[0] if pending_marker and pending_marker[1] == identity else index
            starts.append(dict(start=start, header=index, title=stripped, kind=kind, name=name))
        pending_marker = None
    return _ranges(starts, len(lines))


def _ranges(starts: list[dict], count: int) -> list[dict]:
    if count and (not starts or starts[0]['start'] != 0):
        starts.insert(0, dict(start=0, header=0, title='', kind='preamble', name=''))
    for index, section in enumerate(starts):
        section['end'] = starts[index + 1]['start'] if index + 1 < len(starts) else count
    return starts


def _block_sections(text: str, service: str) -> list[dict]:
    """Locate top-level blocks without treating quoted/comment braces as syntax."""
    lines = source_lines(text)
    starts = []
    depth = 0
    quote_char = None
    escaped = False
    token = ''
    pending_start = None
    for index, line in enumerate(lines):
        if service == 'apache':
            match = re.match(r'^\s*<VirtualHost\b[^>]*>', line, flags=re.IGNORECASE)
            if match:
                starts.append(dict(start=index, header=index, title=line.strip(), kind='VirtualHost', name=''))
            continue
        for char in line:
            if escaped:
                escaped = False
                token += char
                continue
            if char == '\\':
                escaped = True
                token += char
                continue
            if quote_char:
                if char == quote_char:
                    quote_char = None
                continue
            if char in ('"', "'"):
                quote_char = char
                continue
            if char == '#':
                break
            # Attached braces may be regex quantifiers or ${variables}.
            if char in '{}' and not token:
                if char == '{':
                    if depth == 0:
                        start = pending_start if pending_start is not None else index
                        title = ' '.join(part.strip() for part in lines[start:index + 1]).split('{', 1)[0].strip()
                        starts.append(dict(start=start, header=start, title=title + ' {', kind=title.split()[0] if title else 'block', name=''))
                    depth += 1
                else:
                    depth = max(0, depth - 1)
                    if depth == 0:
                        pending_start = None
            elif char == ';':
                token = ''
                if depth == 0:
                    pending_start = None
            elif char.isspace():
                token = ''
            else:
                if depth == 0 and pending_start is None:
                    pending_start = index
                token += char
        token = ''
    return _ranges(starts, len(lines))


def build_document(text: str, service: str, server: str, file_path: str, *,
                   version: str | None = None, editable: bool = False,
                   main_file: bool = False) -> dict:
    sections = haproxy_sections(text) if service == 'haproxy' else _block_sections(text, service)
    occurrences = Counter((section['kind'], section['name']) for section in sections)
    encoded_server = quote(server, safe='')
    file_token = file_path.replace('/', '92')
    file_edit_url = f'/config/{service}/{encoded_server}/edit/{quote(file_token, safe="")}'
    lines = source_lines(text)
    for section in sections:
        section['id'] = hashlib.sha256(
            f'{service}\0{server}\0{file_path}\0{section["start"]}\0{section["title"]}'.encode()
        ).hexdigest()[:20]
        section['start_line'] = section.pop('start') + 1
        section['header_line'] = section.pop('header') + 1
        section['end_line'] = section.pop('end')
        section['editor'] = None
        section['edit_url'] = None
        section['stats_url'] = None
        section['open_urls'] = []
        if service == 'haproxy' and section['kind'] in ('frontend', 'backend', 'listen') and not version:
            section['stats_url'] = f'/stats/haproxy/{encoded_server}#{quote(section["name"], safe="")}'
            if section['kind'] != 'backend':
                section['open_urls'] = _listener_links(lines[section['start_line'] - 1:section['end_line']], server)
        if not editable or version or section['kind'] == 'preamble':
            continue
        if service == 'haproxy':
            section['edit_url'] = (
                f'/config/section/haproxy/{encoded_server}/{quote(section["title"], safe="")}?'
                + urlencode({'file_path': file_path, 'section_line': section['header_line']})
            )
            # The existing Add API stores (server, type, name), not a file path.
            # Until that API becomes file-aware, only main-file, unique sections
            # can use it. Its 404 response selects the ordinary text editor.
            simple_header = section['title'] == (
                section['kind'] if section['kind'] == section['name']
                else f'{section["kind"]} {section["name"]}'
            )
            section['editor'] = 'form-or-text' if (
                main_file and simple_header and section['kind'] in FORM_SECTIONS
                and occurrences[(section['kind'], section['name'])] == 1
                and (section['kind'] not in ('global', 'defaults') or section['name'] == section['kind'])
            ) else 'text'
    return {
        'source': {'service': service, 'server': server, 'path': file_path,
                   'file_token': file_token, 'version': version, 'main_file': main_file},
        'text': text, 'line_count': len(source_lines(text)), 'sections': sections,
        'edit_url': file_edit_url if editable and not version else None,
    }


def _listener_links(lines: list[str], server: str) -> list[dict]:
    """Retain the viewer's Open action for explicit TCP ports; skip Unix/ranges."""
    links = {}
    host = f'[{server}]' if ':' in server else server
    for line in lines:
        tokens = line.split('#', 1)[0].split()
        if len(tokens) < 2 or tokens[0] != 'bind':
            continue
        scheme = 'https' if 'ssl' in tokens[2:] else 'http'
        for address in tokens[1].split(','):
            if address.startswith(('/', 'unix@', 'abns@', 'fd@')) or ':' not in address:
                continue
            port = address.rsplit(':', 1)[1]
            if port.isascii() and port.isdecimal() and 0 < int(port) <= 65535:
                url = f'{scheme}://{host}:{int(port)}/'
                links[url] = {'url': url, 'port': port}
    return list(links.values())
