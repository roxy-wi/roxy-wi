import os
import sys
import uuid

import pytz
import distro
from flask import render_template, request, redirect, url_for, flash, make_response
from flask_login import login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta

from app import login_manager, cache
from app.routes.main import bp

sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app'))

import modules.db.sql as sql
from modules.db.db_model import *
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxy_wi_tools as roxy_wi_tools
import modules.roxywi.roxy as roxy
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.nettools as nettools
import modules.roxywi.common as roxywi_common
import modules.service.common as service_common
import modules.service.haproxy as service_haproxy


@bp.before_request
@cache.memoize(50)
def check_login():
    user_params = roxywi_common.get_users_params()
    if user_params is None:
        make_response(redirect(url_for('login_page')))

    try:
        roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
    except Exception:
        make_response(redirect(url_for('login_page')))


@bp.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@bp.errorhandler(500)
def page_not_found(e):
    return render_template('500.html', e=e), 500


@login_manager.user_loader
def load_user(user_id):
    user = f'user_{user_id}'
    user_obj = cache.get(user)

    if user_obj is None:
        query = User.get(User.user_id == user_id)
        cache.set(user, query, timeout=360)
        return query

    return user_obj


@bp.after_request
def redirect_to_login(response):
    if response.status_code == 401:
        return redirect(url_for('login_page') + '?next=' + request.url)

    return response


@bp.route('/login', methods=['GET', 'POST'])
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
                    if check_in_ldap(login, password):
                        login_user(user)
                        resp = make_response(next_url or url_for('index'))
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
                    resp = make_response(next_url or url_for('index'))
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


@bp.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    user = f'user_{current_user.id}'
    cache.delete(user)
    logout_user()
    resp = make_response(redirect(url_for('index')))
    resp.delete_cookie('uuid')
    resp.delete_cookie('group')

    return resp


@bp.route('/stats/<service>/', defaults={'serv': None})
@bp.route('/stats/<service>/<serv>')
@login_required
def stats(service, serv):
    try:
        user_params = roxywi_common.get_users_params(virt=1, haproxy=1)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    try:
        if serv is None:
            first_serv = user_params['servers']
            for i in first_serv:
                serv = i[2]
                break
    except Exception:
        pass

    if service in ('haproxy', 'nginx', 'apache'):
        service_desc = sql.select_service(service)
        is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id)

        if is_redirect != 'ok':
            return redirect(url_for(f'{is_redirect}'))

        servers = roxywi_common.get_dick_permit(service=service_desc.slug)
    else:
        return redirect(url_for('index'))

    return render_template(
        'statsview.html', h2=1, autorefresh=1, role=user_params['role'], user=user, selects=servers, serv=serv,
        service=service, user_services=user_params['user_services'], token=user_params['token'],
        select_id="serv", lang=user_params['lang'], service_desc=service_desc
    )


@bp.route('/stats/view/<service>/<server_ip>')
@login_required
def show_stats(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    if service in ('nginx', 'apache'):
        return service_common.get_stat_page(server_ip, service)
    else:
        return service_haproxy.stat_page_action(server_ip)


@bp.route('/nettools')
@login_required
def nettools():
    try:
        user_params = roxywi_common.get_users_params(virt=1)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    return render_template(
        'nettools.html', autorefresh=0, role=user_params['role'], user=user, servers=user_params['servers'],
        user_services=user_params['user_services'], token=user_params['token'], lang=user_params['lang']
    )


@bp.post('/nettols/<check>')
@login_required
def nettols_check(check):
    server_from = common.checkAjaxInput(request.form.get('server_from'))
    server_to = common.is_ip_or_dns(request.form.get('server_to'))
    action = common.checkAjaxInput(request.form.get('nettools_action'))
    port_to = common.checkAjaxInput(request.form.get('nettools_telnet_port_to'))
    dns_name = common.checkAjaxInput(request.form.get('nettools_nslookup_name'))
    dns_name = common.is_ip_or_dns(dns_name)
    record_type = common.checkAjaxInput(request.form.get('nettools_nslookup_record_type'))

    if check == 'icmp':
        return nettools.ping_from_server(server_from, server_to, action)
    elif check == 'tcp':
        return nettools.telnet_from_server(server_from, server_to, port_to)
    elif check == 'dns':
        return nettools.nslookup_from_server(server_from, dns_name, record_type)
    else:
        return 'error: Wrong check'


@bp.route('/history/<service>/<server_ip>')
@login_required
def service_history(service, server_ip):
    users = sql.select_users()
    server_ip = common.checkAjaxInput(server_ip)
    user_subscription = roxywi_common.return_user_subscription()

    try:
        user_params = roxywi_common.get_users_params()
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    if service in ('haproxy', 'nginx', 'keepalived', 'apache'):
        service_desc = sql.select_service(service)
        if roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id):
            server_id = sql.select_server_id_by_ip(server_ip)
            history = sql.select_action_history_by_server_id_and_service(server_id, service_desc.service)
    elif service == 'server':
        if roxywi_common.check_is_server_in_group(server_ip):
            server_id = sql.select_server_id_by_ip(server_ip)
            history = sql.select_action_history_by_server_id(server_id)
    elif service == 'user':
        history = sql.select_action_history_by_user_id(server_ip)

    try:
        sql.delete_action_history_for_period()
    except Exception as e:
        print(e)

    return render_template(
        'history.html', h2=1, role=user_params['role'], user=user, users=users, serv=server_ip, service=service,
        history=history, user_services=user_params['user_services'], token=user_params['token'],
        user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'], lang=user_params['lang']
    )


@bp.route('/servers')
@login_required
def servers():
    roxywi_auth.page_for_admin(level=2)

    try:
        user_params = roxywi_common.get_users_params()
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    ldap_enable = sql.get_setting('ldap_enable')
    user_group = roxywi_common.get_user_group(id=1)
    settings = sql.get_setting('', all=1)
    services = sql.select_services()
    gits = sql.select_gits()
    servers = roxywi_common.get_dick_permit(virt=1, disable=0, only_group=1)
    masters = sql.select_servers(get_master_servers=1, uuid=user_params['user_uuid'])
    is_needed_tool = common.is_tool('ansible')
    user_roles = sql.select_user_roles_by_group(user_group)
    backups = sql.select_backups()
    s3_backups = sql.select_s3_backups()
    user_subscription = roxywi_common.return_user_subscription()

    if user_params['lang'] == 'ru':
        title = 'Сервера: '
    else:
        title = "Servers: "

    return render_template(
        'servers.html',
        h2=1, title=title, role=user_params['role'], user=user, users=sql.select_users(group=user_group),
        groups=sql.select_groups(), servers=servers, roles=sql.select_roles(), sshs=sql.select_ssh(group=user_group),
        masters=masters, group=user_group, services=services, timezones=pytz.all_timezones, guide_me=1,
        token=user_params['token'], settings=settings, backups=backups, s3_backups=s3_backups, page="servers.py",
         user_services=user_params['user_services'], ldap_enable=ldap_enable,
        user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'], gits=gits,
        is_needed_tool=is_needed_tool, lang=user_params['lang'], user_roles=user_roles
    )


@bp.route('/internal/show_version')
@cache.cached()
def show_roxywi_version():
    return render_template('ajax/check_version.html', versions=roxy.versions())
