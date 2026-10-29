from functools import wraps
from flask import abort, g, jsonify, render_template, request
from pydantic import ValidationError
from app.middleware import get_user_params
from app.modules.roxywi import auth
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiResourceNotFound
from app.modules.db.db_model import HaCluster, PacemakerCluster, OperationalAssessment
from app.modules.service import ha_readiness as audit
from app.routes.ha import bp


def access(handler):
    @wraps(handler)
    @get_user_params()
    def wrapped(*args, **kwargs):
        if not auth.is_access_permit_to_service('cluster'):
            abort(403)
        if request.method != 'GET' and int(g.user_params['role']) > (2 if request.path.endswith(('/profile','/attest')) else 3):
            abort(403)
        try:
            return handler(*args, **kwargs)
        except RoxywiResourceNotFound:
            return jsonify(error='HA assessment or cluster not found'),404
        except RoxywiConflictError as error:
            return jsonify(error=error.public_message),409
        except (ValidationError,ValueError):
            return jsonify(error='Invalid assessment fields; refresh the cluster and review the form'),400
    return wrapped


@bp.get('/readiness')
@access
def readiness():
    return render_template('ha_readiness.html',lang=g.user_params['lang'])


@bp.get('/api/readiness')
@access
def subjects():
    group=g.user_params['group_id']
    return jsonify(data=[dict(provider=provider,id=row.id,name=row.name) for provider,model in
        [('keepalived',HaCluster),('pacemaker',PacemakerCluster)] for row in model.select().where(model.group_id==group)])


@bp.get('/api/readiness/<provider>/<int:cluster_id>')
@access
def overview(provider,cluster_id):
    group=g.user_params['group_id']; info=audit.public_profile(provider,cluster_id,group)
    cluster, _nodes=audit.subject(provider,cluster_id,group)
    rows=OperationalAssessment.select().where((OperationalAssessment.group_id==group) &
        (OperationalAssessment.kind=='ha-readiness') & (OperationalAssessment.subject==audit.subject_key(provider,cluster))).order_by(OperationalAssessment.id.desc()).limit(20)
    return jsonify(profile=info,assessments=[audit.get_report(row.id,group) for row in rows])


@bp.post('/api/readiness/<provider>/<int:cluster_id>/run')
@access
def run(provider,cluster_id):
    row=audit.enqueue(provider,cluster_id,g.user_params['group_id'],g.user_params['user_id'])
    return jsonify(id=row.id,task_id=row.task_id,status='created'),202


@bp.post('/api/readiness/<provider>/<int:cluster_id>/profile')
@access
def save_profile(provider,cluster_id):
    return jsonify(profile=audit.save_profile(provider,cluster_id,g.user_params['group_id'],
        audit.ProfileRequest.model_validate(request.get_json())))


@bp.post('/api/readiness/<provider>/<int:cluster_id>/attest')
@access
def attest(provider,cluster_id):
    return jsonify(profile=audit.attest(provider,cluster_id,g.user_params['group_id'],g.user_params['user_id'],
        audit.Attestation.model_validate(request.get_json())))
