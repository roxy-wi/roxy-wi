from functools import wraps
from flask import abort, g, jsonify, redirect, request, url_for
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.middleware import get_user_params
from app.modules.roxywi import auth
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiResourceNotFound, RoxywiPermissionError, RoxywiValidationError
from app.modules.db.db_model import HaCluster, PacemakerCluster, OperationalAssessment
from app.modules.service import ha_readiness as audit
from app.routes.ha import bp


class HistoryQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    before: int | None = Field(default=None, gt=0)


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
        except RoxywiPermissionError as error:
            return jsonify(error=error.public_message),403
        except RoxywiValidationError as error:
            return jsonify(error=error.public_message),400
        except (ValidationError,ValueError):
            return jsonify(error='Invalid assessment fields; refresh the cluster and review the form'),400
    return wrapped


@bp.get('/readiness')
@access
def readiness():
    return redirect(url_for('ha.cluster_index', panel='readiness', provider=request.args.get('provider'),
                            cluster=request.args.get('cluster', type=int)))


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
    query = HistoryQuery.model_validate(request.args.to_dict())
    rows = OperationalAssessment.select().where((OperationalAssessment.group_id == group) &
        (OperationalAssessment.kind == 'ha-readiness') & (OperationalAssessment.subject == audit.subject_key(provider, cluster)))
    if query.before:
        rows = rows.where(OperationalAssessment.id < query.before)
    page = list(rows.order_by(OperationalAssessment.id.desc()).limit(21))
    return jsonify(profile=info, assessments=[audit.get_report(row.id, group) for row in page[:20]],
                   next_before=page[19].id if len(page) > 20 else None)


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
