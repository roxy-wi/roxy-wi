import os
import sys
import uuid

import pytz
import distro
from flask import render_template, request, redirect, url_for, flash, make_response
from flask_login import login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta

from app import app, login_manager, cache

sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app'))

import modules.db.sql as sql
from modules.db.db_model import *
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxy_wi_tools as roxy_wi_tools
import modules.roxywi.logs as roxy_logs
import modules.roxywi.roxy as roxywi
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

get_config = roxy_wi_tools.GetConfigVar()
time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)


@app.before_request
@cache.memoize(50)
def check_login():
	user_params = roxywi_common.get_users_params()
	if user_params is None:
		make_response(redirect(url_for('login_page')))

	try:
		roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
	except Exception:
		make_response(redirect(url_for('login_page')))


@app.errorhandler(404)
def page_not_found(e):
	return render_template('404.html'), 404


@app.errorhandler(500)
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


@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
	user = f'user_{current_user.id}'
	cache.delete(user)
	logout_user()
	resp = make_response(redirect(url_for('index')))
	resp.delete_cookie('uuid')
	resp.delete_cookie('group')

	return resp


@app.route('/')
@app.route('/overview')
@login_required
def index():
	try:
		user_params = roxywi_common.get_users_params()
		user = user_params['user']
	except Exception:
		return redirect(url_for('login_page'))

	groups = sql.select_groups()
	return render_template(
		'ovw.html', h2=1, autorefresh=1, role=user_params['role'], user=user, groups=groups,
		roles=sql.select_roles(), servers=user_params['servers'], user_services=user_params['user_services'],
		roxy_wi_log=roxy_logs.roxy_wi_log(), token=user_params['token'], guide_me=1, lang=user_params['lang']
	)


@app.route('/stats/<service>/', defaults={'serv': None})
@app.route('/stats/<service>/<serv>')
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


@app.route('/logs/internal')
@login_required
def logs_internal():
	log_type = request.args.get('type')

	if log_type == '2':
		roxywi_auth.page_for_admin(level=2)
	else:
		roxywi_auth.page_for_admin()

	try:
		user_params = roxywi_common.get_users_params(virt=1, haproxy=1)
		user = user_params['user']
	except Exception:
		return redirect(url_for('login_page'))

	time_storage = sql.get_setting('log_time_storage')
	log_path = get_config.get_config_var('main', 'log_path')
	selects = roxywi_common.get_files(log_path, file_format="log")

	try:
		time_storage_hours = time_storage * 24
		for dirpath, dirnames, filenames in os.walk(log_path):
			for file in filenames:
				curpath = os.path.join(dirpath, file)
				file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
				if datetime.datetime.now() - file_modified > datetime.timedelta(hours=time_storage_hours):
					os.remove(curpath)
	except Exception:
		pass

	if log_type is None:
		selects.append(['fail2ban.log', 'fail2ban.log'])
		selects.append(['roxy-wi.error.log', 'error.log'])
		selects.append(['roxy-wi.access.log', 'access.log'])

	return render_template(
		'logs_internal.html',
		h2=1, autorefresh=1, role=user_params['role'], user=user, user_services=user_params['user_services'],
		token=user_params['token'], lang=user_params['lang'], selects=selects, serv='viewlogs'
	)


@app.route('/logs/<service>', defaults={'waf': None})
@app.route('/logs/<service>/<waf>')
@login_required
def logs(service, waf):
	serv = request.args.get('serv')
	rows = request.args.get('rows')
	grep = request.args.get('grep')
	exgrep = request.args.get('exgrep')
	hour = request.args.get('hour')
	minute = request.args.get('minute')
	hour1 = request.args.get('hour1')
	minute1 = request.args.get('minute1')
	log_file = request.args.get('file')

	if rows is None: rows=10
	if grep is None: grep=''

	try:
		user_params = roxywi_common.get_users_params(virt=1, haproxy=1)
		user = user_params['user']
	except Exception:
		return redirect(url_for('login_page'))

	if service in ('haproxy', 'nginx', 'keepalived', 'apache') and not waf:
		service_desc = sql.select_service(service)
		service_name = service_desc.service
		is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id)

		if is_redirect != 'ok':
			return redirect(url_for(f'{is_redirect}'))

		servers = roxywi_common.get_dick_permit(service=service_desc.slug)
	elif waf:
		service_name = 'WAF'
		is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1)

		if is_redirect != 'ok':
			return redirect(url_for(f'{is_redirect}'))

		servers = roxywi_common.get_dick_permit(haproxy=1)
	else:
		return redirect(url_for('index'))

	return render_template(
		'logs.html',
		h2=1, autorefresh=1, role=user_params['role'], user=user, select_id='serv', rows=rows, remote_file=log_file,
		selects=servers, waf=waf, service=service, user_services=user_params['user_services'],
		token=user_params['token'], lang=user_params['lang'], service_name=service_name, grep=grep, serv=serv
	)
	

@app.route('/portscanner')
@login_required
def portscanner():
	try:
		user_params = roxywi_common.get_users_params(virt=1)
		user = user_params['user']
	except Exception:
		return redirect(url_for('login_page'))

	user_group = roxywi_common.get_user_group(id=1)
	port_scanner_settings = sql.select_port_scanner_settings(user_group)

	if not port_scanner_settings:
		port_scanner_settings = ''
		count_ports = ''
	else:
		count_ports = list()
		for s in user_params['servers']:
			count_ports_from_sql = sql.select_count_opened_ports(s[2])
			i = (s[2], count_ports_from_sql)
			count_ports.append(i)

	cmd = "systemctl is-active roxy-wi-portscanner"
	port_scanner, port_scanner_stderr = server_mod.subprocess_execute(cmd)
	user_subscription = roxywi_common.return_user_subscription()

	return render_template(
		'portscanner.html', h2=1, autorefresh=0, role=user_params['role'], user=user, servers=user_params['servers'],
		port_scanner_settings=port_scanner_settings, count_ports=count_ports, port_scanner=''.join(port_scanner),
		port_scanner_stderr=port_scanner_stderr, user_services=user_params['user_services'], user_status=user_subscription['user_status'],
		user_plan=user_subscription['user_plan'], token=user_params['token'], lang=user_params['lang']
	)


@app.route('/nettools')
@login_required
@cache.cached()
def nettools():
	try:
		user_params = roxywi_common.get_users_params(virt=1)
		user = user_params['user']
	except Exception:
		return redirect(url_for('login_page'))

	return render_template(
		'nettools.html', h2=1, autorefresh=0, role=user_params['role'], user=user_params['user'], servers=user_params['servers'],
		user_services=user_params['user_services'], token=user_params['token'], lang=user_params['lang']
	)


@app.route('/history/<service>/<server_ip>')
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


@app.route('/servers')
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
