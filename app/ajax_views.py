import os
import sys

from flask import render_template, request
from flask_login import login_required

from app import app, login_manager, cache

sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app'))

import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.service.action as service_action
import modules.service.common as service_common
import modules.service.haproxy as service_haproxy
import modules.roxywi.roxy as roxy
import modules.roxywi.logs as roxy_logs
import modules.roxywi.nettools as nettools
import modules.roxywi.common as roxywi_common
import modules.roxywi.overview as roxy_overview


@app.route('/overview/services')
@login_required
def show_services_overview():
	return roxy_overview.show_services_overview()


@app.route('/overview/server/<server_ip>')
@login_required
def overview_server(server_ip):
	return roxy_overview.show_overview(server_ip)


@app.route('/overview/users')
@login_required
def overview_users():
	return roxy_overview.user_owv()


@app.route('/overview/sub')
@login_required
@cache.cached()
def overview_sub():
	return roxy_overview.show_sub_ovw()


@app.route('/logs/<service>/<serv>', methods=['GET', 'POST'])
@login_required
def show_remote_log_files(service, serv):
	service = common.checkAjaxInput(service)
	serv = common.checkAjaxInput(serv)
	log_path = sql.get_setting(f'{service}_path_logs')
	return_files = server_mod.get_remote_files(serv, log_path, 'log')

	if 'error: ' in return_files:
		return return_files

	lang = roxywi_common.get_user_lang_for_flask()

	return render_template(
		'ajax/show_log_files.html', serv=serv, return_files=return_files, path_dir=log_path, lang=lang
	)


@app.route('/logs/<service>/<serv>/<rows>', defaults={'waf': '0'}, methods=['GET', 'POST'])
@app.route('/logs/<service>/waf/<serv>/<rows>', defaults={'waf': '1'}, methods=['GET', 'POST'])
@login_required
def show_logs(service, serv, rows, waf):
	if request.method == 'GET':
		grep = request.args.get('grep')
		exgrep = request.args.get('exgrep')
		hour = request.args.get('hour')
		minute = request.args.get('minute')
		hour1 = request.args.get('hour1')
		minute1 = request.args.get('minute1')
		log_file = request.args.get('file')
	else:
		grep = request.form.get('grep')
		exgrep = request.form.get('exgrep')
		hour = request.form.get('hour')
		minute = request.form.get('minute')
		hour1 = request.form.get('hour1')
		minute1 = request.form.get('minute1')
		log_file = request.form.get('file')

	if roxywi_common.check_user_group_for_flask():
		try:
			out = roxy_logs.show_roxy_log(serv=serv, rows=rows, waf=waf, grep=grep, exgrep=exgrep, hour=hour, minute=minute,
											hour1=hour1, minute1=minute1, service=service, log_file=log_file)
		except Exception as e:
			return str(e)
		else:
			return out


@app.route('/internal/show_version')
@cache.cached()
def show_roxywi_version():
	return render_template('ajax/check_version.html', versions=roxy.versions())


@app.route('/stats/view/<service>/<server_ip>')
def show_stats(service, server_ip):
	server_ip = common.is_ip_or_dns(server_ip)

	if service in ('nginx', 'apache'):
		return service_common.get_stat_page(server_ip, service)
	else:
		return service_haproxy.stat_page_action(server_ip)


@app.route('/portscanner/history/<server_ip>')
@login_required
def portscanner_history(server_ip):
	try:
		user_params = roxywi_common.get_users_params()
		user = user_params['user']
	except Exception:
		return redirect(url_for('login_page'))

	history = sql.select_port_scanner_history(server_ip)
	user_subscription = roxywi_common.return_user_subscription()

	return render_template(
		'include/port_scan_history.html', h2=1, autorefresh=0, role=user_params['role'], user=user, servers=user_params['servers'],
		history=history, user_services=user_params['user_services'], token=user_params['token'],
		user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'], lang=user_params['lang']
	)


@app.post('/portscanner/settings')
def change_settings_portscanner():
	server_id = common.checkAjaxInput(request.form.get('server_id'))
	enabled = common.checkAjaxInput(request.form.get('enabled'))
	notify = common.checkAjaxInput(request.form.get('notify'))
	history = common.checkAjaxInput(request.form.get('history'))
	user_group_id = [server[3] for server in sql.select_servers(id=server_id)]

	try:
		if sql.insert_port_scanner_settings(server_id, user_group_id[0], enabled, notify, history):
			return 'ok'
		else:
			if sql.update_port_scanner_settings(server_id, user_group_id[0], enabled, notify, history):
				return 'ok'
	except Exception as e:
		return f'error: Cannot save settings: {e}'
	else:
		return 'ok'


@app.route('/portscanner/scan/<int:server_id>')
def scan_port(server_id):
	server = sql.select_servers(id=server_id)
	ip = ''

	for s in server:
		ip = s[2]

	cmd = f"sudo nmap -sS {ip} |grep -E '^[[:digit:]]'|sed 's/  */ /g'"
	cmd1 = f"sudo nmap -sS {ip} |head -5|tail -2"

	stdout, stderr = server_mod.subprocess_execute(cmd)
	stdout1, stderr1 = server_mod.subprocess_execute(cmd1)

	if stderr != '':
		return f'error: {stderr}'
	else:
		lang = roxywi_common.get_user_lang_for_flask()
		return render_template('ajax/scan_ports.html', ports=stdout, info=stdout1, lang=lang)


@app.post('/nettols/<check>')
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
