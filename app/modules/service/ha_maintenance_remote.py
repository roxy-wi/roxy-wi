"""Fixed, offline Pacemaker scheduling helper, shipped over existing SSH."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET


def parse(value):
    if len(value.encode())>1048576 or '<!DOCTYPE' in value.upper() or '<!ENTITY' in value.upper():
        raise ValueError('Invalid CIB')
    return ET.fromstring(value)


def fingerprint(xml,target):
    root=parse(xml);config=copy.deepcopy(root.find('configuration'))
    if config is None: raise ValueError('Missing CIB configuration')
    # This workflow may change only this node's standby attribute. Every other
    # persistent change invalidates its review, including another node's state.
    for node in config.findall('./nodes/node'):
        if node.get('uname')==target:
            for group in node.findall('./instance_attributes'):
                for value in list(group):
                    if value.tag=='nvpair' and value.get('name')=='standby':group.remove(value)
                if not len(group):node.remove(group)
    canonical=ET.canonicalize(ET.tostring(config,encoding='unicode'),strip_text=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def run(args,*,env=None,allowed=(0,)):
    result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=60)
    if result.returncode not in allowed or len(result.stdout)+len(result.stderr)>2*1024*1024:
        raise ValueError('Pacemaker simulation failed; inspect node journal')
    return result.stdout


def simulate(xml,target,*,returning=False):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,62}',target):raise ValueError('Invalid node')
    root=parse(xml)
    nodes=[n for n in root.findall('./configuration/nodes/node') if n.get('uname')==target]
    if len(nodes)!=1:raise ValueError('Node identity is ambiguous')
    group=ET.SubElement(nodes[0],'instance_attributes',id='roxywi-maintenance-simulation')
    ET.SubElement(group,'nvpair',id='roxywi-maintenance-simulation-standby',name='standby',value='off' if returning else 'on')
    for existing in nodes[0].findall('./instance_attributes'):
        if existing is not group:
            for value in list(existing):
                if value.tag=='nvpair' and value.get('name')=='standby':existing.remove(value)
    with tempfile.TemporaryDirectory(prefix='roxywi-ha-plan-') as tmp:
        Path(tmp).chmod(0o700)
        source=Path(tmp)/'input.xml';output=Path(tmp)/'result.xml'
        source.write_text(ET.tostring(root,encoding='unicode'));source.chmod(0o600)
        run(['crm_simulate','--xml-file',str(source),'--simulate','--save-output',str(output)])
        return run(['crm_mon','--one-shot','--output-as=xml'],
            env={**os.environ,'CIB_file':str(output)},allowed=(0,1,2))
