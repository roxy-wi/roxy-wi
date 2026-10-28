"""Discover native agents/metadata and manage reviewed repository packages."""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor

from defusedxml.ElementTree import fromstring
from pydantic import Field

from app.modules.pacemaker import service
from app.modules.pacemaker.platforms import SOURCE
from app.modules.pacemaker.remote import Remote
from app.modules.pacemaker.schemas import StrictModel, AGENT_PATTERN
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiValidationError

PACKAGE_PATTERN = r'^(?:resource-agents|fence-agents)(?:[a-zA-Z0-9+._-]*)$'
VERSION_PATTERN = r'^[a-zA-Z0-9.+:~_-]{1,200}$'


class AgentRequest(StrictModel):
    agent: str = Field(pattern=AGENT_PATTERN)


class PackageRequest(StrictModel):
    package: str = Field(pattern=PACKAGE_PATTERN)
    plan_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirm: str


DISCOVER = r'''
import json, re, subprocess
pattern = re.compile(r'^[A-Za-z0-9_.@-]+$')
def read(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise SystemExit('Native agent discovery failed')
    return [line.strip() for line in result.stdout.splitlines() if pattern.fullmatch(line.strip())]
agents = []
for provider in read(['crm_resource', '--list-ocf-providers']):
    agents += ['ocf:' + provider + ':' + name for name in read(['crm_resource', '--list-agents', 'ocf:' + provider])]
for standard in ('stonith', 'systemd'):
    agents += [standard + ':' + name for name in read(['crm_resource', '--list-agents', standard])]
print(json.dumps(sorted(set(agents))))
'''

METADATA = r'''
import json, re, subprocess, sys
agent = json.load(sys.stdin)['agent']
if not re.fullmatch(r'(ocf:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+|systemd:[A-Za-z0-9_.@-]+|stonith:[A-Za-z0-9_.-]+)', agent):
    raise SystemExit('Invalid agent ID')
result = subprocess.run(['crm_resource', '--show-metadata', agent], capture_output=True, text=True, timeout=30)
if result.returncode != 0:
    raise SystemExit('Agent metadata is unavailable')
print(result.stdout)
'''

PACKAGES = SOURCE + r'''
import json
package_pattern = re.compile(r'^(resource-agents|fence-agents)[a-zA-Z0-9+._-]*$')
version_pattern = re.compile(r'^[a-zA-Z0-9.+:~_-]{1,200}$')
def native_packages():
    profile = platform_profile()
    env = dict(os.environ, LC_ALL='C')
    packages = {}
    if profile['manager'] == 'apt-get':
        result = subprocess.run(['apt-cache', 'search', '--names-only', '^(resource-agents|fence-agents)'],
                                capture_output=True, text=True, timeout=45, env=env, check=True)
        for line in result.stdout.splitlines():
            name, _, description = line.partition(' - ')
            if package_pattern.fullmatch(name):
                packages[name] = {'name': name, 'description': description[:300], 'installed': None, 'candidate': None}
        if packages:
            result = subprocess.run(['apt-cache', 'policy', *sorted(packages)], capture_output=True,
                                    text=True, timeout=45, env=env, check=True)
            current = None
            for line in result.stdout.splitlines():
                if line.endswith(':') and not line.startswith(' '):
                    current = line[:-1]
                elif current in packages:
                    field, _, value = line.strip().partition(': ')
                    if field in ('Installed', 'Candidate') and version_pattern.fullmatch(value):
                        packages[current][field.lower()] = value
    else:
        result = subprocess.run(['dnf', '-C', '-q', 'list', '--showduplicates', 'resource-agents*', 'fence-agents*'],
                                capture_output=True, text=True, timeout=60, env=env)
        if result.returncode != 0:
            raise SystemExit('Repository cache unavailable; refresh repositories first')
        installed, pending = False, None
        for line in result.stdout.splitlines():
            if line == 'Installed Packages': installed = True; continue
            if line == 'Available Packages': installed = False; continue
            parts = line.split()
            if len(parts) == 1 and package_pattern.fullmatch(parts[0].rsplit('.', 1)[0]):
                pending = parts[0]; continue
            if pending:
                parts = [pending, *parts]; pending = None
            if len(parts) < 2: continue
            name = parts[0].rsplit('.', 1)[0]
            if not package_pattern.fullmatch(name) or not version_pattern.fullmatch(parts[1]): continue
            package = packages.setdefault(name, {'name': name, 'description': '', 'installed': None, 'candidate': None})
            # DNF orders available EVRs for each name; the final row is the candidate.
            if installed: package['installed'] = parts[1]
            package['candidate'] = parts[1]
    return [p for p in packages.values() if p['candidate']]
'''
PACKAGE_QUERY = PACKAGES + '''
try:
    print(json.dumps({'packages': native_packages(), 'error': None}))
except (SystemExit, subprocess.SubprocessError):
    print(json.dumps({'packages': [], 'error': 'Cannot read enabled repository cache; refresh repositories or check the host platform'}))
'''
PACKAGE_INSTALL = PACKAGES + r'''
import fcntl, sys
with open('/run/lock/roxywi-agent-packages.lock', 'a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    data = json.load(sys.stdin)
    name, version = data['package'], data['version']
    if not package_pattern.fullmatch(name) or not version_pattern.fullmatch(version):
        raise SystemExit('Invalid package selection')
    current = next((p for p in native_packages() if p['name'] == name), None)
    if not current or current['candidate'] != version:
        raise SystemExit('Package candidate changed; review again')
    profile = platform_profile()
    if current['installed'] != version:
        if profile['manager'] == 'apt-get':
            command = ['apt-get', '-o', 'DPkg::Lock::Timeout=60', 'install', '-y', '--no-remove', '--no-install-recommends', name + '=' + version]
        else:
            command = ['dnf', '-y', '--setopt=install_weak_deps=False', 'install', name + '-' + version]
        subprocess.run(command, check=True, env=dict(os.environ, DEBIAN_FRONTEND='noninteractive', LC_ALL='C'),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
        actual = next((p for p in native_packages() if p['name'] == name), {})
        if actual.get('installed') != version:
            raise SystemExit('Requested package version was not installed')
    repaired = repair_fence_pve() if pathlib.Path('/usr/sbin/fence_pve').is_file() else False
    print(json.dumps({'fence_pve_repaired': repaired}))
'''
REFRESH = SOURCE + r'''
profile = platform_profile()
command = ['apt-get', '-o', 'DPkg::Lock::Timeout=60', 'update', '-qq'] if profile['manager'] == 'apt-get' else ['dnf', '-q', 'makecache', '--refresh']
subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
'''


def _parallel(cluster, read):
    checked = service.members(cluster)
    def node(pair):
        from app.modules.db.db_model import close_database_connection
        try:
            return read(*pair)
        finally:
            close_database_connection()
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(node, checked))


def inventory(cluster):
    def node(member, server):
        try:
            found = json.loads(Remote(server).run(['python3', '-c', DISCOVER], timeout=120))
            if not isinstance(found, list) or len(found) > 5000:
                raise ValueError('Invalid agent inventory')
            return {'server_id': member.server_id, 'name': member.name,
                    'agents': sorted({AgentRequest(agent=agent).agent for agent in found}), 'error': None}
        except Exception:
            return {'server_id': member.server_id, 'name': member.name, 'agents': [], 'error': 'Cannot read installed agents'}
    nodes = _parallel(cluster, node)
    names = sorted(set().union(*(set(n['agents']) for n in nodes)))
    return {'nodes': nodes, 'agents': [{'id': name, 'available_on': [n['server_id'] for n in nodes if name in n['agents']],
             'ready': all(not n['error'] and name in n['agents'] for n in nodes)} for name in names]}


def _text(element):
    return ' '.join(' '.join(element.itertext()).split())[:2000] if element is not None else ''


def parse_metadata(xml):
    if len(xml.encode()) > 1024 * 1024:
        raise ValueError('Agent metadata too large')
    # Native OCF metadata commonly declares ra-api-1.dtd. Never load its DTD or entities.
    root = fromstring(xml, forbid_dtd=False, forbid_entities=True, forbid_external=True)
    if root.tag != 'resource-agent':
        raise ValueError('Expected resource-agent metadata')
    parameters = []
    for item in root.findall('./parameters/parameter'):
        name = item.get('name', '')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,100}', name):
            continue
        content = item.find('content')
        secret = bool(re.search(r'passw|passwd|secret|token|private.key', name, re.I))
        parameters.append({'name': name, 'label': _text(item.find('shortdesc')) or name,
            'description': _text(item.find('longdesc')), 'required': item.get('required') in ('1', 'true'),
            'type': content.get('type', 'string') if content is not None else 'string', 'secret': secret,
            'default': None if secret or content is None else content.get('default'),
            'options': [option.get('value', '') for option in content.findall('option')] if content is not None else []})
    if len(parameters) > 200:
        raise ValueError('Too many agent parameters')
    actions = [{key: action.get(key) for key in ('name', 'timeout', 'interval', 'role')}
               for action in root.findall('./actions/action')][:100]
    return {'description': _text(root.find('shortdesc')) or _text(root.find('longdesc')),
            'parameters': parameters, 'actions': actions}


def metadata(cluster, agent):
    agent = AgentRequest(agent=agent).agent
    found = inventory(cluster)
    available = next((item for item in found['agents'] if item['id'] == agent), None)
    if not available or not available['ready']:
        raise RoxywiValidationError('Select an agent installed and discoverable on every cluster node')
    def node(member, server):
        raw = Remote(server).run(['python3', '-c', METADATA], data=json.dumps({'agent': agent}), timeout=45)
        return member.name, parse_metadata(raw)
    values = _parallel(cluster, node)
    common = set.intersection(*(set(p['name'] for p in value['parameters']) for _name, value in values))
    required = set.union(*(set(p['name'] for p in value['parameters'] if p['required']) for _name, value in values))
    if not required <= common:
        raise RoxywiValidationError('Required agent parameters differ between nodes; align agent package versions first')
    first = values[0][1]
    parameters = []
    for parameter in first['parameters']:
        if parameter['name'] not in common:
            continue
        peers = [p for _name, value in values for p in value['parameters'] if p['name'] == parameter['name']]
        defaults = {p['default'] for p in peers}
        options = sorted(set.intersection(*(set(p['options']) for p in peers)))
        if any(p['options'] for p in peers) and not options:
            raise RoxywiValidationError('Agent parameter options differ between nodes; align package versions first')
        parameters.append(dict(parameter, required=any(p['required'] for p in peers),
            default=parameter['default'] if len(defaults) == 1 else None,
            options=options))
    if agent.startswith('stonith:'):
        extras = [
            {'name': 'pcmk_host_check', 'label': 'Host lookup', 'type': 'select', 'default': None,
             'options': ['dynamic-list', 'static-list', 'status', 'none'], 'description': 'How Pacemaker checks the fencing targets. Use static-list with an explicit host list/map.'},
            {'name': 'pcmk_host_list', 'label': 'Cluster host names', 'type': 'string', 'default': None,
             'options': [], 'description': 'Space-separated cluster node names. Use the button to insert the registered names.'},
            {'name': 'pcmk_host_map', 'label': 'Host to fencing target map', 'type': 'string', 'default': None,
             'options': [], 'description': 'Map node names to device outlet or VM IDs: node1:target1;node2:target2. Verify each device target explicitly.'},
        ]
        existing = {p['name'] for p in parameters}
        parameters += [dict(p, required=False, secret=False) for p in extras if p['name'] not in existing]
    return dict(first, parameters=parameters, agent=agent, nodes=[name for name, _value in values])


def validate_resource(cluster, spec):
    found = metadata(cluster, spec.agent)
    missing = [p['name'] for p in found['parameters'] if p['required'] and not p['default'] and not spec.parameters.get(p['name'])]
    # Pacemaker supplies the outlet to fencing agents from the host map at execution time.
    if spec.agent.startswith('stonith:') and (spec.parameters.get('pcmk_host_map') or spec.parameters.get('pcmk_host_list')):
        missing = [name for name in missing if name not in ('port', 'plug')]
    invalid = [p['name'] for p in found['parameters'] if p['options'] and spec.parameters.get(p['name']) and spec.parameters[p['name']] not in p['options']]
    if invalid:
        raise RoxywiValidationError('Invalid option for agent parameters: ' + ', '.join(invalid))
    if missing:
        raise RoxywiValidationError('Missing required agent parameters: ' + ', '.join(missing))


def packages(cluster):
    def node(member, server):
        try:
            data = json.loads(Remote(server).run(['python3', '-c', PACKAGE_QUERY], timeout=120))
            return dict(data, server_id=member.server_id, name=member.name)
        except Exception:
            return {'server_id': member.server_id, 'name': member.name, 'packages': [], 'error': 'Cannot read repository packages'}
    nodes = _parallel(cluster, node)
    names = sorted({p['name'] for n in nodes for p in n['packages'] if re.fullmatch(PACKAGE_PATTERN, p['name'])})
    result = []
    for name in names:
        versions = []
        for node in nodes:
            candidate = next((p for p in node['packages'] if p['name'] == name), {})
            versions.append({'server_id': node['server_id'], 'node': node['name'],
                             'installed': candidate.get('installed'), 'candidate': candidate.get('candidate')})
        ready = all(not n['error'] for n in nodes) and all(v['candidate'] for v in versions)
        plan = {'package': name, 'nodes': versions}
        result.append(dict(plan, ready=ready, needed=any(v['installed'] != v['candidate'] for v in versions),
            plan_digest=hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()))
    return {'nodes': [{'server_id': n['server_id'], 'name': n['name'], 'error': n['error']} for n in nodes], 'packages': result}


def plan(cluster, package, expected_digest):
    if not re.fullmatch(PACKAGE_PATTERN, package):
        raise RoxywiValidationError('Select an agent package from the enabled repositories')
    selected = next((p for p in packages(cluster)['packages'] if p['package'] == package), None)
    if not selected or not selected['ready']:
        raise RoxywiValidationError('This package is not available on every cluster node')
    if selected['plan_digest'] != expected_digest:
        raise RoxywiConflictError('Package candidates changed; reload and review the package plan')
    return selected


def install(cluster, user_id, data):
    with service.locked(cluster) as lease:
        selected = plan(cluster, data['package'], data['plan_digest'])
        checked = service.members(cluster)
        for member, server in checked:
            service.renew_lock(cluster, lease)
            version = next(v['candidate'] for v in selected['nodes'] if v['server_id'] == member.server_id)
            service.event(cluster, user_id, f'agent-package:{data["package"]}:{member.name}', 'started')
            try:
                result = json.loads(Remote(server).run(['python3', '-c', PACKAGE_INSTALL],
                    data=json.dumps({'package': data['package'], 'version': version}), timeout=420))
            except Exception as exc:
                raise RoxywiValidationError(f'Agent package installation failed on {member.name}. Earlier nodes may have completed; rescan before retrying') from exc
            if result['fence_pve_repaired']:
                service.event(cluster, user_id, f'fence-pve-repair:{member.name}', 'completed')
            service.event(cluster, user_id, f'agent-package:{data["package"]}:{member.name}', 'completed')


def refresh_repositories(cluster, user_id):
    with service.locked(cluster) as lease:
        for member, server in service.members(cluster):
            service.renew_lock(cluster, lease)
            Remote(server).run(['python3', '-c', REFRESH], timeout=300)
            service.event(cluster, user_id, f'agent-repositories:{member.name}', 'completed')
