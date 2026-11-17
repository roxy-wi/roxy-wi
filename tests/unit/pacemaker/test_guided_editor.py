import shutil
import shlex
import subprocess
import xml.etree.ElementTree as ET

import pytest
from pydantic import ValidationError

from app.modules.pacemaker import guided
from app.modules.pacemaker.xml import parse,digest,configuration
from app.modules.roxywi.exception import RoxywiInputError,RoxywiConflictError

CIB='''<cib crm_feature_set="3.16.2" validate-with="pacemaker-3.7" admin_epoch="0" epoch="1" num_updates="0">
<configuration><crm_config><cluster_property_set id="bootstrap"><nvpair id="no-fencing" name="stonith-enabled" value="false"/></cluster_property_set></crm_config>
<nodes><node id="1" uname="one"/><node id="2" uname="two"/></nodes><resources>
<primitive id="vip" class="ocf" provider="pacemaker" type="Dummy"><operations><op id="vip-start" name="start" interval="0" timeout="60s"/></operations></primitive>
<primitive id="proxy" class="ocf" provider="pacemaker" type="Dummy"/>
<primitive id="fence-a" class="stonith" type="fence_dummy"/>
<primitive id="fence-b" class="stonith" type="fence_dummy"/>
</resources><constraints/></configuration><status/></cib>'''
NODES=['one','two']


def build(kind,data,xml=CIB):return guided.build(xml,guided.Request(base_digest=digest(xml),kind=kind,data=data),NODES).xml


def test_topology_fallback_order_device_conjunction_and_other_targets_are_preserved():
    first=build('topology',dict(node='two',levels=[dict(index=1,devices=['fence-b'])]))
    result=build('topology',dict(node='one',levels=[dict(index=2,devices=['fence-b']),dict(index=1,devices=['fence-a','fence-b'])]),first)
    levels=configuration(result).findall('./fencing-topology/fencing-level')
    assert [(row.get('target'),row.get('index'),row.get('devices')) for row in levels]==[('two','1','fence-b'),('one','1','fence-a,fence-b'),('one','2','fence-b')]
    item=next(row for row in levels if row.get('target')=='two')
    assert item.get('id')==configuration(first).find('./fencing-topology/fencing-level').get('id')
    cleared=build('topology',dict(node='one',levels=[]),result)
    assert [value.get('target') for value in configuration(cleared).findall('./fencing-topology/fencing-level')]==['two']


@pytest.mark.parametrize('data',[
 dict(node='foreign',levels=[]),dict(node='one',levels=[dict(index=0,devices=['fence-a'])]),
 dict(node='one',levels=[dict(index=1,devices=['proxy'])]),dict(node='one',levels=[dict(index=1,devices=['fence-a','fence-a'])]),
 dict(node='one',levels=[dict(index=1,devices=['fence-a']),dict(index=1,devices=['fence-b'])])])
def test_invalid_topology_never_produces_a_candidate(data):
    with pytest.raises((ValidationError,RoxywiInputError)):build('topology',data)


def test_attribute_and_date_rules_escape_values_and_roundtrip_stable_ids():
    body=dict(id='site-rule',resource='proxy',score='-INFINITY',boolean_op='or',conditions=[
        dict(attribute='site',operation='eq',value='east<&"',type='string'),
        dict(kind='date',start='2026-10-29T10:00:00+01:00',end='2026-10-29T11:00:00+01:00')])
    first=build('location-rule',body);assert 'east&lt;&amp;&quot;' in first
    values=guided.catalog(first,NODES)['rules'];assert values==[body | {'conditions':[dict(kind='attribute',**body['conditions'][0]),body['conditions'][1]]}]
    second=build('location-rule',body,first)
    assert digest(first)==digest(second)


@pytest.mark.parametrize('start,end', [('2026-10-29T10:00','2026-10-29T11:00'),('2026-10-29T11:00Z','2026-10-29T10:00Z')])
def test_time_windows_require_explicit_offsets_and_increasing_times(start,end):
    with pytest.raises(ValidationError):build('location-rule',dict(id='r',resource='vip',conditions=[dict(kind='date',start=start,end=end)]))


def test_nested_rule_is_visible_only_in_lossless_cib_editor():
    xml=CIB.replace('<constraints/>','<constraints><rsc_location id="nested" rsc="vip"><rule id="outer" score="100"><rule id="inner"><expression id="e" attribute="site" operation="defined"/></rule></rule></rsc_location></constraints>')
    assert guided.catalog(xml,NODES)['rules']==[]
    with pytest.raises(RoxywiInputError,match='CIB editor'):build('location-rule',dict(id='nested',resource='vip',conditions=[dict(attribute='site',operation='defined')]),xml)


def test_collections_reorder_and_keep_unselected_resources_without_changing_parameters():
    xml=build('collection',dict(id='web',kind='group',members=['vip','proxy']))
    assert [item.get('id') for item in configuration(xml).findall('./resources/group/primitive')]==['vip','proxy']
    changed=build('collection',dict(id='web',kind='group',members=['proxy']),xml)
    assert configuration(changed).find('./resources/primitive[@id="vip"]/operations/op').get('id')=='vip-start'
    wrapped=build('collection',dict(id='web-clone',kind='promotable',members=['web'],meta={'clone-max':'2','promoted-max':'1'}),changed)
    clone=configuration(wrapped).find('./resources/clone')
    assert clone.find('group').get('id')=='web'
    assert clone.find('./meta_attributes/nvpair[@name="promotable"]').get('value')=='true'
    with pytest.raises(RoxywiInputError,match='standalone'):build('collection',dict(id='other',kind='group',members=['proxy']),wrapped)


def test_meta_updates_preserve_unknown_keys_and_explicit_empty_values_remove_owned_keys():
    xml=CIB.replace('<primitive id="proxy" class="ocf" provider="pacemaker" type="Dummy"/>','<primitive id="proxy" class="ocf" provider="pacemaker" type="Dummy"><meta_attributes id="m"><nvpair id="custom" name="custom-value" value="kept"/><nvpair id="stick" name="resource-stickiness" value="100"/></meta_attributes></primitive>')
    result=build('meta',dict(resource='proxy',values={'resource-stickiness':'','target-role':'Stopped'}),xml)
    meta=configuration(result).find('./resources/primitive[@id="proxy"]/meta_attributes')
    assert [(value.get('name'),value.get('value')) for value in meta]==[('custom-value','kept'),('target-role','Stopped')]


def test_operations_update_in_place_keep_unknown_fields_and_reject_semantic_duplicates():
    xml=build('operation',dict(resource='vip',id='vip-start',name='start',interval='0s',timeout='90s'))
    assert configuration(xml).find('./resources/primitive[@id="vip"]/operations/op').get('id')=='vip-start'
    xml=build('operation',dict(resource='vip',name='monitor',interval='30s',timeout='20s',role='Promoted'),xml)
    with pytest.raises(RoxywiInputError,match='already exist'):build('operation',dict(resource='vip',name='monitor',interval='30000ms',timeout='20s',role='Promoted'),xml)
    with pytest.raises(RoxywiInputError,match='zero interval'):build('operation',dict(resource='vip',name='stop',interval='30s',timeout='20s'))
    removed=build('operation',dict(resource='vip',id='vip-start',name='start',interval='0s',remove=True),xml)
    assert configuration(removed).find('./resources/primitive[@id="vip"]/operations/op[@id="vip-start"]') is None


def test_existing_unitless_operation_times_roundtrip_as_seconds():
    xml = CIB.replace('name="start" interval="0" timeout="60s"',
                      'name="monitor" interval="30" timeout="60"')
    operation = guided.catalog(xml, NODES)['operations'][0]
    assert operation['interval'] == '30s'
    assert operation['timeout'] == '60s'
    saved = configuration(build('operation', operation, xml)).find('.//op')
    assert saved.get('interval') == '30s' and saved.get('timeout') == '60s'


@pytest.mark.parametrize('interval,duplicate', [('30s', True), ('30000ms', True), ('30ms', False)])
def test_unitless_operation_intervals_use_seconds_for_duplicate_detection(interval, duplicate):
    xml = CIB.replace('name="start" interval="0"', 'name="monitor" interval="30"')
    data = dict(resource='vip', name='monitor', interval=interval, timeout='60s')
    if duplicate:
        with pytest.raises(RoxywiInputError, match='already exist'):
            build('operation', data, xml)
    else:
        assert len(configuration(build('operation', data, xml)).findall('.//op')) == 2


@pytest.mark.parametrize('metadata', [
    '<meta_attributes id="op-meta"><nvpair id="op-disabled" name="enabled" value="false"/>'
    '<nvpair id="op-timeout" name="timeout" value="300s"/></meta_attributes>',
    '<meta_attributes id="op-meta"><rule id="op-rule" score="INFINITY">'
    '<expression id="op-expr" attribute="site" operation="eq" value="east"/></rule>'
    '<nvpair id="op-timeout" name="timeout" value="300s"/></meta_attributes>',
    '<meta_attributes id-ref="op-defaults"/>',
])
def test_operation_metadata_requires_cib_editor_and_survives_unrelated_edits(metadata):
    xml = CIB.replace('name="start" interval="0" timeout="60s"/>',
                      'name="monitor" interval="30s">' + metadata + '</op>')
    catalog = guided.catalog(xml, NODES)
    assert catalog['operations'] == []
    assert dict(kind='operation', id='vip-start') in catalog['unsupported']
    with pytest.raises(RoxywiInputError, match='CIB editor'):
        build('operation', dict(resource='vip', id='vip-start', name='monitor', interval='30s'), xml)
    changed = build('meta', dict(resource='proxy', values={'priority': '10'}), xml)
    assert ET.tostring(configuration(changed).find('.//op')) == ET.tostring(configuration(xml).find('.//op'))


def test_operation_roundtrip_preserves_inherited_timeout_and_enabled_defaults():
    xml = CIB.replace(' timeout="60s"', '').replace('<constraints/>',
        '<op_defaults><meta_attributes id="op-defaults">'
        '<nvpair id="default-timeout" name="timeout" value="300s"/>'
        '<nvpair id="default-enabled" name="enabled" value="false"/>'
        '</meta_attributes></op_defaults><constraints/>')
    operation = guided.catalog(xml, NODES)['operations'][0]
    assert operation['timeout'] == '' and operation['enabled'] is None
    result = configuration(build('operation', operation, xml))
    saved = result.find('.//op')
    assert 'timeout' not in saved.attrib and 'enabled' not in saved.attrib
    assert ET.tostring(result.find('op_defaults')) == ET.tostring(configuration(xml).find('op_defaults'))


def test_bundle_roundtrip_preserves_primitive_and_uses_distinct_global_ids():
    body=dict(id='app',engine='podman',image='example.test/app@sha256:'+'a'*64,replicas=2,replicas_per_host=1,promoted_max=1,resource='proxy',control_port=3122,
        ports=[dict(port=443,internal_port=8443)],volumes=[dict(source='/srv/app',target='/app',source_root=False,options='ro,Z')])
    xml=build('bundle',body);config=configuration(xml);bundle=config.find('./resources/bundle')
    assert bundle.find('primitive').get('id')=='proxy' and bundle.find('podman').get('image')==body['image']
    item=guided.catalog(xml,NODES)['bundles'][0]
    rebuilt=build('bundle',item,xml)
    assert configuration(rebuilt).find('./resources/bundle/primitive').get('id')=='proxy'
    ids=[value.get('id') for value in configuration(rebuilt).iter() if value.get('id')]
    assert len(ids)==len(set(ids))
    assert configuration(rebuilt).find('./resources/primitive[@id="vip"]') is not None


@pytest.mark.parametrize('engine', ['docker', 'podman'])
@pytest.mark.parametrize('options', [None, 'rw', 'ro,Z'])
def test_existing_bundle_storage_options_survive_unrelated_image_edit(engine, options):
    attribute = '' if options is None else f' options="{options}"'
    xml = CIB.replace('<resources>', f'<resources><bundle id="app"><{engine} image="example/app:1"/>'
        '<storage><storage-mapping id="data" source-dir="/srv/app" target-dir="/app"'
        f'{attribute}/></storage></bundle>')
    data = guided.catalog(xml, NODES)['bundles'][0]
    data['image'] = 'example/app:2'
    saved = configuration(build('bundle', data, xml)).find('.//storage-mapping')
    assert saved.get('options') == options


def test_new_storage_mapping_keeps_explicit_read_only_default():
    xml = build('bundle', dict(id='app', image='example/app:1',
        volumes=[dict(source='/srv/app', target='/app')]))
    assert configuration(xml).find('.//storage-mapping').get('options') == 'ro'


@pytest.mark.parametrize('change',[
 {'replicas':1,'promoted_max':2},{'network':'host','replicas_per_host':2,'replicas':2},
 {'resource':'proxy'},{'ports':[{'port':3122}],'resource':'proxy','control_port':3122},
 {'volumes':[dict(source='/srv/../secret',target='/app')]},{'ip_range_start':'255.255.255.255','replicas':2},
 {'image':'image\n--privileged'}])
def test_invalid_bundles_are_refused(change):
    with pytest.raises((ValidationError,RoxywiInputError)):build('bundle',dict(id='bundle',image='example/app:1')|change)


def test_bundle_custom_options_are_never_silently_removed():
    xml=CIB.replace('<constraints/>','<constraints/>').replace('<resources>','<resources><bundle id="custom"><podman image="app:1" options="--custom"/></bundle>')
    assert guided.catalog(xml,NODES)['bundles']==[]
    with pytest.raises(RoxywiInputError,match='CIB editor'):build('bundle',dict(id='custom',image='other:2'),xml)


def test_stale_digest_and_global_id_collisions_are_rejected():
    body=guided.Request(base_digest='0'*64,kind='meta',data=dict(resource='vip',values={}))
    with pytest.raises(RoxywiConflictError):guided.build(CIB,body,NODES)
    with pytest.raises(RoxywiInputError):build('collection',dict(id='vip',kind='group',members=['proxy']))
    with pytest.raises(RoxywiInputError):build('operation',dict(resource='proxy',id='vip-start',name='start',interval='0s'))


@pytest.mark.skipif(not shutil.which('crm_verify'),reason='Pacemaker CLI required')
@pytest.mark.parametrize('kind,data',[
 ('topology',dict(node='one',levels=[dict(index=1,devices=['fence-a','fence-b']),dict(index=2,devices=['fence-b'])])),
 ('location-rule',dict(id='prefer',resource='proxy',conditions=[dict(attribute='#uname',value='one')])),
 ('location-rule',dict(id='hours',resource='proxy',conditions=[dict(kind='date',start='2026-10-29T10:00Z',end='2026-10-29T11:00Z')])),
 ('collection',dict(id='group',kind='group',members=['vip','proxy'])),
 ('operation',dict(resource='proxy',name='monitor',interval='10s',timeout='5s')),
 ('bundle',dict(id='bundle',engine='podman',image='example/app:1',network='host',ports=[dict(port=443,internal_port=8443)])),
 ('meta',dict(resource='vip',values={'resource-stickiness':'100'}))])
def test_generated_candidates_pass_real_pacemaker_schema_validation(tmp_path,kind,data):
    xml=build(kind,data)
    # Keep non-topology fixtures independent of optional fencing agent packages.
    root=parse(xml);config=root.find('configuration')
    for item in list(config.find('resources')):
        if kind!='topology' and item.get('class')=='stonith':config.find('resources').remove(item)
    file=tmp_path/'candidate.xml';file.write_text(ET.tostring(root,encoding='unicode'))
    result=subprocess.run(['crm_verify','--xml-file',str(file)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr


def native_graph(xml, directory):
    directory.mkdir()
    root = parse(xml)
    root.set('have-quorum', '1')
    resources = root.find('./configuration/resources')
    for resource in list(resources):
        if resource.get('class') == 'stonith':
            resources.remove(resource)
    source = directory / 'cib.xml'
    source.write_text(ET.tostring(root, encoding='unicode'))
    verified = subprocess.run(['crm_verify', '--xml-file', str(source)], capture_output=True, text=True, timeout=20)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    graph = directory / 'graph.xml'
    result = subprocess.run(['crm_simulate', '--xml-file', str(source), '--simulate',
        '--node-up', 'one', '--node-up', 'two', '--save-graph', str(graph)],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    return ET.parse(graph).getroot()


native_scheduler = pytest.mark.skipif(
    not shutil.which('crm_verify') or not shutil.which('crm_simulate'), reason='Pacemaker CLI required')


@native_scheduler
@pytest.mark.parametrize('inherited', [False, True])
def test_native_scheduler_retains_unitless_monitor_timing_after_roundtrip(tmp_path, inherited):
    xml = CIB.replace('name="start" interval="0" timeout="60s"',
        'name="monitor" interval="30"' + ('' if inherited else ' timeout="60"'))
    if inherited:
        xml = xml.replace('<constraints/>', '<op_defaults><meta_attributes id="op-defaults">'
            '<nvpair id="slow-default" name="timeout" value="300s"/></meta_attributes></op_defaults><constraints/>')
    data = guided.catalog(xml, NODES)['operations'][0]
    updated = build('operation', data, xml)
    for name, source in [('before', xml), ('after', updated)]:
        graph = native_graph(source, tmp_path / name)
        actions = graph.findall('.//action_set/rsc_op[@operation_key="vip_monitor_30000"]/attributes')
        assert len(actions) == 1
        assert actions[0].get('CRM_meta_interval') == '30000'
        assert actions[0].get('CRM_meta_timeout') == ('300000' if inherited else '60000')


@native_scheduler
def test_native_scheduler_preserves_operation_metadata_during_unrelated_edit(tmp_path):
    xml = CIB.replace('name="start" interval="0" timeout="60s"/>',
        'name="monitor" interval="30"><meta_attributes id="monitor-meta">'
        '<nvpair id="monitor-disabled" name="enabled" value="false"/>'
        '<nvpair id="monitor-slow" name="timeout" value="300s"/></meta_attributes></op>')
    assert guided.catalog(xml, NODES)['operations'] == []
    updated = build('meta', dict(resource='proxy', values={'priority': '10'}), xml)
    settings = []
    for name, source in [('before', xml), ('after', updated)]:
        graph = native_graph(source, tmp_path / name)
        settings.append(sorted((action.get('operation_key'), attributes.get('CRM_meta_interval'),
            attributes.get('CRM_meta_timeout'), attributes.get('CRM_meta_enabled'))
            for action in graph.findall('.//action_set/rsc_op')
            if action.find('primitive[@id="vip"]') is not None
            for attributes in action.findall('attributes')))
    assert settings[0] == settings[1]


@native_scheduler
def test_native_scheduler_retains_bundle_default_mount_options(tmp_path):
    xml = CIB.replace('<resources>', '<resources><bundle id="app"><docker image="example/app:1"/>'
        '<storage><storage-mapping id="data" source-dir="/srv/app" target-dir="/app"/></storage></bundle>')
    data = guided.catalog(xml, NODES)['bundles'][0]
    data['image'] = 'example/app:2'
    updated = build('bundle', data, xml)
    for name, source in [('before', xml), ('after', updated)]:
        graph = native_graph(source, tmp_path / name)
        commands = [shlex.split(item.get('run_opts')) for item in graph.iter('attributes') if item.get('run_opts')]
        assert commands
        assert all(command[command.index('-v') + 1] == '/srv/app:/app' for command in commands)


def test_existing_boolean_aliases_and_templates_are_not_misrepresented():
    xml=build('collection',dict(id='cloned',kind='promotable',members=['proxy']))
    xml=xml.replace('name="promotable" value="true"','name="promotable" value="TRUE"')
    assert guided.catalog(xml,NODES)['collections'][0]['kind']=='promotable'
    xml=xml.replace('id="vip-start" name="start"','id="vip-start" enabled="no" name="start"')
    assert guided.catalog(xml,NODES)['operations'][0]['enabled'] is False
    xml=CIB.replace('<resources>','<resources><template id="profile" class="ocf" provider="pacemaker" type="Dummy"/>').replace('id="proxy" class="ocf" provider="pacemaker" type="Dummy"','id="proxy" template="profile"')
    assert next(value for value in guided.catalog(xml,NODES)['resources'] if value['id']=='proxy')['agent']=='ocf:pacemaker:Dummy'
