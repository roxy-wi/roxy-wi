import shutil
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


def test_existing_boolean_aliases_and_templates_are_not_misrepresented():
    xml=build('collection',dict(id='cloned',kind='promotable',members=['proxy']))
    xml=xml.replace('name="promotable" value="true"','name="promotable" value="TRUE"')
    assert guided.catalog(xml,NODES)['collections'][0]['kind']=='promotable'
    xml=xml.replace('id="vip-start" name="start"','id="vip-start" enabled="no" name="start"')
    assert guided.catalog(xml,NODES)['operations'][0]['enabled'] is False
    xml=CIB.replace('<resources>','<resources><template id="profile" class="ocf" provider="pacemaker" type="Dummy"/>').replace('id="proxy" class="ocf" provider="pacemaker" type="Dummy"','id="proxy" template="profile"')
    assert next(value for value in guided.catalog(xml,NODES)['resources'] if value['id']=='proxy')['agent']=='ocf:pacemaker:Dummy'
