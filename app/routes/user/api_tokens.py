from flask import g, jsonify, render_template, request, abort
from functools import wraps
from flask_jwt_extended import jwt_required

from app.middleware import get_user_params
from app.modules.api_tokens import service
from app.modules.api_tokens.scopes import SCOPES
from app.modules.roxywi.exception import RoxywiPublicError, RoxywiPermissionError, RoxywiResourceNotFound
from app.routes.user import bp


def interactive_session(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if request.headers.get('Authorization'):
            abort(403, 'Use the interactive cookie session without an Authorization header')
        return fn(*args, **kwargs)
    return wrapped


def result(call, status=200):
    try:
        response = jsonify(call())
        response.status_code = status
    except RoxywiPublicError as error:
        response = jsonify(error=error.public_message)
        response.status_code = (503 if isinstance(error, service.CredentialWriteUnavailable) else
                                403 if isinstance(error, RoxywiPermissionError) else
                                404 if isinstance(error, RoxywiResourceNotFound) else 400)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.get('/api-access')
@jwt_required(locations=['cookies'])
@interactive_session
@get_user_params()
def api_access_page():
    response = render_template('personal_tokens.html', lang=g.user_params['lang'], scopes=SCOPES, security_available=service.security_provider() is not None)
    return response, {'Cache-Control': 'no-store'}


@bp.get('/personal-tokens')
@jwt_required(locations=['cookies'])
@interactive_session
@get_user_params()
def personal_tokens_list():
    return result(lambda: dict(tokens=service.list_tokens(g.user_params['user_id'])))


@bp.post('/personal-tokens')
@jwt_required(locations=['cookies'])
@interactive_session
@get_user_params()
def personal_token_create():
    return result(lambda: service.create(request.get_json(), g.user_params['user_id']), 201)


@bp.delete('/personal-tokens/<token_id>')
@jwt_required(locations=['cookies'])
@interactive_session
@get_user_params()
def personal_token_revoke(token_id):
    return result(lambda: service.revoke(token_id, g.user_params['user_id']))
