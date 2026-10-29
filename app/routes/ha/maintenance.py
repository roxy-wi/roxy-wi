from flask import g,jsonify,render_template,request
from app.modules.db.db_model import HaMaintenancePlan
from app.modules.service import ha_maintenance as maintenance
from app.modules.subscription.access import CHANGE_CENTER,require_feature
from app.routes.ha.readiness import access
from app.routes.ha import bp


@bp.get('/maintenance')
@access
def maintenance_page():
    return render_template('ha_maintenance.html',lang=g.user_params['lang'])


@bp.get('/api/maintenance')
@access
def maintenance_list():
    require_feature(CHANGE_CENTER)
    rows=HaMaintenancePlan.select().where(HaMaintenancePlan.group_id==g.user_params['group_id']).order_by(HaMaintenancePlan.id.desc()).limit(100)
    return jsonify(data=[maintenance.public(row) for row in rows])


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
