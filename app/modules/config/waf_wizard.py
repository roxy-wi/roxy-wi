"""Versioned WAF form generation; managed comments are not a SecLang parser."""
import ipaddress
import json
from pathlib import Path
import re
import string
import tempfile

from app.modules.common import common
from app.modules.config import config
from app.modules.db import sql, waf as waf_sql
from app.modules.roxywi import waf, common as roxywi_common
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiValidationError
from app.modules.subscription.access import WAF_WIZARD, require_feature


START = '# BEGIN Roxy-WI MANAGED WAF do not edit it directly'
END = '# END Roxy-WI MANAGED WAF do not edit it directly'
METADATA = '# Roxy-WI WAF Wizard v1: '
METADATA_V2 = '# Roxy-WI WAF Wizard v2: '
MAX_CONDITIONS = 10
FIELDS = {'ip': 'REMOTE_ADDR', 'uri': 'REQUEST_FILENAME', 'method': 'REQUEST_METHOD',
          'header': 'REQUEST_HEADERS', 'arg': 'ARGS'}
DEFAULT = dict(version=1, id=10000, kind='rule', field='uri', key='', operator='equals',
               value='', action='deny', exclude_id=0, exclude_parameter='')


class WizardError(RoxywiValidationError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _text(value, maximum=1024, *, empty=False):
    if (not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip())
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise WizardError('invalid')
    return value.strip()


def _condition(data: dict) -> dict:
    if not isinstance(data, dict) or set(data) != {'field', 'key', 'operator', 'value'}:
        raise WizardError('invalid')
    if (not isinstance(data['field'], str) or data['field'] not in FIELDS
            or data['operator'] not in ('equals', 'contains', 'begins')):
        raise WizardError('invalid')
    result = {**data, 'value': _text(data['value']), 'key': _text(data['key'], 128, empty=True)}
    if result['field'] in ('header', 'arg'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', result['key']):
            raise WizardError('invalid')
    else:
        result['key'] = ''
    if result['field'] == 'ip':
        try:
            result['value'] = ','.join(str(ipaddress.ip_network(item.strip(), strict=False))
                                       for item in result['value'].split(','))
        except ValueError as exc:
            raise WizardError('invalid') from exc
        result['operator'] = 'equals'
    if result['field'] == 'uri' and not result['value'].startswith('/'):
        raise WizardError('invalid')
    return result


def validate_spec(data: dict, *, allow_auto=False) -> dict:
    if isinstance(data, dict) and data.get('version') == 2:
        allowed = {'version', 'id', 'kind', 'action', 'match', 'conditions', 'exclude_id', 'exclude_parameter'}
        if set(data) != allowed or type(data['version']) is not int:
            raise WizardError('invalid')
        spec = data.copy()
        if (spec['kind'] not in ('rule', 'exclusion') or spec['match'] not in ('all', 'any')
                or spec['action'] not in ('deny', 'log')
                or not isinstance(spec['conditions'], list) or len(spec['conditions']) > MAX_CONDITIONS):
            raise WizardError('invalid')
        spec['conditions'] = [_condition(item) for item in spec['conditions']]
        if spec['kind'] == 'rule':
            if not spec['conditions']:
                raise WizardError('invalid')
            spec.update(exclude_id=0, exclude_parameter='')
        else:
            if (type(spec['exclude_id']) is not int or not 1 <= spec['exclude_id'] <= 2147483647
                    or any(item['field'] == 'arg' for item in spec['conditions'])):
                raise WizardError('invalid')
            parameter = _text(spec['exclude_parameter'], 128, empty=True)
            if parameter and not re.fullmatch(r'[A-Za-z0-9_.-]+', parameter):
                raise WizardError('invalid')
            spec.update(action='log', exclude_parameter=parameter)
        if spec['id'] is None and allow_auto:
            return spec
        if type(spec['id']) is not int or not 1 <= spec['id'] <= 99999:
            raise WizardError('invalid')
        ids = rule_ids(spec)
        if ids[-1] > 99999 or (spec['kind'] == 'exclusion' and spec['exclude_id'] in ids):
            raise WizardError('invalid')
        return spec
    if not isinstance(data, dict) or set(data) - set(DEFAULT):
        raise WizardError('invalid')
    spec = {**DEFAULT, **data}
    if any(not isinstance(spec[key], str) for key, value in DEFAULT.items() if isinstance(value, str)):
        raise WizardError('invalid')
    automatic = spec['id'] is None and allow_auto
    if (type(spec['version']) is not int or spec['version'] != 1
            or (not automatic and (type(spec['id']) is not int or not 1 <= spec['id'] <= 99999))
            or spec['kind'] not in ('rule', 'exclusion')
            or spec['operator'] not in ('equals', 'contains', 'begins')):
        raise WizardError('invalid')
    if spec['kind'] == 'exclusion':
        spec.update(field='uri', key='', action='log')
        if (type(spec['exclude_id']) is not int or not 1 <= spec['exclude_id'] <= 2147483647
                or spec['exclude_id'] == spec['id']):
            raise WizardError('invalid')
        parameter = _text(spec['exclude_parameter'], 128, empty=True)
        if parameter and not re.fullmatch(r'[A-Za-z0-9_.-]+', parameter):
            raise WizardError('invalid')
        spec['exclude_parameter'] = parameter
        spec['value'] = _text(spec['value'], empty=True)
        if spec['value'] and not spec['value'].startswith('/'):
            raise WizardError('invalid')
    else:
        if spec['field'] not in FIELDS or spec['action'] not in ('deny', 'log'):
            raise WizardError('invalid')
        spec.update(exclude_id=0, exclude_parameter='')
        spec['value'] = _text(spec['value'])
        spec['key'] = _text(spec['key'], 128, empty=True)
        if spec['field'] in ('header', 'arg'):
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', spec['key']):
                raise WizardError('invalid')
        else:
            spec['key'] = ''
        if spec['field'] == 'ip':
            try:
                networks = [ipaddress.ip_network(item.strip(), strict=False) for item in spec['value'].split(',')]
            except ValueError as exc:
                raise WizardError('invalid') from exc
            spec['value'] = ','.join(str(network) for network in networks)
            spec['operator'] = 'equals'
        if spec['field'] == 'uri' and not spec['value'].startswith('/'):
            raise WizardError('invalid')
    return spec


def form_spec(spec: dict) -> dict:
    """Upgrade saved v1 metadata for the form without parsing handwritten rules."""
    if spec['version'] == 2:
        return spec
    conditions = ([{key: spec[key] for key in ('field', 'key', 'operator', 'value')}]
                  if spec['kind'] != 'exclusion' or spec['value'] else [])
    return {**{key: spec[key] for key in ('id', 'kind', 'action', 'exclude_id', 'exclude_parameter')},
            'version': 2, 'match': 'all', 'conditions': conditions}


def rule_ids(spec: dict) -> list[int]:
    count = max(1, len(spec['conditions'])) if spec.get('match') == 'any' else 1
    return list(range(spec['id'], spec['id'] + count))


def available_id(used: set[int], count=1) -> int:
    """Allocate a consecutive block for OR branches, preferring the local range."""
    for candidates in (range(10000, 100000), range(1, min(100000, 10000 + count - 1))):
        run = 0
        for identifier in candidates:
            run = 0 if identifier in used else run + 1
            if run == count:
                return identifier - count + 1
    raise WizardError('ids_exhausted')


def _expression(condition: dict) -> str:
    variable = FIELDS[condition['field']] + (':' + condition['key'] if condition['key'] else '')
    if condition['field'] == 'ip':
        operator = '@ipMatch ' + condition['value']
    else:
        # Literal UTF-8 values cannot inject SecLang quoting, macros or regex.
        literal = string.ascii_letters + string.digits + '/_- '
        pattern = ''.join(chr(byte) if chr(byte) in literal else f'\\x{byte:02x}'
                          for byte in condition['value'].encode('utf-8'))
        if condition['operator'] != 'contains':
            pattern = '^' + pattern
        if condition['operator'] == 'equals':
            pattern += '$'
        operator = '@rx ' + pattern
    return f'SecRule {variable} "{operator}"'


def _actions(spec: dict, identifier: int, phase: int) -> tuple[str, str]:
    actions = f'id:{identifier},phase:{phase},t:none,'
    if spec['kind'] == 'exclusion':
        target = spec['exclude_id']
        exclusion = (f'ruleRemoveTargetById={target};ARGS:{spec["exclude_parameter"]}'
                     if spec['exclude_parameter'] else f'ruleRemoveById={target}')
        return actions + 'pass,nolog', ',ctl:' + exclusion
    actions += ('deny,status:403' if spec['action'] == 'deny' else 'pass')
    return actions + f",log,msg:'Roxy-WI WAF rule {spec['id']}'", ''


def render_rule(data: dict) -> str:
    spec = validate_spec(data)
    current = form_spec(spec)
    conditions = current['conditions']
    groups = [[item] for item in conditions] if current['match'] == 'any' else [conditions]
    lines = []
    for identifier, group in zip(rule_ids(current), groups or [[]]):
        phase = 2 if any(item['field'] == 'arg' for item in group) else 1
        actions, effect = _actions(current, identifier, phase)
        if not group:
            lines.append(f'SecAction "{actions}{effect}"')
        for index, condition in enumerate(group):
            # Disruptive actions/ID/phase belong to the chain starter. Runtime
            # exclusions must run ONLY on the last match (also on ModSecurity 2).
            part = actions if index == 0 else 't:none'
            part += ',chain' if index < len(group) - 1 else effect
            lines.append(f'{_expression(condition)} "{part}"')
    metadata = METADATA_V2 if spec['version'] == 2 else METADATA
    return '\n'.join([START, '# Generated by Roxy-WI. Use WAF Config Wizard to edit this rule.',
                      metadata + json.dumps(spec, ensure_ascii=True, sort_keys=True), *lines, END, ''])


def read_spec(content: str) -> dict:
    # The form owns these files. Do not import handwritten directives or merge
    # changes made against the explicit managed-file warning.
    lines = content.splitlines()
    values = [line[len(prefix):] for line in lines for prefix in (METADATA, METADATA_V2) if line.startswith(prefix)]
    if not lines or lines[0] != START or len(values) != 1 or END not in lines:
        raise WizardError('metadata_missing')
    try:
        return validate_spec(json.loads(values[0]))
    except (ValueError, TypeError, WizardError) as exc:
        raise WizardError('metadata_missing') from exc


def read_rule(server_ip: str, rule) -> str:
    with tempfile.TemporaryDirectory(prefix='waf-wizard-read-', dir=sql.get_setting('tmp_config_path')) as workdir:
        path = Path(workdir) / rule.rule_file
        config.get_config(server_ip, str(path), waf=rule.service, waf_rule_file=rule.rule_file)
        return path.read_text(encoding='utf-8')


def _identity(data: dict) -> dict:
    if not isinstance(data, dict):
        raise WizardError('invalid')
    result = {key: _text(data.get(key), maximum) for key, maximum in (
        ('new_waf_rule', 255), ('new_rule_file', 255), ('new_rule_description', 4096))}
    filename = result['new_rule_file']
    if not filename.endswith('.conf'):
        filename += '.conf'
    if len(filename) > 255 or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9._-]*\.conf', filename):
        raise WizardError('invalid')
    result['new_rule_file'] = filename
    return result


def id_inventory(targets: list, service: str, filename: str) -> dict[str, set[int]]:
    result = {}
    for node in targets:
        try:
            inventory = waf.run_waf_file_command(node.ip, common.get_waf_directory(service),
                ['inspect-ids', common.get_waf_entrypoint(service), common.resolve_waf_config_path(service, filename)])
            ids = inventory.get('ids')
            if not isinstance(ids, list) or any(type(value) is not int for value in ids):
                raise RuntimeError('Unconfirmed WAF rule ID inventory')
            result[node.ip] = set(ids)
        except Exception as exc:
            if len(targets) == 1:
                raise
            raise waf.WafSyncError(node.ip, 'inspection_failed') from exc
    return result


def preview_or_save(server_ip: str, service: str, data: dict, rule_id=None) -> dict:
    require_feature(WAF_WIZARD)
    roxywi_common.check_is_server_in_group(server_ip)
    if not isinstance(data, dict):
        raise WizardError('invalid')
    identity = _identity(data)
    spec = validate_spec(data.get('spec'), allow_auto=True)
    action = data.get('action')
    if action not in ('preview', 'save', 'restart' if service == 'haproxy' else 'reload'):
        raise WizardError('invalid')
    with waf.rule_operation(server_ip, service) as targets:
        if rule_id is not None:
            rule = waf.get_waf_rule(server_ip, rule_id, service)
            if not rule.wizard:
                raise WizardError('not_managed')
            if (rule.rule_name, rule.rule_file, rule.desc) != tuple(identity[key] for key in (
                    'new_waf_rule', 'new_rule_file', 'new_rule_description')):
                raise WizardError('identity_changed')
        else:
            conflicts = waf_sql.find_waf_rule_conflicts(server_ip, service, identity['new_waf_rule'], identity['new_rule_file'])
            rule = conflicts[0] if len(conflicts) == 1 else None
            if conflicts and (not rule or not rule.wizard or
                              (rule.rule_name, rule.rule_file, rule.desc) != tuple(identity.values())):
                raise RoxywiConflictError('A different WAF rule already uses this name or file')
        if rule:
            previous = read_rule(server_ip, rule)
            # A failed initial upload can leave the existing creation marker.
            if previous.startswith('# Roxy-WI rule creation:'):
                previous = ''
            else:
                previous_spec = read_spec(previous)
                if spec['id'] is None and rule_id is None:
                    # Retain the ID after a lost response to an automatic save.
                    spec['id'] = previous_spec['id']
                if rule_id is None and form_spec(previous_spec) != form_spec(spec):
                    raise RoxywiConflictError('Use the existing wizard rule to edit it')
        else:
            previous = ''
        if rule:
            for node in targets[1:]:
                waf.replica_rule(node, rule)
        inventories = id_inventory(targets, service, identity['new_rule_file'])
        used = set().union(*inventories.values())
        if spec['id'] is None:
            count = max(1, len(spec['conditions'])) if spec.get('match') == 'any' else 1
            reserved = used | ({spec['exclude_id']} if spec['kind'] == 'exclusion' else set())
            spec['id'] = available_id(reserved, count)
        spec = validate_spec(spec)
        ids = rule_ids(spec)
        if used.intersection(ids):
            raise WizardError('id_conflict')
        if spec['kind'] == 'exclusion' and any(spec['exclude_id'] not in values for values in inventories.values()):
            raise WizardError('target_missing')
        content = render_rule(spec)
        if action == 'preview':
            return dict(status='ok', config=content, previous=previous, rule_ids=ids)
        for node in targets:
            config.validate_waf_action(node.ip, service, action)
        if not rule:
            new_id = waf.create_waf_rule(server_ip, service, identity, wizard=True)
            rule = waf.get_waf_rule(server_ip, new_id, service)
        with tempfile.TemporaryDirectory(prefix='waf-wizard-save-', dir=sql.get_setting('tmp_config_path')) as workdir:
            path = Path(workdir) / rule.rule_file
            path.write_text(content, encoding='utf-8', newline='')
            waf.save_waf_rule(server_ip, rule.id, str(path), action, service)
        return dict(status='ok', id=rule.id, rule_ids=ids)
