"""Parse votequorum's bounded, locale-independent status output."""
import re


def details(output):
    flags = re.search(r'^Flags:\s*(.*)$', output, re.MULTILINE)
    if not flags:
        raise ValueError('Unsupported votequorum status output')
    words = flags[1].split()
    vote = re.search(r'^\s*0\s+(\d+)\s+Qdevice\s*$', output, re.MULTILINE)
    return {'configured': 'Qdevice' in words, 'votes': int(vote[1]) if vote else 0,
            'two_node': '2Node' in words}
