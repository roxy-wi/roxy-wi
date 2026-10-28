"""Executed on a managed node. No shell interpolation or persistent staging files."""

TRANSACTION = r'''
import copy, fcntl, hashlib, json, os, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

def parse(text):
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('XML entities are not allowed')
    return ET.fromstring(text)

def digest(root):
    value = ET.canonicalize(ET.tostring(root.find('configuration'), encoding='unicode'), strip_text=True)
    return hashlib.sha256(value.encode()).hexdigest()

def run(args, allowed=(0,)):
    result = subprocess.run(args, capture_output=True, text=True, timeout=35)
    if result.returncode not in allowed:
        raise ValueError(args[0] + ' failed; inspect the node journal')
    return result.stdout

payload = json.load(sys.stdin)
os.umask(0o077)
try:
    with open('/run/lock/roxywi-pacemaker.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        live = parse(run(['cibadmin', '--query']))
        if digest(live) != payload['base_digest']:
            print(json.dumps({'error': 'Configuration changed; load a fresh CIB and review again', 'conflict': True}))
            sys.exit(0)
        proposed = parse(payload['xml'])
        candidate = copy.deepcopy(live)
        candidate.remove(candidate.find('configuration'))
        candidate.insert(0, copy.deepcopy(proposed.find('configuration')))
        # A versioned patch lets Pacemaker reject changes made by other managers
        # between this read and commit, including managers on another node.
        candidate.set('epoch', str(int(live.get('epoch', '0')) + 1))
        candidate.set('num_updates', '0')
        with tempfile.TemporaryDirectory(prefix='roxywi-pcmk-') as tmp:
            old, new, patch = [os.path.join(tmp, name) for name in ('old.xml', 'new.xml', 'patch.xml')]
            ET.ElementTree(live).write(old, encoding='utf-8', xml_declaration=True)
            ET.ElementTree(candidate).write(new, encoding='utf-8', xml_declaration=True)
            run(['crm_verify', '--xml-file', new])
            simulation = run(['crm_simulate', '--xml-file', new, '--simulate'])
            delta = run(['crm_diff', '--original', old, '--new', new, '--cib'], allowed=(0, 1))
            with open(patch, 'w') as stream:
                stream.write(delta)
            if payload['apply']:
                run(['cibadmin', '--patch', '--xml-file', patch, '--sync-call'])
            print(json.dumps({'status': 'applied' if payload['apply'] else 'validated',
                              'simulation': simulation[:60000], 'digest': digest(candidate)}))
except (ValueError, OSError, subprocess.TimeoutExpired, ET.ParseError):
    print(json.dumps({'error': 'Cluster validation or commit failed; inspect the node journal'}))
'''
