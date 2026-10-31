from functools import wraps
from flask import abort,g,jsonify,redirect,render_template,request,url_for
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from app.middleware import get_user_params
from app.modules.db.db_model import Server, OperationalAssessment
from app.modules.db import service as service_sql,user as user_sql
from app.modules.roxywi.exception import RoxywiResourceNotFound,RoxywiPermissionError,RoxywiConflictError,RoxywiValidationError
from app.modules.service import proxy_assessments as assessments, service_map, served_tls
from app.modules.roxywi import logger
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
        except (ValidationError,ValueError):return jsonify(error='Invalid fields; review the selected proxy, discovered targets and form values'),400
        except Exception as error:
            logger.error('Proxy inspection API failed', error_type=type(error).__name__)
            return jsonify(error='Proxy inspection failed; refresh configuration discovery and permissions'), 502
    return wrapped


@bp.get('/diagnostics')
@api
def diagnostics_page():
    """Keep existing links working while diagnostics live on service cards."""
    services = available_services()
    if not services:
        raise RoxywiPermissionError('Proxy inspection permission denied')
    service = request.args.get('service') or services[0]
    if service not in services:
        raise RoxywiPermissionError('Proxy inspection permission denied')
    server_id = request.args.get('server_id', type=int)
    if server_id:
        assessments.authorize(server_id, service, g.user_params['group_id'], g.user_params['user_id'])
    return redirect(url_for('service.services', service=service, diagnostics=server_id))


def available_services() -> list[str]:
    """Return proxy services available to the current user."""
    allowed = set(user_sql.select_user_services(g.user_params['user_id']).split())
    return [name for name in ('haproxy', 'nginx', 'apache')
            if str(service_sql.select_service_id_by_slug(name)) in allowed]


@bp.get('/services')
def service_map_page():
    return render_template('published_services.html',lang=g.user_params['lang'])


@bp.get('/tls')
def tls_page():
    return render_template('served_tls.html',lang=g.user_params['lang'])


@bp.get('/api/tls')
@api
def tls_collection():
    from app.modules.db.db_model import ServedTlsMonitor,CertificateSource
    rows=[]
    for row in ServedTlsMonitor.select().where(ServedTlsMonitor.group_id==g.user_params['group_id']).limit(257):
        try:rows.append(served_tls.public(row,g.user_params['user_id']))
        except (RoxywiResourceNotFound,RoxywiPermissionError):continue
    if len(rows)>256:raise ValueError('Too many TLS monitors in this group')
    return jsonify(data=rows,sources=[dict(id=s.id,name=s.name,status=s.status) for s in CertificateSource.select().where(
        CertificateSource.group_id==g.user_params['group_id']).limit(256)])


@bp.post('/api/tls')
@bp.put('/api/tls/<int:monitor_id>')
@api
def tls_save(monitor_id=None):
    body=served_tls.MonitorRequest.model_validate(request.get_json())
    row=served_tls.save(body,g.user_params['group_id'],g.user_params['user_id'],monitor_id)
    return jsonify(data=served_tls.public(row,g.user_params['user_id'])),201 if monitor_id is None else 200


@bp.delete('/api/tls/<int:monitor_id>')
@api
def tls_delete(monitor_id):
    row=served_tls.get(monitor_id,g.user_params['group_id']);served_tls.authorize(row,g.user_params['user_id'])
    if served_tls.active(row):raise RoxywiConflictError('Wait for the active TLS assessment')
    row.delete_instance();return jsonify(status='deleted')


@bp.post('/api/tls/<int:monitor_id>/run')
@api
def tls_run(monitor_id):
    row=served_tls.enqueue(served_tls.get(monitor_id,g.user_params['group_id']),g.user_params['user_id'])
    return jsonify(id=row.id,task_id=row.task_id,status='created'),202


@bp.get('/api/tls/<int:monitor_id>/history')
@api
def tls_history(monitor_id):
    row=served_tls.get(monitor_id,g.user_params['group_id']);served_tls.authorize(row,g.user_params['user_id'])
    history=OperationalAssessment.select().where((OperationalAssessment.group_id==row.group_id)&
        (OperationalAssessment.kind=='served-tls')&(OperationalAssessment.subject==str(row.id))).order_by(OperationalAssessment.id.desc()).limit(20)
    return jsonify(data=[assessments.public(item) for item in history])


@bp.get('/api/services')
@api
def service_map_view():
    return jsonify(service_map.view(g.user_params['group_id'],g.user_params['user_id'],request.args.get('impact_node',type=int)))


@bp.post('/api/services/discover')
@api
def service_map_discover():
    body=assessments.ProxyRequest.model_validate(request.get_json())
    row=assessments.enqueue(body,g.user_params['group_id'],g.user_params['user_id'],kind='service-map')
    return jsonify(id=row.id,task_id=row.task_id,status='created'),202


@bp.post('/api/services/confirm')
@api
def service_map_confirm():
    body=service_map.Confirmation.model_validate(request.get_json())
    row=service_map.confirm(body,g.user_params['group_id'],g.user_params['user_id'])
    return jsonify(id=row.id),201


@bp.delete('/api/services/confirm/<int:confirmation_id>')
@api
def service_map_retract(confirmation_id):
    from app.modules.db.db_model import PublishedServiceConfirmation
    row=PublishedServiceConfirmation.get_or_none((PublishedServiceConfirmation.id==confirmation_id)&
        (PublishedServiceConfirmation.group_id==g.user_params['group_id']))
    if row is None:raise RoxywiResourceNotFound()
    snapshot=assessments.get(row.assessment_id,g.user_params['group_id'],g.user_params['user_id'])
    service,ident=snapshot.subject.split(':')
    assessments.authorize(int(ident),service,g.user_params['group_id'],g.user_params['user_id'],probe=True)
    row.delete_instance()
    return jsonify(status='retracted')


@bp.get('/api/choices')
@api
def choices():
    services = available_services()
    rows=Server.select().where((Server.group_id==str(g.user_params['group_id']))&(Server.enabled==1)&(Server.type_ip==0))
    rows=list(rows)
    return jsonify(services=services,nodes=[dict(id=row.server_id,name=row.hostname,ip=row.ip) for row in rows],servers=[dict(id=row.server_id,name=row.hostname,ip=row.ip,
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
    rows=assessments.history(service,server_id,g.user_params['group_id'],g.user_params['user_id'])
    return jsonify(data=[assessments.public(row) for row in rows])


@bp.get('/api/assessments/<int:assessment_id>')
@api
def assessment(assessment_id):
    return jsonify(data=assessments.public(assessments.get(assessment_id,g.user_params['group_id'],g.user_params['user_id'])))
