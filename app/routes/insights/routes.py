from functools import wraps
from flask import abort,g,jsonify,render_template,request
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.middleware import get_user_params
from app.modules.db.db_model import Server,OperationalAssessment
from app.modules.db import service as service_sql,user as user_sql
from app.modules.roxywi.exception import RoxywiResourceNotFound,RoxywiPermissionError,RoxywiConflictError,RoxywiValidationError
from app.modules.service import proxy_assessments as assessments
from app.routes.insights import bp


@bp.before_request
@jwt_required()
@get_user_params()
def before_request():
    if not {'1','2','4'}&set(g.user_params['user_services'].split()):abort(403)
    if request.method!='GET' and int(g.user_params['role'])>3:abort(403)


def api(handler):
    @wraps(handler)
    def wrapped(*args,**kwargs):
        try:return handler(*args,**kwargs)
        except RoxywiResourceNotFound:return jsonify(error='Proxy assessment or server not found'),404
        except RoxywiPermissionError:return jsonify(error='Proxy inspection permission denied'),403
        except RoxywiConflictError as error:return jsonify(error=error.public_message),409
        except RoxywiValidationError as error:return jsonify(error=error.public_message),400
        except (ValidationError,ValueError):return jsonify(error='Invalid fields; select a registered proxy and an HTTP(S) URL without credentials'),400
        except Exception:return jsonify(error='Proxy inspection failed; refresh configuration discovery and permissions'),502
    return wrapped


@bp.get('/diagnostics')
def diagnostics_page():
    return render_template('proxy_diagnostics.html',lang=g.user_params['lang'])


@bp.get('/api/choices')
@api
def choices():
    allowed=set(user_sql.select_user_services(g.user_params['user_id']).split())
    services=[name for name in ('haproxy','nginx','apache') if str(service_sql.select_service_id_by_slug(name)) in allowed]
    rows=Server.select().where((Server.group_id==str(g.user_params['group_id']))&(Server.enabled==1)&(Server.type_ip==0))
    return jsonify(services=services,servers=[dict(id=row.server_id,name=row.hostname,ip=row.ip,
        services=[name for name in services if getattr(row,name)]) for row in rows if any(getattr(row,name) for name in services)])


@bp.post('/api/diagnostics')
@api
def diagnose():
    body=assessments.DiagnosticRequest.model_validate(request.get_json())
    row=assessments.enqueue(body,g.user_params['group_id'],g.user_params['user_id'])
    return jsonify(id=row.id,task_id=row.task_id,status='created'),202


@bp.get('/api/diagnostics')
@api
def diagnostics_history():
    service=request.args.get('service','');server_id=request.args.get('server_id',type=int)
    if not server_id:raise ValueError('Select a server')
    assessments.authorize(server_id,service,g.user_params['group_id'],g.user_params['user_id'])
    rows=OperationalAssessment.select().where((OperationalAssessment.group_id==g.user_params['group_id'])&
        (OperationalAssessment.kind=='proxy-diagnostics')&(OperationalAssessment.subject==f'{service}:{server_id}')).order_by(OperationalAssessment.id.desc()).limit(20)
    return jsonify(data=[assessments.public(row) for row in rows])


@bp.get('/api/assessments/<int:assessment_id>')
@api
def assessment(assessment_id):
    return jsonify(data=assessments.public(assessments.get(assessment_id,g.user_params['group_id'],g.user_params['user_id'])))
