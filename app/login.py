from flask import render_template, request, redirect, url_for, make_response
from flask_login import login_required, logout_user, current_user, login_url

from app import app, login_manager, cache
import app.modules.db.sql as sql
import app.modules.roxywi.common as roxywi_common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.roxy as roxy
import app.modules.roxy_wi_tools as roxy_wi_tools


@app.before_request
def check_login():
    if request.endpoint not in (
            'login_page', 'static', 'main.show_roxywi_version', 'service.check_service', 'smon.show_smon_status_page',
            'smon.smon_history_statuses'
    ):
        try:
            user_params = roxywi_common.get_users_params()
        except Exception:
            return redirect(login_url('login_page', next_url=request.url))

        if not sql.is_user_active(user_params['user_id']):
            return redirect(login_url('login_page', next_url=request.url))

        try:
            roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
        except Exception:
            return redirect(login_url('login_page', next_url=request.url))


@login_manager.user_loader
def load_user(user_id):
    user = f'user_{user_id}'
    user_obj = cache.get(user)

    if user_obj is None:
        query = sql.get_user_id(user_id)
        cache.set(user, query, timeout=360)
        return query

    return user_obj


@app.after_request
def redirect_to_login(response):
    if response.status_code == 401:
        return redirect(login_url('login_page', next_url=request.url))

    return response


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    try:
        roxy.update_plan()
    except Exception:
        pass
    next_url = request.args.get('next') or request.form.get('next')
    login = request.form.get('login')
    password = request.form.get('pass')
    role = 5
    user1 = ''

    if login and password:
        users = sql.select_users(user=login)

        for user in users:
            if user.activeuser == 0:
                return 'Your login is disabled', 200
            if user.ldap_user == 1:
                if login in user.username:
                    if roxywi_auth.check_in_ldap(login, password):
                        role = int(user.role)
                        user1 = user.username
                        user_uuid, user_token = roxywi_auth.create_uuid_and_token(login)
                        return roxywi_auth.do_login(user_uuid, str(user.groups), user, next_url)

            else:
                hashed_password = roxy_wi_tools.Tools.get_hash(password)
                if login in user.username and hashed_password == user.password:
                    role = int(user.role)
                    user1 = user.username
                    user_uuid, user_token = roxywi_auth.create_uuid_and_token(login)
                    return roxywi_auth.do_login(user_uuid, str(user.groups), user, next_url)
                else:
                    return 'ban', 200
        else:
            return 'ban', 200

    try:
        lang = roxywi_common.get_user_lang_for_flask()
    except Exception:
        lang = 'en'

    return render_template('login.html', user_params='', role=role, user=user1, lang=lang)


@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    user = f'user_{current_user.id}'
    cache.delete(user)
    logout_user()
    resp = make_response(redirect(url_for('login_page')))
    resp.delete_cookie('uuid')
    resp.delete_cookie('group')

    return resp
