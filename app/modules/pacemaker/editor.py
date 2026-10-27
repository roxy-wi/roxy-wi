"""Small form builders; the lossless CIB editor covers advanced agent options."""
import re
import xml.etree.ElementTree as ET
from typing import Literal

from pydantic import Field, field_validator

from app.modules.roxywi.exception import RoxywiInputError
from app.modules.pacemaker.schemas import StrictModel, Candidate, AGENT_PATTERN
from app.modules.pacemaker.xml import parse, configuration


Identifier = r'^[A-Za-z_][A-Za-z0-9_.-]{0,127}$'


class Resource(StrictModel):
    id: str = Field(pattern=Identifier)
    agent: str = Field(pattern=AGENT_PATTERN)
    parameters: dict[str, str] = Field(default_factory=dict, max_length=100)
    monitor_interval: str = Field(default='30s', pattern=r'^\d+(ms|s|min|h)$')
    start_timeout: str | None = Field(default=None, pattern=r'^\d+(ms|s|min|h)$')
    stop_timeout: str | None = Field(default=None, pattern=r'^\d+(ms|s|min|h)$')
    monitor_timeout: str | None = Field(default=None, pattern=r'^\d+(ms|s|min|h)$')
    wrapper: Literal['none', 'group', 'clone', 'promotable'] = 'none'
    wrapper_id: str | None = Field(default=None, pattern=Identifier)

    @field_validator('parameters')
    @classmethod
    def parameter_names(cls, values):
        if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,100}', key) or len(value) > 4096 for key, value in values.items()):
            raise RoxywiInputError('Invalid resource parameters')
        return values


class Constraint(StrictModel):
    id: str = Field(pattern=Identifier)
    type: Literal['location', 'order', 'colocation']
    resource: str = Field(pattern=Identifier)
    other: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_.-]{0,127}$')
    score: str = Field(default='INFINITY', pattern=r'^(-?INFINITY|-?\d{1,10})$')


class Edit(StrictModel):
    base_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    kind: Literal['resource', 'constraint', 'property', 'delete']
    data: dict


def _section(config, name):
    existing = config.find(name)
    return existing if existing is not None else ET.SubElement(config, name)


def _unused(config, identifier):
    if any(element.get('id') == identifier for element in config.iter()):
        raise RoxywiInputError('This XML ID already exists; use the CIB editor to change it')


def build(xml, body: Edit):
    root = parse(xml)
    config = configuration(xml)
    root.remove(root.find('configuration'))
    root.insert(0, config)
    if body.kind == 'resource':
        spec = Resource.model_validate(body.data)
        _unused(config, spec.id)
        resources = _section(config, 'resources')
        parent = resources
        if spec.wrapper != 'none':
            if not spec.wrapper_id:
                raise RoxywiInputError('Specify a group or clone ID')
            _unused(config, spec.wrapper_id)
            parent = ET.SubElement(resources, 'group' if spec.wrapper == 'group' else 'clone', id=spec.wrapper_id)
            if spec.wrapper == 'promotable':
                meta = ET.SubElement(parent, 'meta_attributes', id=f'{spec.wrapper_id}-meta')
                ET.SubElement(meta, 'nvpair', id=f'{spec.wrapper_id}-promotable', name='promotable', value='true')
        parts = spec.agent.split(':')
        attrs = {'id': spec.id, 'class': parts[0], 'type': parts[-1]}
        if parts[0] == 'ocf':
            attrs['provider'] = parts[1]
        resource = ET.SubElement(parent, 'primitive', attrs)
        if spec.parameters:
            parameters = ET.SubElement(resource, 'instance_attributes', id=f'{spec.id}-params')
            for name, value in spec.parameters.items():
                ET.SubElement(parameters, 'nvpair', id=f'{spec.id}-param-{name}', name=name, value=value)
        operations = ET.SubElement(resource, 'operations')
        monitor = ET.SubElement(operations, 'op', id=f'{spec.id}-monitor', name='monitor', interval=spec.monitor_interval)
        if spec.monitor_timeout:
            monitor.set('timeout', spec.monitor_timeout)
        for action in ('start', 'stop'):
            timeout = getattr(spec, action + '_timeout')
            if timeout:
                ET.SubElement(operations, 'op', id=f'{spec.id}-{action}', name=action, interval='0', timeout=timeout)
    elif body.kind == 'constraint':
        spec = Constraint.model_validate(body.data)
        _unused(config, spec.id)
        attrs = {'id': spec.id}
        if spec.type == 'location':
            attrs.update(rsc=spec.resource, node=spec.other, score=spec.score)
        elif spec.type == 'colocation':
            attrs.update(rsc=spec.resource, **{'with-rsc': spec.other, 'score': spec.score})
        else:
            attrs.update(first=spec.resource, then=spec.other, kind='Mandatory')
        ET.SubElement(_section(config, 'constraints'), f'rsc_{spec.type}', attrs)
    elif body.kind == 'property':
        name, value = body.data.get('name', ''), body.data.get('value', '')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,100}', name):
            raise RoxywiInputError('Invalid cluster property')
        if not isinstance(value, str) or len(value) > 4096:
            raise RoxywiInputError('Invalid cluster property value')
        section = _section(config, 'crm_config')
        matches = section.findall(f"./cluster_property_set/nvpair[@name='{name}']")
        if matches:
            for match in matches:
                match.set('value', value)
        else:
            properties = section.find('cluster_property_set')
            if properties is None:
                properties = ET.SubElement(section, 'cluster_property_set', id='roxywi-properties')
            ET.SubElement(properties, 'nvpair', id=f'roxywi-property-{name}', name=name, value=value)
    else:
        identifier = body.data.get('id', '')
        if not isinstance(identifier, str) or not re.fullmatch(Identifier, identifier):
            raise RoxywiInputError('Invalid resource or constraint ID')
        removed = False
        for section_name in ('resources', 'constraints'):
            section = config.find(section_name)
            if section is None:
                continue
            for parent in section.iter():
                for child in list(parent):
                    if child.get('id') == identifier and child.tag in ('primitive', 'group', 'clone', 'master', 'bundle', 'rsc_location', 'rsc_order', 'rsc_colocation', 'rsc_ticket'):
                        parent.remove(child)
                        removed = True
        if not removed:
            raise RoxywiInputError('Resource or constraint not found')
    return Candidate(xml=ET.tostring(root, encoding='unicode'), base_digest=body.base_digest)
