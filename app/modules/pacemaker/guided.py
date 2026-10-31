"""Typed CIB edits for the guided forms; no cluster mutation or shell execution."""
from datetime import datetime
from ipaddress import IPv4Address
from pathlib import PurePosixPath
import re
import xml.etree.ElementTree as ET
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.modules.pacemaker.editor import Identifier
from app.modules.pacemaker.schemas import Candidate, StrictModel
from app.modules.pacemaker.xml import configuration, parse, digest
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiInputError

ID = dict(pattern=Identifier)
TIME = r'^\d{1,10}(ms|s|min|h)$'
SCORE = r'^(-?INFINITY|-?\d{1,10})$'
META = {'resource-stickiness', 'migration-threshold', 'failure-timeout', 'priority', 'target-role',
        'is-managed', 'clone-max', 'clone-node-max', 'promoted-max', 'promoted-node-max',
        'globally-unique', 'notify', 'ordered', 'interleave'}


class Request(StrictModel):
    base_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    kind: Literal['topology', 'location-rule', 'collection', 'operation', 'bundle', 'meta']
    data: dict


class Level(StrictModel):
    index: int = Field(ge=1, le=9)
    devices: list[str] = Field(min_length=1, max_length=32)


class Topology(StrictModel):
    node: str = Field(min_length=1, max_length=63)
    levels: list[Level] = Field(max_length=9)


class Condition(StrictModel):
    kind: Literal['attribute', 'date'] = 'attribute'
    attribute: str = Field(default='#uname', pattern=r'^#?[A-Za-z_][A-Za-z0-9_.:-]{0,127}$')
    operation: Literal['eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'defined', 'not_defined'] = 'eq'
    value: str = Field(default='', max_length=1024)
    type: Literal['string', 'integer', 'number', 'version'] = 'string'
    start: str = Field(default='', max_length=64)
    end: str = Field(default='', max_length=64)

    @model_validator(mode='after')
    def content(self):
        if self.kind == 'date':
            if not self.start or not self.end:
                raise ValueError('A date window requires start and end')
            first, last = datetime.fromisoformat(self.start.replace('Z', '+00:00')), datetime.fromisoformat(self.end.replace('Z', '+00:00'))
            if first.tzinfo is None or last.tzinfo is None or first >= last:
                raise ValueError('Use an increasing date window with explicit timezone offsets')
        elif self.operation not in ('defined', 'not_defined') and not self.value:
            raise ValueError('Specify the attribute comparison value')
        if any(char in self.value for char in '\x00\r\n'):
            raise ValueError('Use a single-line attribute value')
        return self


class Location(StrictModel):
    id: str = Field(**ID)
    resource: str = Field(**ID)
    score: str = Field(default='INFINITY', pattern=SCORE)
    boolean_op: Literal['and', 'or'] = 'and'
    conditions: list[Condition] = Field(min_length=1, max_length=32)


class Collection(StrictModel):
    id: str = Field(**ID)
    kind: Literal['group', 'clone', 'promotable']
    members: list[str] = Field(min_length=1, max_length=32)
    meta: dict[str, str] = Field(default_factory=dict, max_length=16)


class Operation(StrictModel):
    resource: str = Field(**ID)
    id: str | None = Field(default=None, **ID)
    name: Literal['monitor', 'start', 'stop', 'promote', 'demote', 'notify', 'reload', 'reload-agent', 'migrate_to', 'migrate_from']
    interval: str = Field(default='30s', pattern=TIME)
    timeout: str = Field(default='60s', pattern=TIME)
    role: Literal['', 'Started', 'Stopped', 'Promoted', 'Unpromoted'] = ''
    on_fail: Literal['', 'ignore', 'block', 'stop', 'restart', 'fence', 'standby', 'demote'] = ''
    enabled: bool = Field(default=True, strict=True)
    remove: bool = Field(default=False, strict=True)


class Port(StrictModel):
    port: int = Field(ge=1, le=65535)
    internal_port: int | None = Field(default=None, ge=1, le=65535)


class Volume(StrictModel):
    source: str = Field(min_length=1, max_length=1024)
    target: str = Field(min_length=1, max_length=1024)
    source_root: bool = Field(default=False, strict=True)
    options: str = Field(default='ro', pattern=r'^(ro|rw)(,[zZ])?$')

    @field_validator('source', 'target')
    @classmethod
    def absolute_path(cls, value):
        if not PurePosixPath(value).is_absolute() or '..' in PurePosixPath(value).parts or any(char in value for char in '\x00\r\n'):
            raise ValueError('Use an absolute container/host path without traversal')
        return value


class Bundle(StrictModel):
    id: str = Field(**ID)
    engine: Literal['docker', 'podman'] = 'podman'
    image: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,1023}$')
    replicas: int = Field(default=1, ge=1, le=32)
    replicas_per_host: int = Field(default=1, ge=1, le=32)
    promoted_max: int = Field(default=0, ge=0, le=32)
    network: Literal['', 'host', 'bridge'] = ''
    run_command: str = Field(default='', max_length=4096)
    ip_range_start: str = Field(default='', max_length=15)
    host_netmask: int = Field(default=32, ge=0, le=32)
    host_interface: str = Field(default='', pattern=r'^[A-Za-z0-9_.:-]{0,63}$')
    control_port: int | None = Field(default=None, ge=1, le=65535)
    resource: str | None = Field(default=None, **ID)
    ports: list[Port] = Field(default_factory=list, max_length=32)
    volumes: list[Volume] = Field(default_factory=list, max_length=32)

    @model_validator(mode='after')
    def coherent(self):
        if any(char in self.run_command for char in '\x00\r\n'):
            raise ValueError('Use a single-line container startup command')
        if self.promoted_max > self.replicas or self.replicas_per_host > self.replicas:
            raise ValueError('Replica limits exceed the replica count')
        if self.ip_range_start:
            if int(IPv4Address(self.ip_range_start)) + self.replicas - 1 > 2**32-1:
                raise ValueError('Bundle IP range exceeds IPv4')
        if self.resource and not (self.ip_range_start or self.control_port):
            raise ValueError('A managed primitive requires an IP range or explicit Remote control port')
        if self.network == 'host' and self.replicas_per_host != 1:
            raise ValueError('Host networking requires one replica per host')
        if self.resource and self.control_port and self.control_port in {port.port for port in self.ports}:
            raise ValueError('The Remote control port is mapped automatically; do not repeat it')
        if len({port.port for port in self.ports}) != len(self.ports) or len({item.target for item in self.volumes}) != len(self.volumes):
            raise ValueError('Duplicate bundle port or storage target')
        return self


class Meta(StrictModel):
    resource: str = Field(**ID)
    values: dict[str, str] = Field(max_length=16)


def unique(config, base):
    existing = {item.get('id') for item in config.iter()}
    stem = re.sub(r'[^A-Za-z0-9_.-]', '-', base)[:112]
    if not re.match(r'^[A-Za-z_]', stem):
        stem = 'rw-' + stem
    for index in range(10000):
        candidate = stem + (f'-{index}' if index else '')
        if candidate not in existing:
            return candidate
    raise RoxywiInputError('Cannot allocate an unused XML ID')


def require(config, identifier, tags):
    matches = [item for item in config.iter() if item.get('id') == identifier]
    if len(matches) != 1 or matches[0].tag not in tags:
        raise RoxywiInputError('Select an existing resource of the required type')
    return matches[0]


def section(config, name):
    existing = config.find(name)
    return existing if existing is not None else ET.SubElement(config, name)


def own_id(config, identifier, tags):
    found = [item for item in config.iter() if item.get('id') == identifier]
    if not found:
        return None
    return require(config, identifier, tags)


def static_meta(resource):
    groups = resource.findall('meta_attributes')
    if len(groups) > 1 or any(group.get('id-ref') or set(group.attrib)-{'id'} or any(child.tag != 'nvpair' for child in group) for group in groups):
        raise RoxywiInputError('Conditional or referenced meta-attributes require the CIB editor')
    pairs = groups[0].findall('nvpair') if groups else []
    if len({item.get('name') for item in pairs}) != len(pairs):
        raise RoxywiInputError('Duplicate meta-attributes require the CIB editor')
    return {item.get('name'): item.get('value', '') for item in pairs}


def update_meta(config, resource, values):
    static_meta(resource)
    if set(values)-META:
        raise RoxywiInputError('Unsupported meta-attribute')
    for name, value in values.items():
        if name in ('is-managed', 'globally-unique', 'notify', 'ordered', 'interleave') and value not in ('', 'true', 'false'):
            raise RoxywiInputError('Use true/false for boolean meta-attributes')
        if name in ('resource-stickiness', 'priority') and value and not re.fullmatch(SCORE, value):
            raise RoxywiInputError('Invalid resource score')
        if name in ('clone-max','clone-node-max','promoted-max','promoted-node-max') and value and (not value.isdigit() or not 0<=int(value)<=32):
            raise RoxywiInputError('Use a clone limit from 0 to 32')
        if name in ('clone-max', 'clone-node-max', 'promoted-max', 'promoted-node-max', 'migration-threshold') and value and not re.fullmatch(r'\d{1,10}|INFINITY', value):
            raise RoxywiInputError('Use a nonnegative meta-attribute count')
        if name == 'failure-timeout' and value and not re.fullmatch(TIME, value):
            raise RoxywiInputError('Invalid failure timeout')
        if name == 'target-role' and value not in ('', 'Started', 'Stopped', 'Promoted', 'Unpromoted'):
            raise RoxywiInputError('Invalid target role')
        group = resource.find('meta_attributes')
        if group is None and value:
            group = ET.SubElement(resource, 'meta_attributes', id=unique(config, resource.get('id')+'-meta'))
        if group is None:
            continue
        matches = [item for item in group.findall('nvpair') if item.get('name') == name]
        if matches and not value:
            group.remove(matches[0])
        elif matches:
            matches[0].set('value', value)
        elif value:
            ET.SubElement(group, 'nvpair', id=unique(config, resource.get('id')+'-'+name), name=name, value=value)
        if not len(group):
            resource.remove(group)


def topology(config, data, nodes):
    spec = Topology.model_validate(data)
    if spec.node not in nodes:
        raise RoxywiInputError('Select a registered cluster node')
    indexes = [level.index for level in spec.levels]
    if len(set(indexes)) != len(indexes):
        raise RoxywiInputError('Fencing level indexes must be unique')
    for level in spec.levels:
        if len(set(level.devices)) != len(level.devices):
            raise RoxywiInputError('A fencing level cannot repeat a device')
        for identifier in level.devices:
            device = require(config, identifier, {'primitive'})
            template = next((item for item in config.findall('./resources/template') if item.get('id') == device.get('template')), None)
            if device.get('class', template.get('class') if template is not None else '') != 'stonith':
                raise RoxywiInputError('Select fencing devices, not application resources')
    parent = section(config, 'fencing-topology')
    if any(item.get('target-pattern') or item.get('target-attribute') for item in parent):
        raise RoxywiInputError('Pattern/attribute-selected fencing topology requires the CIB editor')
    previous = {item.get('index'): item for item in parent if item.get('target') == spec.node}
    if len(previous) != len([item for item in parent if item.get('target') == spec.node]):
        raise RoxywiInputError('Duplicate fencing levels require the CIB editor')
    for item in list(parent):
        if item.get('target') == spec.node:
            parent.remove(item)
    for level in sorted(spec.levels, key=lambda value:value.index):
        item = previous.get(str(level.index))
        if item is None:
            item = ET.Element('fencing-level', id=unique(config, f'rw-fence-{spec.node}-{level.index}'), target=spec.node, index=str(level.index))
        item.set('devices', ','.join(level.devices)); parent.append(item)
    if not len(parent):
        config.remove(parent)


def location_supported(item):
    if set(item.attrib)-{'id', 'rsc', 'node', 'score'} or any(child.tag != 'rule' for child in item) or len(item.findall('rule')) > 1:
        return False
    for rule in item.findall('rule'):
        if set(rule.attrib)-{'id', 'score', 'boolean-op'} or not rule.get('score'):
            return False
        for child in rule:
            expected = {'id', 'attribute', 'operation', 'value', 'type'} if child.tag == 'expression' else {'id', 'operation', 'start', 'end'}
            if child.tag not in ('expression', 'date_expression') or set(child.attrib)-expected or len(child):
                return False
            if child.tag == 'date_expression' and (child.get('operation') != 'in_range' or not child.get('start') or not child.get('end')):
                return False
    return True


def location(config, data):
    spec = Location.model_validate(data)
    require(config, spec.resource, {'primitive', 'group', 'clone', 'bundle', 'master'})
    item = own_id(config, spec.id, {'rsc_location'})
    if item is not None and not location_supported(item):
        raise RoxywiInputError('This rule uses advanced XML that must be preserved in the CIB editor')
    parent = section(config, 'constraints')
    if item is not None:
        parent.remove(item)
    old_rule=item.find('rule') if item is not None else None
    old_conditions=list(old_rule) if old_rule is not None else []
    item = ET.SubElement(parent, 'rsc_location', id=spec.id, rsc=spec.resource)
    rule = ET.SubElement(item, 'rule', id=old_rule.get('id') if old_rule is not None else unique(config, spec.id+'-rule'), score=spec.score, **{'boolean-op':spec.boolean_op})
    for index, condition in enumerate(spec.conditions):
        identifier = old_conditions[index].get('id') if index<len(old_conditions) else unique(config, f'{spec.id}-condition-{index+1}')
        if condition.kind == 'date':
            ET.SubElement(rule, 'date_expression', id=identifier, operation='in_range', start=condition.start, end=condition.end)
        else:
            attributes = dict(id=identifier, attribute=condition.attribute, operation=condition.operation)
            if condition.operation not in ('defined', 'not_defined'):
                attributes.update(value=condition.value, type=condition.type)
            ET.SubElement(rule, 'expression', attributes)


def collection(config, data):
    spec = Collection.model_validate(data)
    if len(set(spec.members)) != len(spec.members) or spec.id in spec.members:
        raise RoxywiInputError('Collection members must be distinct')
    if spec.kind != 'group' and len(spec.members) != 1:
        raise RoxywiInputError('A clone wraps exactly one primitive or group')
    parent = section(config, 'resources'); existing = own_id(config, spec.id, {'group', 'clone'})
    tag = 'group' if spec.kind == 'group' else 'clone'
    if existing is not None and existing.tag != tag:
        raise RoxywiInputError('Keep the existing collection type; use a separate reviewed conversion')
    if existing is not None and any(item.tag not in ('primitive', 'group', 'meta_attributes') for item in existing):
        raise RoxywiInputError('This collection has advanced options; use the CIB editor')
    children = []
    for identifier in spec.members:
        item = require(config, identifier, {'primitive'} if tag == 'group' else {'primitive', 'group'})
        owner = next((p for p in config.iter() if item in list(p)), None)
        if owner is not parent and owner is not existing:
            raise RoxywiInputError('Select standalone resources or current collection members')
        children.append((owner, item))
    result = existing if existing is not None else ET.SubElement(parent, tag, id=spec.id)
    static_meta(result)
    for item in list(result):
        if item.tag in ('primitive', 'group'):
            result.remove(item)
            if item.get('id') not in spec.members:
                parent.append(item) # Never discard an unselected application resource.
    for owner, item in children:
        if item in list(owner):
            owner.remove(item)
        result.append(item)
    values = dict(spec.meta)
    if spec.kind != 'group':
        values['promotable'] = 'true' if spec.kind == 'promotable' else ''
    # The wrapper's promotable flag is owned by its explicit kind selector.
    flag = values.pop('promotable', None)
    update_meta(config, result, values)
    if flag is not None:
        group = result.find('meta_attributes')
        if group is None and flag:
            group = ET.SubElement(result, 'meta_attributes', id=unique(config, spec.id+'-meta'))
        current = next((item for item in group.findall('nvpair') if item.get('name') == 'promotable'), None) if group is not None else None
        if current is not None and not flag: group.remove(current)
        elif current is not None: current.set('value', flag)
        elif flag: ET.SubElement(group, 'nvpair', id=unique(config, spec.id+'-promotable'), name='promotable', value=flag)
        if group is not None and not len(group):result.remove(group)


def duration(value):
    if value.isdigit():return int(value)
    match = re.fullmatch(r'(\d+)(ms|s|min|h)', value)
    if match is None:raise RoxywiInputError('Existing operation duration requires the CIB editor')
    return int(match[1])*{'ms':1,'s':1000,'min':60000,'h':3600000}[match[2]]


def operation(config, data):
    spec = Operation.model_validate(data); item = require(config, spec.resource, {'primitive'})
    parent = item.find('operations')
    if parent is not None and parent.get('id-ref'):
        raise RoxywiInputError('Referenced operations require the CIB editor')
    if parent is None: parent = ET.SubElement(item, 'operations')
    current = own_id(config, spec.id, {'op'}) if spec.id else None
    if current is not None and current not in list(parent):
        raise RoxywiInputError('Operation belongs to another resource')
    if spec.remove:
        if current is None: raise RoxywiInputError('Select an existing operation to remove')
        parent.remove(current); return
    if duration(spec.timeout) == 0 or (spec.name != 'monitor' and duration(spec.interval) != 0):
        raise RoxywiInputError('Use a positive timeout and zero interval for non-monitor operations')
    for other in parent.findall('op'):
        if other is not current and other.get('name') == spec.name and duration(other.get('interval', '0s')) == duration(spec.interval) and other.get('role', '') == spec.role:
            raise RoxywiInputError('This operation/action interval and role already exist')
    if current is None: current = ET.SubElement(parent, 'op', id=unique(config, spec.resource+'-'+spec.name))
    for key, value in dict(name=spec.name, interval=spec.interval, timeout=spec.timeout, role=spec.role,
                           **{'on-fail':spec.on_fail, 'enabled':'true' if spec.enabled else 'false'}).items():
        if value: current.set(key, value)
        else: current.attrib.pop(key, None)


def bundle_supported(item):
    engines = [child for child in item if child.tag in ('docker', 'podman')]
    if len(engines) != 1 or set(item.attrib)-{'id', 'description'} or any(child.tag not in ('docker','podman','network','storage','primitive','meta_attributes') for child in item): return False
    if set(engines[0].attrib)-{'image','replicas','replicas-per-host','promoted-max','network','run-command'}: return False
    networks=item.findall('network'); storages=item.findall('storage')
    if len(networks)>1 or len(storages)>1 or len(item.findall('primitive'))>1:return False
    for network in networks:
        if set(network.attrib)-{'ip-range-start','host-netmask','host-interface','control-port'}:return False
        if any(child.tag!='port-mapping' or set(child.attrib)-{'id','port','internal-port'} or not child.get('port') for child in network):return False
    for storage in storages:
        if storage.attrib or any(child.tag!='storage-mapping' or set(child.attrib)-{'id','source-dir','source-dir-root','target-dir','options'} for child in storage):return False
    return True


def bundle(config, data):
    spec = Bundle.model_validate(data); parent=section(config,'resources'); existing=own_id(config,spec.id,{'bundle'})
    if existing is not None and not bundle_supported(existing):raise RoxywiInputError('This bundle uses options that must be retained in the CIB editor')
    old=existing.find('primitive') if existing is not None else None
    if old is not None and old.get('id')!=spec.resource:raise RoxywiInputError('Keep the existing bundle primitive; relocating it requires a separate reviewed change')
    primitive=require(config,spec.resource,{'primitive'}) if spec.resource else None
    if primitive is not None and primitive is not old and primitive not in list(parent):raise RoxywiInputError('Only a standalone primitive can be moved into a new bundle')
    result=existing if existing is not None else ET.SubElement(parent,'bundle',id=spec.id)
    for child in list(result):
        if child.tag not in ('primitive','meta_attributes'):result.remove(child)
    attributes=dict(image=spec.image,replicas=str(spec.replicas),**{'replicas-per-host':str(spec.replicas_per_host),'promoted-max':str(spec.promoted_max)})
    if spec.network:attributes['network']=spec.network
    if spec.run_command:attributes['run-command']=spec.run_command
    result.insert(0,ET.Element(spec.engine,attributes))
    if spec.ip_range_start or spec.control_port or spec.ports:
        attributes={}
        if spec.ip_range_start:attributes.update({'ip-range-start':spec.ip_range_start,'host-netmask':str(spec.host_netmask)})
        if spec.host_interface:attributes['host-interface']=spec.host_interface
        if spec.control_port:attributes['control-port']=str(spec.control_port)
        network=ET.Element('network',attributes);result.insert(1,network)
        for index,port in enumerate(spec.ports):
            attributes=dict(id=unique(config,f'{spec.id}-port-{index+1}'),port=str(port.port))
            if port.internal_port:attributes['internal-port']=str(port.internal_port)
            ET.SubElement(network,'port-mapping',attributes)
    if spec.volumes:
        storage=ET.Element('storage');result.insert(2 if result.find('network') is not None else 1,storage)
        for index,volume in enumerate(spec.volumes):
            ET.SubElement(storage,'storage-mapping',id=unique(config,f'{spec.id}-storage-{index+1}'),**{
                'source-dir-root' if volume.source_root else 'source-dir':volume.source,'target-dir':volume.target,'options':volume.options})
    if primitive is not None and primitive is not old:
        parent.remove(primitive);result.append(primitive)


def boolean(value):
    if str(value).lower() in ('true','1','yes','on'):return True
    if str(value).lower() in ('false','0','no','off'):return False
    raise RoxywiInputError('Custom boolean values require the CIB editor')


def display_meta(values):
    return {key: ('true' if boolean(value) else 'false') if key in {'is-managed','globally-unique','notify','ordered','interleave'} else value
            for key,value in values.items() if key in META}


def agent_name(config,item):
    template=next((value for value in config.findall('./resources/template') if value.get('id')==item.get('template')),None)
    attributes=dict(template.attrib) if template is not None else {}
    attributes.update(item.attrib)
    return ':'.join([attributes.get('class',''),*([attributes['provider']] if attributes.get('provider') else []),attributes.get('type','')])


def catalog(xml, nodes):
    root=parse(xml); config=configuration(xml); resources=[]; rules=[]; bundles=[]; collections=[]; operations=[]; unsupported=[]
    for item in config.findall('./resources//*'):
        if item.tag not in ('primitive','group','clone','master','bundle'):continue
        identifier=item.get('id'); parent=next((p for p in config.iter() if item in list(p)),None)
        resources.append(dict(id=identifier,type=item.tag,parent=parent.get('id') if parent is not None else None,agent=agent_name(config,item) if item.tag=='primitive' else ''))
        if item.tag in ('group','clone'):
            try:
                if any(child.tag not in ('primitive','group','meta_attributes') for child in item):raise RoxywiInputError('Custom collection options')
                meta=static_meta(item);kind='promotable' if boolean(meta.get('promotable','false')) else item.tag
                collections.append(dict(id=identifier,kind=kind,members=[child.get('id') for child in item if child.tag in ('primitive','group')],meta=display_meta(meta)))
            except RoxywiInputError:unsupported.append(dict(kind='collection',id=identifier))
        if item.tag=='primitive':
            for op in item.findall('./operations/op'):
                if op.get('id'):
                    values=dict(resource=identifier,id=op.get('id'),name=op.get('name'),interval=op.get('interval','0s'),timeout=op.get('timeout','60s'),role=op.get('role',''),on_fail=op.get('on-fail',''),enabled=boolean(op.get('enabled','true')))
                    for key in ('interval','timeout'):
                        if values[key].isdigit():values[key]+='ms'
                    try:operations.append(Operation.model_validate(values).model_dump(exclude={'remove'}))
                    except ValueError:unsupported.append(dict(kind='operation',id=op.get('id')))
        if item.tag=='bundle':
            if not bundle_supported(item):
                unsupported.append(dict(kind='bundle',id=identifier));continue
            engine=item.find('podman');name='podman'
            if engine is None:engine=item.find('docker');name='docker'
            network=item.find('network');storage=item.find('storage');primitive=item.find('primitive')
            values=dict(id=identifier,engine=name,image=engine.get('image'),replicas=int(engine.get('replicas',1)),replicas_per_host=int(engine.get('replicas-per-host',1)),promoted_max=int(engine.get('promoted-max',0)),network=engine.get('network',''),run_command=engine.get('run-command',''),resource=primitive.get('id') if primitive is not None else None,ports=[],volumes=[])
            if network is not None:
                values.update(ip_range_start=network.get('ip-range-start',''),host_netmask=int(network.get('host-netmask',32)),host_interface=network.get('host-interface',''),control_port=int(network.get('control-port')) if network.get('control-port') else None)
                values['ports']=[dict(port=int(port.get('port')),internal_port=int(port.get('internal-port')) if port.get('internal-port') else None) for port in network]
            if storage is not None:values['volumes']=[dict(source=value.get('source-dir',value.get('source-dir-root')),target=value.get('target-dir'),source_root=value.get('source-dir-root') is not None,options=value.get('options','ro')) for value in storage]
            try:Bundle.model_validate(values)
            except ValueError:
                unsupported.append(dict(kind='bundle',id=identifier));continue
            bundles.append(values)
    for item in config.findall('./constraints/rsc_location'):
        if not location_supported(item):
            unsupported.append(dict(kind='location-rule',id=item.get('id')));continue
        rule=item.find('rule');conditions=[]
        if rule is None:
            conditions=[dict(kind='attribute',attribute='#uname',operation='eq',value=item.get('node'),type='string')]
        else:
            for child in rule:
                conditions.append(dict(kind='attribute',attribute=child.get('attribute'),operation=child.get('operation'),value=child.get('value',''),type=child.get('type','string')) if child.tag=='expression' else dict(kind='date',start=child.get('start'),end=child.get('end')))
        rules.append(dict(id=item.get('id'),resource=item.get('rsc'),score=item.get('score','INFINITY') if rule is None else rule.get('score'),boolean_op=rule.get('boolean-op','and') if rule is not None else 'and',conditions=conditions))
    topology_values={node:[] for node in nodes}
    for item in config.findall('./fencing-topology/fencing-level'):
        if item.get('target') in topology_values:topology_values[item.get('target')].append(dict(index=int(item.get('index')),devices=item.get('devices','').split(',')))
    for entry in resources:
        try:entry['meta']=display_meta(static_meta(require(config,entry['id'],{'primitive','group','clone','master','bundle'})))
        except RoxywiInputError:
            entry['meta']=None;unsupported.append(dict(kind='meta',id=entry['id']))
    attributes=sorted({'#uname','#id','#kind',*[value.get('name') for value in root.findall('.//node//nvpair') if value.get('name')]})
    return dict(base_digest=digest(xml),resources=resources,collections=collections,bundles=bundles,rules=rules,
                operations=operations,topology=topology_values,nodes=list(nodes),attributes=attributes,unsupported=unsupported,
                topology_supported=not any(value.get('target-pattern') or value.get('target-attribute') for value in config.findall('./fencing-topology/fencing-level')))


def build(xml, body, nodes):
    if digest(xml)!=body.base_digest:raise RoxywiConflictError('Configuration changed; reload the wizard')
    root=parse(xml); config=root.find('configuration')
    if len({value.get('id') for value in config.iter() if value.get('id')})!=len([value for value in config.iter() if value.get('id')]):
        raise RoxywiInputError('Existing duplicate XML IDs must be repaired before guided editing')
    if body.kind=='topology':topology(config,body.data,nodes)
    elif body.kind=='location-rule':location(config,body.data)
    elif body.kind=='collection':collection(config,body.data)
    elif body.kind=='operation':operation(config,body.data)
    elif body.kind=='bundle':bundle(config,body.data)
    elif body.kind=='meta':
        spec=Meta.model_validate(body.data);update_meta(config,require(config,spec.resource,{'primitive','group','clone','bundle'}),spec.values)
    return Candidate(xml=ET.tostring(root,encoding='unicode'),base_digest=body.base_digest)
