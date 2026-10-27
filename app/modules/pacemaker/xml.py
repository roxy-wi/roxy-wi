"""Parse bounded XML without DTDs; hash only persistent configuration."""
import hashlib
import re
import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring

from app.modules.roxywi.exception import RoxywiInputError


def parse(value):
    if len(value.encode('utf-8')) > 1024 * 1024:
        raise RoxywiInputError('XML exceeds 1 MiB')
    try:
        return fromstring(value, forbid_dtd=True)
    except Exception as exc:
        raise RoxywiInputError('Invalid XML; DTDs and entities are not allowed') from exc


def configuration(value):
    root = parse(value)
    if root.tag != 'cib' or root.find('configuration') is None:
        raise RoxywiInputError('Expected a CIB document containing configuration')
    if len(root.findall('configuration')) != 1:
        raise RoxywiInputError('Expected exactly one configuration')
    return root.find('configuration')


def digest(value):
    canonical = ET.canonicalize(ET.tostring(configuration(value), encoding='unicode'), strip_text=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def summary(value):
    root = parse(value)
    if root.tag != 'pacemaker-result':
        raise RoxywiInputError('Unsupported crm_mon XML output')
    nodes = [{key: node.get(key) for key in ('name', 'id', 'online', 'standby', 'maintenance', 'unclean')}
             for node in root.findall('./nodes/node')]
    resources = []
    parents = {child: parent for parent in root.iter() for child in parent}
    for resource in root.findall('./resources//resource'):
        target = re.sub(r':\d+$', '', resource.get('id', ''))
        parent = parents.get(resource)
        while parent is not None and parent.tag != 'resources':
            if parent.tag in ('clone', 'bundle'):
                target = parent.get('id', target)
            parent = parents.get(parent)
        resources.append({
            'target_id': target,
            **{key: resource.get(key) for key in ('id', 'resource_agent', 'role', 'active', 'blocked', 'failed', 'managed')},
            'nodes': [node.get('name') for node in resource.findall('node')],
        })
    dc = root.find('./summary/current_dc')
    failures = root.find('failures')
    return {
        'quorate': dc is not None and dc.get('with_quorum') == 'true',
        'dc': dc.get('name') if dc is not None else None,
        'nodes': nodes, 'resources': resources,
        'failures': len(list(failures)) if failures is not None else 0,
    }
