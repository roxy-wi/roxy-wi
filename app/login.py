import uuid

import distro
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, make_response
from flask_login import login_user, login_required, logout_user, current_user

from app import app, login_manager, cache
import app.modules.db.sql as sql
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxy_wi_tools as roxy_wi_tools


@app.before_request
def check_login():
    if request.endpoint not in ('login_page', 'static', 'main.show_roxywi_version'):
        try:
            user_params = roxywi_common.get_users_params()
        except Exception:
            return redirect(url_for('login_page'))

        if user_params is None:
            make_response(redirect(url_for('login_page')))

        try:
            roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
        except Exception:
            make_response(redirect(url_for('login_page')))


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
        return redirect(url_for('login_page') + '?next=' + request.url)

    return response


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    next_url = request.args.get('next') or request.form.get('next')
    login = request.form.get('login')
    password = request.form.get('pass')
    role = 5
    user1 = ''

    if next_url is None:
        next_url = ''

    try:
        groups = sql.select_groups(id=user_groups)
        for g in groups:
            if g[0] == int(user_groups):
                user_group = g[1]
    except Exception:
        user_group = ''

    try:
        if distro.id() == 'ubuntu':
            if os.path.exists('/etc/apt/auth.conf.d/roxy-wi.conf'):
                cmd = "grep login /etc/apt/auth.conf.d/roxy-wi.conf |awk '{print $2}'"
                get_user_name, stderr = server_mod.subprocess_execute(cmd)
                user_name = get_user_name[0]
            else:
                user_name = 'git'
        else:
            if os.path.exists('/etc/yum.repos.d/roxy-wi.repo'):
                cmd = "grep base /etc/yum.repos.d/roxy-wi.repo |awk -F\":\" '{print $2}'|awk -F\"/\" '{print $3}'"
                get_user_name, stderr = server_mod.subprocess_execute(cmd)
                user_name = get_user_name[0]
            else:
                user_name = 'git'
        if sql.select_user_name():
            sql.update_user_name(user_name)
        else:
            sql.insert_user_name(user_name)
    except Exception as e:
        roxywi_common.logging('Cannot update subscription: ', str(e), roxywi=1)

    try:
        session_ttl = int(sql.get_setting('session_ttl'))
    except Exception:
        session_ttl = 5

    expires = datetime.utcnow() + timedelta(days=session_ttl)

    if login and password:
        users = sql.select_users(user=login)

        for user in users:
            if user.activeuser == 0:
                flash('Your login is disabled', 'alert alert-danger wrong-login')
            if user.ldap_user == 1:
                if login in user.username:
                    print(str(user.groups))
                    if roxywi_auth.check_in_ldap(login, password):
                        login_user(user)
                        resp = make_response(next_url or url_for('overview.index'))
                        resp.set_cookie('uuid', user_uuid, secure=True, expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT"))
                        resp.set_cookie('group', str(user.groups), secure=True, expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT"))
            else:
                passwordHashed = roxy_wi_tools.Tools.get_hash(password)
                if login in user.username and passwordHashed == user.password:
                    user_uuid = str(uuid.uuid4())
                    user_token = str(uuid.uuid4())
                    sql.write_user_uuid(login, user_uuid)
                    sql.write_user_token(login, user_token)
                    role = int(user.role)
                    user1 = user.username

                    login_user(user)
                    resp = make_response(next_url or url_for('overview.index'))
                    try:
                        resp.set_cookie('uuid', user_uuid, secure=True, expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT"))
                        resp.set_cookie('group', str(user.groups), secure=True, expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT"))
                    except Exception as e:
                        print(e)

                    try:
                        user_name = sql.get_user_name_by_uuid(user_uuid)
                        roxywi_common.logging('Roxy-WI server', f' user: {user_name}, group: {user_group} login', roxywi=1)
                    except Exception:
                        pass

                    return resp

                else:
                    flash('Login or password is not correct', 'alert alert-danger wrong-login')
        else:
            return 'ban', 200
    else:
        flash('Login or password is not correct', 'alert alert-danger wrong-login')

    try:
        lang = roxywi_common.get_user_lang_for_flask()
    except Exception:
        lang = 'en'

    return render_template('login.html', role=role, user=user1, lang=lang)


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
