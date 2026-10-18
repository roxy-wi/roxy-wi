import json
import importlib

import pytest
from peewee import IntegrityError, SqliteDatabase

from app.modules.config import waf_wizard as wizard
from app.modules.roxywi import waf_rule_file as remote
from app.modules.db.db_model import WafRules


@pytest.mark.parametrize('field,value,key,expected', [
    ('uri', '/admin', '', 'REQUEST_FILENAME'), ('method', 'DELETE', '', 'REQUEST_METHOD'),
    ('header', 'bad bot', 'User-Agent', 'REQUEST_HEADERS:User-Agent'),
    ('arg', 'injection', 'q', 'ARGS:q'), ('ip', '192.0.2.3,2001:db8::/32', '', 'REMOTE_ADDR'),
])
def test_generator_round_trips_form_metadata_and_uses_request_phase(field, value, key, expected):
    spec = {**wizard.DEFAULT, 'field': field, 'value': value, 'key': key}
    content = wizard.render_rule(spec)
    assert content.startswith(wizard.START) and wizard.END in content
    assert 'Use WAF Config Wizard' in content
    assert f'SecRule {expected} ' in content
    assert f'phase:{2 if field == "arg" else 1}' in content
    assert wizard.read_spec(content) == wizard.validate_spec(spec)


@pytest.mark.parametrize('value', ['" deny,id:42', '\\', '%{REMOTE_ADDR}', '中文 & <script>'])
def test_literal_values_cannot_inject_directives_macros_or_regular_expressions(value):
    content = wizard.render_rule({**wizard.DEFAULT, 'field': 'header', 'key': 'X-Test', 'value': value})
    directive = next(line for line in content.splitlines() if line.startswith('SecRule'))
    if value == '\\':
        assert '"@rx ^\\x5c$"' in directive
    else:
        assert value not in directive
    assert directive.count('SecRule') == 1 and directive.count('id:') == 1
    assert directive.count('"') == 4


@pytest.mark.parametrize('patch', [
    {'id': True}, {'id': 100000}, {'id': '42'}, {'field': []}, {'action': 'allow'},
    {'operator': 'regex'}, {'value': 'foo\nSecRuleEngine Off'}, {'extra': 'directive'},
    {'field': 'header', 'key': 'X-Test|ARGS'}, {'field': 'ip', 'value': 'invalid'},
    {'kind': 'exclusion', 'exclude_id': 10000}, {'kind': 'exclusion', 'exclude_id': 0},
    {'kind': 'exclusion', 'exclude_id': 942100, 'exclude_parameter': 'foo,ctl:ruleEngine=Off'},
])
def test_generator_rejects_invalid_or_unsafe_fields(patch):
    with pytest.raises(wizard.WizardError):
        wizard.render_rule({**wizard.DEFAULT, 'value': '/admin', **patch})


@pytest.mark.parametrize('parameter', ['', 'body'])
@pytest.mark.parametrize('value', ['', '/submit'])
def test_runtime_exclusion_has_narrow_target_and_phase_one(parameter, value):
    content = wizard.render_rule({**wizard.DEFAULT, 'kind': 'exclusion', 'value': value,
                                  'exclude_id': 942100, 'exclude_parameter': parameter})
    directive = next(line for line in content.splitlines() if line.startswith('Sec'))
    assert 'phase:1,t:none,pass,nolog,ctl:' in directive
    assert ('ruleRemoveTargetById=942100;ARGS:body' if parameter else 'ruleRemoveById=942100') in directive
    assert directive.startswith('SecRule ' if value else 'SecAction ')
    assert 'ruleEngine' not in directive


def test_form_reads_only_its_metadata_not_handwritten_rule_changes():
    content = wizard.render_rule({**wizard.DEFAULT, 'value': '/admin'})
    edited = content.replace('deny,status:403', 'pass')
    assert wizard.read_spec(edited)['action'] == 'deny'
    with pytest.raises(wizard.WizardError):
        wizard.read_spec('SecRule ARGS "attack" "id:10000,deny"')


def include(path):
    return 'Include ' + json.dumps(str(path)) + '\n'


@pytest.mark.parametrize('service', ['nginx', 'haproxy'])
def test_generated_file_precedes_crs_and_keeps_order_when_toggled(tmp_path, service):
    root = tmp_path / 'waf'
    (root / 'rules').mkdir(parents=True)
    base = root / 'modsecurity.conf'
    crs = root / 'rules/crs.conf'
    crs.write_text('SecRule ARGS "test" "id:942100,phase:2,deny"\n')
    base.write_text('SecRuleEngine On\n' + include(crs))
    entry = base if service == 'haproxy' else root / 'waf.conf'
    if entry != base:
        entry.write_text(include(base))
    rule = root / 'rules/generated.conf'
    remote.create_rule(entry, rule, 'a' * 64, before_rules=True)
    text = entry.read_text()
    assert text.index('generated.conf') < text.index('crs.conf' if service == 'haproxy' else 'modsecurity.conf')
    remote.switch_rule(entry, rule, 0)
    remote.switch_rule(entry, rule, 1)
    assert entry.read_text() == text
    assert remote.inspect_rule_ids(entry, rule) == [942100]


def test_id_inventory_includes_disabled_files_nested_includes_and_ignores_current_file(tmp_path):
    root = tmp_path / 'waf'
    (root / 'rules').mkdir(parents=True)
    entry = root / 'modsecurity.conf'
    other = tmp_path / 'external.conf'
    other.write_text('SecAction "id:\'201\',phase:1,pass"\n')
    entry.write_text('SecRuleEngine On\n' + include(other))
    disabled = root / 'rules/disabled.conf'
    disabled.write_text('# id:666\nSecRule ARGS "test" \\\n"id:202,phase:2,deny"\n')
    current = root / 'rules/current.conf'
    current.write_text(wizard.render_rule({**wizard.DEFAULT, 'value': '/admin'}))
    assert remote.inspect_rule_ids(entry, current) == [201, 202]


def test_generated_rule_refuses_wildcard_placement(tmp_path):
    root = tmp_path / 'waf'
    (root / 'rules').mkdir(parents=True)
    entry = root / 'modsecurity.conf'
    entry.write_text(include(root / 'rules/*.conf'))
    with pytest.raises(remote.RuleConflict):
        remote.create_rule(entry, root / 'rules/new.conf', 'a' * 64, before_rules=True)
    assert not (root / 'rules/new.conf').exists()


@pytest.mark.parametrize('table_constraint', ['', ', UNIQUE (serv, rule_name, service)'])
def test_upgrade_preserves_existing_manual_rules_and_is_repeatable(tmp_path, table_constraint):
    database = SqliteDatabase(tmp_path / 'old-waf.db')
    with database.bind_ctx([WafRules], bind_refs=False, bind_backrefs=False):
        database.execute_sql('CREATE TABLE waf_rules (id INTEGER PRIMARY KEY, serv TEXT, rule_name TEXT, '
                             'rule_file TEXT, desc TEXT, en INTEGER, service TEXT' + table_constraint + ')')
        database.execute_sql("INSERT INTO waf_rules VALUES (1, '192.0.2.1', 'Manual', 'manual.conf', '', 1, 'nginx')")
        migration = importlib.import_module('app.modules.db.migrations.20261017000000_waf_wizard')
        migration.up()
        migration.up()
        old = WafRules.get_by_id(1)
        assert old.rule_name == 'Manual' and not old.wizard
        generated = WafRules.create(serv=old.serv, rule_name='Generated', rule_file='new.conf',
                                    en=1, service='nginx', wizard=True)
        assert WafRules.get_by_id(generated.id).wizard
        if table_constraint:
            with pytest.raises(IntegrityError, match='UNIQUE constraint failed'):
                database.execute_sql("INSERT INTO waf_rules (serv, rule_name, rule_file, service) "
                                     "VALUES ('192.0.2.1', 'Manual', 'duplicate.conf', 'nginx')")
        database.execute_sql("INSERT INTO waf_rules (serv, rule_name, rule_file, service) "
                             "VALUES ('192.0.2.1', 'Default', 'default.conf', 'nginx')")
        assert not WafRules.get(WafRules.rule_name == 'Default').wizard
    database.close()


def compound_spec(**changes):
    return dict(version=2, id=10000, kind='rule', action='deny', match='all', exclude_id=0,
                exclude_parameter='', conditions=[
                    dict(field='uri', key='', operator='equals', value='/submit'),
                    dict(field='method', key='', operator='equals', value='POST'),
                ], **changes)


def test_and_chain_defers_disruption_until_all_conditions_match():
    spec = compound_spec()
    spec['conditions'].append(dict(field='arg', key='body', operator='contains', value='attack'))
    text = wizard.render_rule(spec)
    lines = [line for line in text.splitlines() if line.startswith('SecRule')]
    assert len(lines) == 3
    assert 'id:10000,phase:2,t:none,deny,status:403,log' in lines[0]
    assert lines[0].endswith(',chain"') and lines[1].endswith('"t:none,chain"')
    assert lines[2].endswith('"t:none"')
    assert wizard.read_spec(text) == spec


def test_or_branches_use_unique_ids_and_do_not_chain():
    spec = compound_spec()
    spec['match'] = 'any'
    text = wizard.render_rule(spec)
    assert 'chain' not in text
    assert text.count('deny,status:403') == 2
    assert 'id:10000,phase:1' in text and 'id:10001,phase:1' in text
    assert wizard.rule_ids(spec) == [10000, 10001]


def test_or_body_condition_does_not_delay_header_branch_to_phase_two():
    spec = compound_spec()
    spec['match'] = 'any'
    spec['conditions'][1] = dict(field='arg', key='body', operator='equals', value='attack')
    lines = [line for line in wizard.render_rule(spec).splitlines() if line.startswith('SecRule')]
    assert 'id:10000,phase:1' in lines[0]
    assert 'id:10001,phase:2' in lines[1]


def test_chained_exclusion_executes_ctl_only_after_last_match():
    spec = compound_spec()
    spec.update(kind='exclusion', exclude_id=942100, exclude_parameter='body')
    lines = [line for line in wizard.render_rule(spec).splitlines() if line.startswith('SecRule')]
    assert 'phase:1,t:none,pass,nolog,chain' in lines[0] and 'ctl:' not in lines[0]
    assert lines[1].endswith('"t:none,ctl:ruleRemoveTargetById=942100;ARGS:body"')


@pytest.mark.parametrize('patch', [
    {'conditions': []}, {'conditions': 'invalid'}, {'match': 'xor'}, {'id': False},
    {'conditions': [dict(field='uri', key='', operator='regex', value='/')]},
    {'conditions': [dict(field='uri', key='', operator='equals', value='/')] * 11},
    {'match': 'any', 'id': 99999},
    {'kind': 'exclusion', 'exclude_id': 10001, 'match': 'any'},
    {'kind': 'exclusion', 'exclude_id': 942100, 'conditions': [dict(field='arg', key='x', operator='equals', value='y')]},
])
def test_invalid_compound_conditions_and_id_ranges_are_rejected(patch):
    with pytest.raises(wizard.WizardError):
        wizard.render_rule({**compound_spec(), **patch})


def test_automatic_id_allocation_finds_whole_block_and_handles_exhaustion():
    assert wizard.available_id({10000, 10002}, 2) == 10003
    assert wizard.available_id(set(range(10000, 100000)), 2) == 1
    assert wizard.available_id(set(range(1, 9999)) | set(range(10001, 100000)), 2) == 9999
    with pytest.raises(wizard.WizardError, match='ids_exhausted'):
        wizard.available_id(set(range(1, 100000)))


def test_auto_id_cannot_reach_rendering_or_saved_metadata_unresolved():
    spec = {**compound_spec(), 'id': None}
    assert wizard.validate_spec(spec, allow_auto=True)['id'] is None
    with pytest.raises(wizard.WizardError):
        wizard.render_rule(spec)
