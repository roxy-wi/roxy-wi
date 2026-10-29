"""Exercise the real offline scheduler; no daemon or running cluster is required."""
import shutil
from pathlib import Path
import pytest
from app.modules.service import ha_maintenance_remote as helper,ha_maintenance as maintenance
from app.modules.pacemaker.xml import summary
from app.modules.roxywi.exception import RoxywiValidationError

pytestmark=pytest.mark.skipif(not shutil.which('crm_simulate') or not shutil.which('crm_mon'),reason='Requires Pacemaker CLI tools')

CIB='''<cib crm_feature_set="3.16.2" validate-with="pacemaker-3.9" epoch="1" num_updates="0" admin_epoch="0" have-quorum="1" dc-uuid="1">
<configuration><crm_config><cluster_property_set id="props"><nvpair id="fence" name="stonith-enabled" value="false"/></cluster_property_set></crm_config>
<nodes><node id="1" uname="one"/><node id="2" uname="two"/></nodes>
<resources><primitive id="vip" class="ocf" provider="pacemaker" type="Dummy"/></resources><constraints>{constraints}</constraints></configuration>
<status><node_state id="1" uname="one" in_ccm="true" crmd="online" join="member" expected="member"/>
<node_state id="2" uname="two" in_ccm="true" crmd="online" join="member" expected="member"/></status></cib>'''


def test_real_scheduler_places_workload_on_survivor_without_changing_input():
    xml=CIB.format(constraints='')
    before=helper.fingerprint(xml,'one')
    predicted=summary(helper.simulate(xml,'one'))
    assert predicted['resources'][0]['nodes']==['two']
    assert next(n for n in predicted['nodes'] if n['name']=='one')['standby']=='true'
    assert before==helper.fingerprint(xml,'one')


def test_real_scheduler_cannot_approve_a_workload_with_no_remaining_eligible_node():
    xml=CIB.format(constraints='<rsc_location id="ban" rsc="vip" node="two" score="-INFINITY"/>')
    predicted=summary(helper.simulate(xml,'one'))
    before=dict(nodes=predicted['nodes'],resources=[dict(target_id='vip',active='true',resource_agent='ocf:pacemaker:Dummy')])
    with pytest.raises(RoxywiValidationError,match='surviving'):
        maintenance.check_placement(before,predicted,'one')
