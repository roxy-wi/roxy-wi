from flask import g, jsonify, redirect, request, url_for
from app.modules.db.db_model import ConfigChange, HaCluster, HaMaintenancePlan, PacemakerCluster
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.roxywi.exception import RoxywiResourceNotFound
from app.modules.roxywi.exception import RoxywiPermissionError
from app.modules.service.ha_access import allowed_providers
from app.modules.service import ha_maintenance as maintenance
from app.modules.subscription.access import CHANGE_CENTER, require_feature
from app.routes.ha.readiness import access
from app.routes.ha import bp


@bp.get('/maintenance')
@access
def maintenance_page():
    change_id = request.args.get('change', type=int)
    if change_id:
        row = HaMaintenancePlan.get_or_none((HaMaintenancePlan.change_id == change_id)
                                            & (HaMaintenancePlan.group_id == g.user_params['group_id']))
        if row is None:
            raise RoxywiResourceNotFound('Maintenance plan not found')
        if row.provider not in allowed_providers(g.user_params['user_services']):
            raise RoxywiPermissionError('No access to this cluster service')
        maintenance.get(row.id, g.user_params['group_id'])
        return redirect(url_for('ha.cluster_index', provider=row.provider, cluster=row.cluster_id,
                                panel='maintenance', change=change_id))
    return redirect(url_for('ha.cluster_index', panel='maintenance', provider=request.args.get('provider'),
                            cluster=request.args.get('cluster', type=int)))


@bp.get('/api/maintenance')
@access
def maintenance_list():
    require_feature(CHANGE_CENTER)
    query = maintenance.ListQuery.model_validate(request.args.to_dict())
    providers = allowed_providers(g.user_params['user_services'])
    rows, next_before, registration = maintenance.plans(g.user_params['group_id'], query, providers=providers)
    approvers = {provider: maintenance.approvers(g.user_params['group_id'], provider) for provider in providers}
    return jsonify(data=[maintenance.public(row, available_approvers=approvers[row.provider]) for row in rows],
                   next_before=next_before, registration_key=registration)


@bp.get('/api/maintenance/active')
@access
def maintenance_active():
    require_feature(CHANGE_CENTER)
    providers = allowed_providers(g.user_params['user_services'])
    registrations = {(provider, row.id): row.readiness_key for provider, model in
                     [('keepalived', HaCluster), ('pacemaker', PacemakerCluster)]
                     if provider in providers
                     for row in model.select().where(model.group_id == g.user_params['group_id'])}
    rows = HaMaintenancePlan.select().join(ConfigChange, on=(HaMaintenancePlan.change_id == ConfigChange.id)).where(
        (HaMaintenancePlan.group_id == g.user_params['group_id']) & (ConfigChange.group_id == g.user_params['group_id'])
        & (HaMaintenancePlan.status != 'completed') & (ConfigChange.status != 'cancelled')
    ).order_by(HaMaintenancePlan.id.desc())
    approvers = {provider: maintenance.approvers(g.user_params['group_id'], provider) for provider in providers}
    result = []
    for row in rows:
        key = (row.provider, row.cluster_id)
        if key not in registrations or registrations[key] != deserialize_operation_payload(row.payload).get('registration_key'):
            continue
        value = maintenance.public(row, available_approvers=approvers[row.provider])
        result.append({key: value[key] for key in ('id', 'change_id', 'provider', 'cluster_id', 'node_name',
                                                  'status', 'change_status', 'operation')})
    return jsonify(data=result)


@bp.post('/api/maintenance')
@access
def maintenance_create():
    row=maintenance.create(maintenance.Create.model_validate(request.get_json()),g.user_params['group_id'],g.user_params['user_id'])
    return jsonify(data=maintenance.public(row)),201


@bp.post('/api/maintenance/<int:plan_id>/<action>')
@access
def maintenance_action(plan_id,action):
    row=maintenance.get(plan_id,g.user_params['group_id'])
    task=maintenance.enqueue(row,g.user_params['user_id'],action)
    return jsonify(task_id=task.id,status=task.status),202
