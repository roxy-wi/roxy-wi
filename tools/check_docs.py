#!/usr/bin/env python3
"""Check repository documentation links and heading anchors without network access."""

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]


class HTMLLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ('href', 'src') and value:
                self.links.append(value)


def without_code(text):
    return re.sub(r'^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$', '', text, flags=re.M | re.S)


def anchors(text):
    result = set()
    counts = Counter()
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', without_code(text), flags=re.M):
        heading = re.sub(r'<[^>]+>', '', heading).lower()
        slug = re.sub(r'[^\w\- ]', '', heading).replace(' ', '-')
        index = counts[slug]
        result.add(f'{slug}-{index}' if index else slug)
        counts[slug] += 1
    result.update(re.findall(r'\bid=["\x27]([^"\x27]+)', text))
    return result


def check_file(path, root=ROOT):
    text = without_code(path.read_text(encoding='utf-8'))
    # The documentation uses inline links; HTML is used for the README logo.
    links = re.findall(r'!?\[[^\]\n]*\]\(<?([^\s)>]+)>?(?:\s+["\x27].*?["\x27])?\)', text)
    parser = HTMLLinks()
    parser.feed(text)
    errors = []
    for link in links + parser.links:
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc:
            continue
        decoded = unquote(parsed.path)
        target = ((root / decoded.lstrip('/')) if decoded.startswith('/')
                  else (path.parent / decoded) if decoded else path).resolve()
        label = f'{path.relative_to(root)}: {link}'
        if not target.is_relative_to(root.resolve()):
            errors.append(f'{label} points outside the repository')
        elif not target.exists():
            errors.append(f'{label} does not exist')
        elif parsed.fragment and target.suffix.lower() == '.md':
            if unquote(parsed.fragment) not in anchors(target.read_text(encoding='utf-8')):
                errors.append(f'{label} has no matching heading or anchor')
    return errors


def main():
    files = sorted({*ROOT.glob('*.md'), *ROOT.glob('docs/**/*.md'), *ROOT.glob('.github/*.md')})
    errors = [error for path in files for error in check_file(path)]
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print(f'Checked local links and anchors in {len(files)} Markdown files.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
