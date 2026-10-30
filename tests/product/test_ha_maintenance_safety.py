"""Regression coverage for fresh drain health and persistent native startup holds."""
import io
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tests.product.test_ha_maintenance import (
    readiness_cluster, maintenance_cluster, keepalived_maintenance,
    ka_create, ka_step, approve,
)
from app.modules.db.db_model import HaCluster, HaMaintenancePlan
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiValidationError
from app.modules.service import ha_maintenance as maintenance, ha_readiness as audit


def reviewed(product_client, state, approver, app):
    row=ka_step(product_client,ka_create(product_client,state),'review')
    approve(app,row,approver)
    return row


def test_standby_stopping_after_approval_prevents_last_working_member_stop(
        product_client,keepalived_maintenance,maintenance_cluster,app):
    state=keepalived_maintenance
    row=reviewed(product_client,state,maintenance_cluster.reviewer,app)
    state.nodes[33]['active']=False
    row=ka_step(product_client,row,'drain',expected='failed')
    assert state.actions==[] and state.startup_actions==[]
    assert state.nodes[11]['active'] and state.nodes[11]['addresses']==['192.0.2.100']
    assert row.status=='review-failed' and not maintenance.unseal(row.payload).get('drained_at')


def test_health_is_refreshed_after_mask_before_stop(
        product_client,keepalived_maintenance,maintenance_cluster,app,monkeypatch):
    state=keepalived_maintenance
    row=reviewed(product_client,state,maintenance_cluster.reviewer,app)
    startup=maintenance.ka_startup
    def lose_standby(server,action,policy=None):
        result=startup(server,action,policy)
        if action=='hold':state.nodes[33]['active']=False
        return result
    monkeypatch.setattr(maintenance,'ka_startup',lose_standby)
    row=ka_step(product_client,row,'drain',expected='failed')
    assert state.actions==[] and state.nodes[11]['active']
    assert state.startup=='masked' and row.status=='unknown'


def test_single_member_cannot_be_drained(product,keepalived_maintenance):
    state=keepalived_maintenance
    cluster,nodes=audit.subject('keepalived',state.cluster.id,1)
    with pytest.raises(RoxywiValidationError,match='surviving'):
        maintenance.ka_view(cluster,[next((n,s) for n,s in nodes if s.server_id==11)],11)


@pytest.mark.parametrize('endpoint',[
    '192.0.2.100:443','[::ffff:192.0.2.100]:443','[::ffff:c000:264]:443',
])
@pytest.mark.parametrize('vip',['192.0.2.100','::ffff:192.0.2.100'])
def test_socket_probe_counts_native_and_mapped_ipv4(endpoint,vip,monkeypatch,capsys):
    monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps([vip])))
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(
        stdout=f'0 0 {endpoint} 198.51.100.12:50000\n0 0 192.0.2.101:443 198.51.100.12:50001\n'))
    exec(maintenance.SOCKETS,{})
    assert capsys.readouterr().out.strip()=='1'


def test_socket_probe_preserves_native_ipv6_matching(monkeypatch,capsys):
    monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps(['2001:db8::100'])))
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(
        stdout='0 0 [2001:db8::100]:443 [2001:db8::20]:50000\n'))
    exec(maintenance.SOCKETS,{})
    assert capsys.readouterr().out.strip()=='1'


@pytest.mark.parametrize('original',['enabled','disabled','static','indirect'])
def test_native_policy_is_journaled_before_mask_and_restored_only_after_return_approval(
        product_client,keepalived_maintenance,maintenance_cluster,app,monkeypatch,original):
    state=keepalived_maintenance;state.startup=original
    row=reviewed(product_client,state,maintenance_cluster.reviewer,app)
    startup=maintenance.ka_startup;action=maintenance.ka_action
    def journaled_startup(server,operation,policy=None):
        journal=maintenance.unseal(HaMaintenancePlan.get_by_id(row.id).payload).get('keepalived_startup')
        if operation=='hold':assert journal==dict(policy=original,phase='mask-requested')
        if operation=='restore':assert journal==dict(policy=original,phase='restore-requested')
        return startup(server,operation,policy)
    def held_action(server,binding,operation):
        journal=maintenance.unseal(HaMaintenancePlan.get_by_id(row.id).payload)['keepalived_startup']
        assert journal==dict(policy=original,phase='held' if operation=='stop' else 'restored')
        assert state.startup==('masked' if operation=='stop' else original)
        return action(server,binding,operation)
    monkeypatch.setattr(maintenance,'ka_startup',journaled_startup)
    monkeypatch.setattr(maintenance,'ka_action',held_action)
    row=ka_step(product_client,row,'drain')
    assert row.status=='ready' and state.startup=='masked'
    assert product_client.post(f'/ha/api/maintenance/{row.id}/resume',json={}).status_code==409
    assert state.startup=='masked'
    row=ka_step(product_client,row,'verify') if row.status=='unknown' else row
    row=ka_step(product_client,row,'review-return')
    assert maintenance.unseal(row.payload)['review']['view']['startup_policy']==original
    assert product_client.post(f'/ha/api/maintenance/{row.id}/resume',json={}).status_code==409
    approve(app,row,maintenance_cluster.reviewer)
    row=ka_step(product_client,row,'resume')
    assert row.status=='completed' and state.startup==original
    assert state.actions==[(11,'stop'),(11,'start')]


@pytest.mark.parametrize('applied',[False,True])
def test_interrupted_mask_keeps_original_policy_for_approved_recovery(
        product_client,keepalived_maintenance,maintenance_cluster,app,monkeypatch,applied):
    state=keepalived_maintenance
    row=reviewed(product_client,state,maintenance_cluster.reviewer,app)
    startup=maintenance.ka_startup
    def interrupted(server,operation,policy=None):
        if operation=='hold':
            if applied:startup(server,operation,policy)
            raise RuntimeError('SSH response was lost')
        return startup(server,operation,policy)
    monkeypatch.setattr(maintenance,'ka_startup',interrupted)
    row=ka_step(product_client,row,'drain',expected='failed')
    assert state.actions==[] and row.status=='unknown'
    assert maintenance.unseal(row.payload)['keepalived_startup']==dict(policy='enabled',phase='mask-requested')
    row=ka_step(product_client,row,'review-return');approve(app,row,maintenance_cluster.reviewer)
    row=ka_step(product_client,row,'resume')
    assert row.status=='completed' and state.startup=='enabled'
    assert state.actions==[(11,'start')]


def test_interrupted_policy_restore_is_idempotent_on_reapproved_return(
        product_client,keepalived_maintenance,maintenance_cluster,app,monkeypatch):
    state=keepalived_maintenance;state.startup='disabled'
    row=reviewed(product_client,state,maintenance_cluster.reviewer,app)
    row=ka_step(product_client,row,'drain')
    row=ka_step(product_client,row,'review-return');approve(app,row,maintenance_cluster.reviewer)
    startup=maintenance.ka_startup;fail=[True]
    def interrupted(server,operation,policy=None):
        result=startup(server,operation,policy)
        if operation=='restore' and fail:
            fail.pop()
            raise RuntimeError('SSH response was lost')
        return result
    monkeypatch.setattr(maintenance,'ka_startup',interrupted)
    row=ka_step(product_client,row,'resume',expected='failed')
    assert row.status=='unknown' and state.actions==[(11,'stop')]
    assert maintenance.unseal(row.payload)['keepalived_startup']==dict(policy='disabled',phase='restore-requested')
    row=ka_step(product_client,row,'review-return');approve(app,row,maintenance_cluster.reviewer)
    row=ka_step(product_client,row,'resume')
    assert row.status=='completed' and state.startup=='disabled'
    assert state.actions==[(11,'stop'),(11,'start')]


def test_preexisting_native_mask_is_not_claimed_or_removed(
        product_client,keepalived_maintenance,maintenance_cluster,app):
    state=keepalived_maintenance;state.startup='masked'
    row=reviewed(product_client,state,maintenance_cluster.reviewer,app)
    row=ka_step(product_client,row,'drain',expected='failed')
    assert state.actions==[] and state.startup=='masked'
    assert not maintenance.unseal(row.payload).get('keepalived_startup')
    assert all(action=='read' for _ident,action,_policy in state.startup_actions)


def test_lost_persistent_hold_prevents_verify_handover(
        product_client,keepalived_maintenance,maintenance_cluster,app):
    state=keepalived_maintenance
    row=reviewed(product_client,state,maintenance_cluster.reviewer,app)
    state.no_takeover=True
    row=ka_step(product_client,row,'drain',expected='failed')
    state.no_takeover=False;state.nodes[33]['addresses']=['192.0.2.100']
    state.startup='enabled'
    row=ka_step(product_client,row,'verify',expected='failed')
    assert row.status=='unknown' and not maintenance.unseal(row.payload).get('drained_at')
    assert state.actions==[(11,'stop')]


def test_unverified_mask_command_never_counts_as_a_hold(monkeypatch):
    commands=[]
    def run(args,**kwargs):commands.append(args);return 'enabled\n' if args[1]=='is-enabled' else ''
    monkeypatch.setattr(maintenance,'Remote',lambda server:SimpleNamespace(run=run))
    with pytest.raises(RoxywiValidationError,match='persistently masked'):maintenance.ka_startup(None,'hold')
    assert commands==[['systemctl','mask','keepalived'],['systemctl','is-enabled','keepalived']]


@pytest.mark.parametrize('policy',['enabled','disabled','static','indirect'])
def test_native_helper_uses_persistent_mask_and_verifies_policy(monkeypatch,policy):
    state=dict(policy=policy);commands=[]
    def run(args,**kwargs):
        commands.append(args)
        operation=args[1]
        if operation=='mask':state['policy']='masked'
        elif operation=='unmask':state['policy']=policy
        elif operation=='enable':state['policy']='enabled'
        elif operation=='disable':state['policy']='disabled'
        return state['policy']+'\n' if operation=='is-enabled' else ''
    monkeypatch.setattr(maintenance,'Remote',lambda server:SimpleNamespace(run=run))
    assert maintenance.ka_startup(None,'read')==policy
    assert maintenance.ka_startup(None,'hold')=='masked'
    assert maintenance.ka_startup(None,'hold')=='masked'
    assert maintenance.ka_startup(None,'restore',policy)==policy
    assert maintenance.ka_startup(None,'restore',policy)==policy
    assert ['systemctl','mask','keepalived'] in commands
    assert all('--runtime' not in args for args in commands)


@pytest.mark.parametrize('policy',['masked-runtime','enabled-runtime','linked','unknown',''])
def test_unverifiable_native_startup_policy_is_rejected(monkeypatch,policy):
    commands=[]
    def run(args,**kwargs):commands.append(args);return policy+'\n'
    monkeypatch.setattr(maintenance,'Remote',lambda server:SimpleNamespace(run=run))
    with pytest.raises(RoxywiValidationError,match='startup policy'):maintenance.ka_startup(None,'read')
    assert commands==[['systemctl','is-enabled','keepalived']]


def test_unverified_container_boot_hold_is_rejected_without_native_fallback(
        product,keepalived_maintenance,monkeypatch):
    from app.modules.db import service as service_sql
    from app.modules.service import container_settings
    monkeypatch.setattr(service_sql,'select_service_setting',lambda ident,service,key:'1' if ident==11 and key=='dockerized' else '0')
    monkeypatch.setattr(container_settings,'runtime',lambda *a:dict(engine='podman',owner='vrrp',unit='vrrp.service'))
    monkeypatch.setattr(container_settings,'name',lambda *a:'vrrp')
    cluster,nodes=audit.subject('keepalived',keepalived_maintenance.cluster.id,1)
    with pytest.raises(RoxywiValidationError,match='persistent startup hold'):maintenance.ka_view(cluster,nodes,11)
    assert keepalived_maintenance.startup_actions==[] and keepalived_maintenance.actions==[]


def test_container_return_retains_exact_runtime_owner_unit_and_name(monkeypatch):
    calls=[]
    def run(args,**kwargs):calls.append((args,kwargs));return ''
    monkeypatch.setattr(maintenance,'Remote',lambda server:SimpleNamespace(run=run))
    binding=dict(dockerized='1',runtime=dict(engine='podman',owner='vrrp',unit='vrrp.service'),name='reviewed-vrrp')
    maintenance.ka_action(None,binding,'start')
    assert len(calls)==1 and calls[0][0][:2]==['python3','-c']
    assert json.loads(calls[0][1]['data'])==dict(binding,action='start')
    assert 'module.lifecycle' in calls[0][0][2]


def test_duplicate_names_do_not_hide_maintenance_configuration_drift(product,keepalived_maintenance):
    state=keepalived_maintenance
    state.nodes[11]['name']=state.nodes[33]['name']='Same display name'
    cluster,nodes=audit.subject('keepalived',state.cluster.id,1)
    before=maintenance.ka_view(cluster,nodes,11)
    state.nodes[11]['digest']='c'*64
    assert maintenance.ka_view(cluster,nodes,11)['fingerprint']!=before['fingerprint']


def test_reused_cluster_registration_cannot_reuse_a_maintenance_plan(
        product_client,keepalived_maintenance):
    row=ka_create(product_client,keepalived_maintenance)
    HaCluster.update(readiness_key='f'*32).where(HaCluster.id==row.cluster_id).execute()
    with pytest.raises(RoxywiConflictError,match='previous registration'):maintenance.get(row.id,1)
