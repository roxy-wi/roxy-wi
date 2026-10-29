"""External certificate source UI/API reusing certificate permissions and jobs."""
from functools import wraps

from flask import abort, g, jsonify, render_template, request
from pydantic import ValidationError

from app.middleware import get_user_params
from app.modules.connectors.certificates import PROVIDERS
from app.modules.db.db_model import CertificateSource, PacemakerCluster, Server
from app.modules.roxywi.exception import RoxywiResourceNotFound, RoxywiConflictError, RoxywiPublicError
from app.modules.service import certificate_sources as sources
from app.modules.service.certificates import CertificateError
from app.views.service.certificate_views import failure


def operator(handler):
    @wraps(handler)
    @get_user_params()
    def decorated(*args, **kwargs):
        if int(g.user_params['role']) > 3 or '1' not in g.user_params['user_services'].split():
            abort(403)
        try:
            return handler(*args, **kwargs)
        except RoxywiResourceNotFound as error:
            return jsonify(error=error.public_message), 404
        except RoxywiConflictError as error:
            return jsonify(error=error.public_message), 409
        except ValidationError:
            return jsonify(error='Invalid source fields; check HTTPS URL, credentials, domains and targets'), 400
        except CertificateError as error:
            return failure(error)
        except RoxywiPublicError as error:
            return jsonify(error=error.public_message), 400
        except Exception:
            return failure(RuntimeError('Certificate source operation failed'))
    return decorated


@operator
def page():
    return render_template('certificate_sources.html', lang=g.user_params['lang'])


def available_binding(row, group, user, *, write=False):
    try:
        sources.targets(sources.configuration(row), group, user, write=write)
    except RoxywiResourceNotFound:
        # The source belongs to this group even after its target registration
        # disappears. Reading/removing its binding never contacts a host.
        return False
    return True


def representation(row, group, user):
    available = available_binding(row, group, user)
    return dict(sources.public(row), binding_status='ready' if available else 'unavailable',
        binding_error=None if available else 'Target registration is unavailable; select a replacement or remove this source')


@operator
def collection():
    group, user = int(g.user_params['group_id']), int(g.user_params['user_id'])
    if request.method == 'POST':
        row = sources.save(sources.SourceRequest.model_validate(request.get_json()), group, user)
        return jsonify(data=sources.public(row)), 201
    result = []
    for row in CertificateSource.select().where(CertificateSource.group_id == group):
        result.append(representation(row, group, user))
    return jsonify(data=result)


@operator
def choices():
    group = int(g.user_params['group_id'])
    servers = Server.select().where((Server.group_id == str(group)) & Server.enabled & (Server.type_ip == 0))
    clusters = (PacemakerCluster.select().where(PacemakerCluster.group_id == group)
                if '5' in g.user_params['user_services'].split() else [])
    return jsonify(providers=[{'id': name, 'name': cls.label, 'schema': cls.settings_model.model_json_schema(),
                               'secret_fields': cls.secret_fields} for name, cls in PROVIDERS.items()],
                   servers=[{'id': s.server_id, 'name': s.hostname} for s in servers],
                   clusters=[{'id': c.id, 'name': c.name} for c in clusters])


@operator
def item(source_id):
    group, user = int(g.user_params['group_id']), int(g.user_params['user_id'])
    row = sources.get(source_id, group)
    available_binding(row, group, user, write=request.method != 'GET')
    if request.method == 'PUT':
        row = sources.save(sources.SourceRequest.model_validate(request.get_json()), group, user, source_id)
    elif request.method == 'DELETE':
        with sources.transaction():
            row = sources.locked(CertificateSource, CertificateSource.id == row.id)
            available_binding(row, group, user, write=True)
            sources.editable(row)
            row.delete_instance()
        return jsonify(status='deleted')
    return jsonify(data=representation(row, group, user))


@operator
def action(source_id, action):
    group, user = int(g.user_params['group_id']), int(g.user_params['user_id'])
    row = sources.get(source_id, group)
    task = sources.enqueue(row, user, check=action == 'check', recover=action == 'recover')
    return jsonify(task_id=task.id, status=task.status), 202
