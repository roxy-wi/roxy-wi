from flask import render_template, request, redirect, make_response, abort, g
from flask_jwt_extended import get_jwt, unset_jwt_cookies, jwt_required

from app import app
import app.modules.db.user as user_sql
import app.modules.db.token as token_sql
import app.modules.db.oidc as oidc_sql
from app.modules.change.access import is_change_center_available
from app.modules.oidc.access import is_oidc_available
import app.modules.roxywi.roxy as roxy
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
from app.modules.common.common import checkAjaxInput
from app.modules.roxywi import logger
from app.modules.roxywi.exception import RoxywiResourceNotFound


@app.context_processor
def inject_feature_availability():
    user_params = getattr(g, 'user_params', None)
    if not user_params or not user_params.get('user'):
        return {'oidc_available': False, 'change_center_available': False}

    subscription = roxywi_common.return_user_subscription()

    oidc_available = getattr(g, 'oidc_available', None)
    if oidc_available is None:
        oidc_available = is_oidc_available(subscription)
        g.oidc_available = oidc_available

    change_center_available = is_change_center_available(subscription)
    return {
        'oidc_available': oidc_available,
        'change_center_available': change_center_available,
    }


@app.before_request
def check_login():
    allowed_endpoints = (
        'login_page', 'api.do_login', 'oidc.public_providers', 'oidc.oidc_login', 'oidc.oidc_callback',
        'static', 'main.get_version', 'service.check_service', 'smon.show_smon_status_page',
        'smon.smon_history_statuses', 'smon.agent_get_checks', 'smon.get_check_status', 'favicon',
        'health.live', 'health.ready',
    )
    if request.endpoint not in allowed_endpoints:
        try:
            claims = roxywi_common.get_jwt_token_claims()
        except Exception as e:
            logger.warning('Authentication token rejected', reason=str(e))
            abort(401)

        try:
            user = user_sql.get_user_id(claims['user_id'])
        except RoxywiResourceNotFound:
            logger.warning('Authentication user does not exist', user_id=claims['user_id'])
            abort(401)

        if not user.enabled:
            logger.warning('Authentication user is disabled', user_id=claims['user_id'])
            abort(401)

        if int(claims['group']) != int(user.group_id):
            logger.warning(
                'Authentication active group mismatch',
                user_id=claims['user_id'],
                token_group=claims['group'],
                active_group=user.group_id,
            )
            abort(401)

        roxywi_auth.update_user_activity(claims['user_id'])


@app.after_request
def redirect_to_login(response):
    return response


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'GET':
        lang = roxywi_common.get_user_lang_for_flask()
        oidc_providers = oidc_sql.list_providers(enabled_only=True) if is_oidc_available() else []

        return render_template('login.html', lang=lang, oidc_providers=oidc_providers)
    elif request.method == 'POST':
        next_url = request.json.get('next')
        login = checkAjaxInput(request.json.get('login'))
        password = request.json.get('pass')
        try:
            roxy.update_plan()
        except Exception:
            pass
        try:
            user_params = roxywi_auth.check_user_password(login, password)
        except Exception as e:
            print(str(e))
            return roxywi_common.handle_json_exceptions(e, 'Cannot check login password'), 401
        try:
            response = roxywi_auth.do_login(user_params, next_url)
            logger.info(f'{login} login')
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Cannot do login'), 401

        return response
    return redirect('/', 302)


@app.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    token = get_jwt()
    token_sql.revoke_token(token['jti'], token['exp'])
    resp = make_response(redirect('/', 302))
    unset_jwt_cookies(resp)
    return resp
