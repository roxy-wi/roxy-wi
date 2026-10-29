from http.client import HTTPException
from functools import wraps

from flask import g, jsonify, render_template, request, abort
from flask_jwt_extended import jwt_required

from app.middleware import get_user_params
from app.modules.integrations import connection_profiles as profiles
from app.modules.integrations.connection_transport import check_connection
from app.modules.roxywi import auth, logger
from app.modules.roxywi.exception import (
    RoxywiConflictError, RoxywiPermissionError, RoxywiResourceNotFound, RoxywiValidationError,
)
from app.routes.admin import bp


def interactive_session(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if request.headers.get('Authorization'):
            abort(403, 'Use the interactive cookie session without an Authorization header')
        return fn(*args, **kwargs)
    return wrapped


def _response(call, success_status=200):
    try:
        result = jsonify(call())
        result.status_code = success_status
    except RoxywiResourceNotFound:
        result = jsonify(error='Connection profile not found')
        result.status_code = 404
    except RoxywiPermissionError:
        result = jsonify(error='Not permitted to manage this connection profile')
        result.status_code = 403
    except RoxywiConflictError as error:
        result = jsonify(error=error.public_message)
        result.status_code = 409
    except RoxywiValidationError as error:
        result = jsonify(error=error.public_message)
        result.status_code = 400
    result.headers['Cache-Control'] = 'no-store'
    return result


@bp.get('/connections')
@jwt_required(locations=['cookies'])
@interactive_session
@get_user_params()
def connections_page():
    auth.page_for_admin(level=2)
    return render_template('connection_profiles.html', lang=g.user_params['lang'])


@bp.get('/connection-profiles')
@jwt_required(locations=['cookies'])
@interactive_session
@get_user_params()
def connection_profiles_list():
    auth.page_for_admin(level=3)
    return _response(lambda: {'profiles': profiles.list_profiles(g.user_params['group_id'])})


@bp.post('/connection-profiles')
@jwt_required(locations=['cookies'])
@interactive_session
@get_user_params()
def connection_profile_create():
    auth.page_for_admin(level=2)
    return _response(lambda: profiles.save(
        request.get_json(), group_id=g.user_params['group_id'], role=g.user_params['role'],
        actor_id=g.user_params['user_id'],
    ), 201)


@bp.put('/connection-profiles/<int:profile_id>')
@jwt_required(locations=['cookies'])
@interactive_session
@get_user_params()
def connection_profile_update(profile_id):
    auth.page_for_admin(level=2)
    return _response(lambda: profiles.save(
        request.get_json(), profile_id=profile_id, group_id=g.user_params['group_id'],
        role=g.user_params['role'], actor_id=g.user_params['user_id'],
    ))


@bp.delete('/connection-profiles/<int:profile_id>')
@jwt_required(locations=['cookies'])
@interactive_session
@get_user_params()
def connection_profile_delete(profile_id):
    auth.page_for_admin(level=2)

    def remove():
        data = request.get_json()
        revision = data.get('revision') if isinstance(data, dict) else None
        if type(revision) is not int or revision < 1:
            raise RoxywiValidationError('The current revision is required')
        profiles.delete(profile_id, group_id=g.user_params['group_id'], role=g.user_params['role'],
                        actor_id=g.user_params['user_id'], revision=revision)
        return {'status': 'deleted'}
    return _response(remove)


@bp.post('/connection-profiles/<int:profile_id>/test')
@jwt_required(locations=['cookies'])
@interactive_session
@get_user_params()
def connection_profile_test(profile_id):
    auth.page_for_admin(level=2)

    def test():
        connection = profiles.resolve(profile_id, g.user_params['group_id'])
        try:
            result = check_connection(connection)
        except (OSError, ValueError, KeyError, TimeoutError, HTTPException):
            result = {'status': 'failed', 'detail': 'Connection check failed; verify destination, TLS and credentials'}
        logger.info('Connection profile checked', user_id=g.user_params['user_id'],
                    profile_id=profile_id, revision=connection.revision, result=result['status'])
        return result
    return _response(test)
