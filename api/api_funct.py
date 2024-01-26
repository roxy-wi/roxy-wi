import os
import sys
import json
import random

from bottle import request
sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app/'))

import modules.db.sql as sql
import modules.server.ssh as ssh_mod
import modules.server.server as server_mod
import modules.config.section as section_mod
import modules.config.config as config_mod
import modules.config.runtime as runtime_mod
import modules.roxy_wi_tools as roxy_wi_tools
import modules.roxywi.logs as roxywi_logs
import modules.roxywi.user as roxywi_user
import modules.roxywi.common as roxywi_common
import modules.service.common as service_common
import modules.service.installation as service_mod
import modules.service.ha_cluster as ha_cluster

get_config_var = roxy_wi_tools.GetConfigVar()


def get_token():
	try:
		user_subscription = roxywi_common.return_user_status()
	except Exception as e:
		user_subscription = roxywi_common.return_unsubscribed_user_status()
		roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

	if user_subscription['user_status'] == 0:
		roxywi_common.logging('API', 'You are not subscribed. Please subscribe to have access to this feature.', roxywi=1)
		return False
	elif user_subscription['user_plan'] == 'user':
		roxywi_common.logging('API', 'This feature is not available for your plan.', roxywi=1)
		return False

	try:
		body = request.body.getvalue().decode('utf-8')
		login_pass = json.loads(body)
		login = login_pass['login']
		password_from_user = login_pass['password']
	except Exception as e:
		return f'error getting credentials: {e}'
	try:
		group_name = login_pass['group']
		group_id = sql.get_group_id_by_name(group_name)
	except Exception as e:
		return f'error getting group: {e}'
	try:
		users = sql.select_users(user=login)
		password = roxy_wi_tools.Tools.get_hash(password_from_user)
	except Exception as e:
		return f'error one more: {e}'

	for user in users:
		if user.activeuser == 0:
			return False
		if login in user.username and password == user.password:
			import uuid
			user_token = str(uuid.uuid4())
			role_id = sql.get_role_id(user.user_id, group_id)
			sql.write_api_token(user_token, group_id, role_id, user.username)
			return user_token
		else:
			return False


def check_login(required_service=0) -> bool:
	try:
		user_subscription = roxywi_common.return_user_status()
	except Exception as e:
		user_subscription = roxywi_common.return_unsubscribed_user_status()
		roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

	if user_subscription['user_status'] == 0:
		roxywi_common.logging('API', 'You are not subscribed. Please subscribe to have access to this feature.', roxywi=1)
		return False
	elif user_subscription['user_plan'] == 'user':
		roxywi_common.logging('API', 'This feature is not available for your plan.', roxywi=1)
		return False

	token = request.headers.get('token')
	if sql.get_api_token(token):
		if required_service != 0:
			user_id = sql.get_user_id_by_api_token(token)
			try:
				user_services = sql.select_user_services(user_id)
			except Exception:
				return False

			if str(required_service) in user_services:
				return True
			else:
				return False

		else:
			return True
	else:
		return False


def return_dict_from_out(server_id, out):
	data = {server_id: {}}
	for k in out:
		if "Ncat:" not in k:
			k = k.split(':')
			data[server_id][k[0]] = k[1].strip()
		else:
			data[server_id] = {"error": "Cannot connect to HAProxy"}

	return data


def check_permit_to_server(server_id, service='haproxy'):
	servers = sql.select_servers(id_hostname=server_id)
	token = request.headers.get('token')
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)

	try:
		for s in servers:
			server = roxywi_common.get_dick_permit(username=login, group_id=group_id, ip=s[2], token=token, service=service)
	except Exception as e:
		raise Exception(f'error: {e}')

	return server


def return_requred_serivce(service):
	if service == 'haproxy':
		required_service = 1
	elif service == 'nginx':
		required_service = 2
	elif service == 'apache':
		required_service = 4
	elif service == 'keepalived':
		required_service = 3
	else:
		required_service = 0

	return required_service


def get_server(server_id, service):
	if service != 'apache' and service != 'nginx' and service != 'haproxy' and service != 'keepalived':
		return dict(status='wrong service')
	data = {}
	try:
		servers = check_permit_to_server(server_id, service=service)

		for s in servers:
			data = {
				'server_id': s[0],
				'hostname': s[1],
				'ip': s[2],
				'group': s[3],
				'virt': s[4],
				'enable': s[5],
				'master': s[6],
				'creds': s[7]
			}
	except Exception as e:
		data = {server_id: {"error": f"{e}"}}
		return dict(error=data)

	return dict(server=data)


def get_status(server_id, service):
	if service not in ('apache', 'nginx', 'haproxy', 'keepalived'):
		return dict(status='wrong service')
	try:
		servers = check_permit_to_server(server_id, service=service)

		for s in servers:
			if service == 'haproxy':
				cmd = 'echo "show info" |nc %s %s -w 1|grep -e "Ver\|CurrConns\|Maxco\|MB\|Uptime:"' % (s[2], sql.get_setting('haproxy_sock_port'))
				out = server_mod.subprocess_execute(cmd)
				data = return_dict_from_out(server_id, out[0])
			elif service == 'nginx':
				cmd = [
					"/usr/sbin/nginx -v 2>&1|awk '{print $3}' && systemctl status nginx |grep -e 'Active' "
					"|awk '{print $2, $9$10$11$12$13}' && ps ax |grep nginx:|grep -v grep |wc -l"
				]
				try:
					out = server_mod.ssh_command(s[2], cmd)
					out1 = out.split()
					json_for_sending = {server_id: {"Version": out1[0].split('/')[1], "Uptime": out1[2], "Process": out1[3]}}
					data = json_for_sending
				except Exception as e:
					data = {server_id: {"error": "Cannot get status: " + str(e)}}
			elif service == 'apache':
				apache_stats_user = sql.get_setting('apache_stats_user')
				apache_stats_password = sql.get_setting('apache_stats_password')
				apache_stats_port = sql.get_setting('apache_stats_port')
				apache_stats_page = sql.get_setting('apache_stats_page')
				cmd = "curl -s -u %s:%s http://%s:%s/%s?auto |grep 'ServerVersion\|Processes\|ServerUptime:'" % \
					(apache_stats_user, apache_stats_password, s[2], apache_stats_port, apache_stats_page)
				servers_with_status = list()
				try:
					out = server_mod.subprocess_execute(cmd)
					if out != '':
						for k in out:
							servers_with_status.append(k)
					json_for_sending = {
						server_id: {
							"Version": servers_with_status[0][0].split('/')[1],
							"Uptime": servers_with_status[0][1].split(':')[1].strip(),
							"Process": servers_with_status[0][2].split(' ')[1]
						}
					}
					data = json_for_sending
				except Exception as e:
					data = {server_id: {"error": "Cannot get status: " + str(e)}}

	except Exception:
		data = {server_id: {"error": "Cannot find the server"}}
		return dict(error=data)

	return dict(status=data)


def get_all_statuses():
	data = {}
	try:
		servers = sql.select_servers()
		token = request.headers.get('token')
		login, group_id, role_id = sql.get_username_groupid_from_api_token(token)
		sock_port = sql.get_setting('haproxy_sock_port')

		for _s in servers:
			servers = roxywi_common.get_dick_permit(username=login, group_id=group_id, token=token)

		for s in servers:
			cmd = 'echo "show info" |nc %s %s -w 1|grep -e "Ver\|CurrConns\|Maxco\|MB\|Uptime:"' % (s[2], sock_port)
			data[s[2]] = {}
			out = server_mod.subprocess_execute(cmd)
			data[s[2]] = return_dict_from_out(s[1], out[0])
	except Exception:
		data = {"error": "Cannot find the server"}
		return dict(error=data)

	return dict(status=data)


def actions(server_id, action, service):
	if action not in ('start', 'stop', 'restart', 'reload'):
		return dict(status='wrong action')
	if service not in ('apache', 'nginx', 'haproxy', 'keepalived'):
		return dict(status='wrong service')

	try:
		servers = check_permit_to_server(server_id, service=service)

		for s in servers:
			if service == 'apache':
				service = service_common.get_correct_apache_service_name(server_ip=s[2])
			cmd = ["sudo systemctl %s %s" % (action, service)]
			error = server_mod.ssh_command(s[2], cmd)
			done = error if error else 'done'
			data = {'server_id': s[0], 'ip': s[2], 'action': action, 'hostname': s[1], 'status': done}

		return dict(status=data)
	except Exception as e:
		return dict(status=str(e))


def runtime(server_id):
	try:
		body = request.body.getvalue().decode('utf-8')
		json_loads = json.loads(body)
		action = json_loads['command']
		haproxy_sock = sql.get_setting('haproxy_sock')
		servers = check_permit_to_server(server_id)
		cmd = ['echo "%s" |sudo socat stdio %s' % (action, haproxy_sock)]

		for s in servers:
			out = server_mod.ssh_command(s[2], cmd)

		sep_data = out.split('\r\n')
		data = {server_id: sep_data}

		return dict(status=data)
	except Exception:
		return dict(status='error')


def show_backends(server_id):
	try:
		servers = check_permit_to_server(server_id)

		for s in servers:
			out = runtime_mod.show_backends(s[2], ret=1)

		data = {server_id: out}

	except Exception:
		data = {server_id: {"error": "Cannot find the server"}}
		return dict(error=data)

	return dict(backends=data)


def get_config(server_id, **kwargs):
	service = kwargs.get('service')
	if service not in ('apache', 'nginx', 'haproxy', 'keepalived'):
		return dict(status='wrong service')

	try:
		servers = check_permit_to_server(server_id, service=service)
	except Exception as e:
		data = {server_id: {"error": f"Cannot find the server {e}"}}
		return dict(error=data)

	for s in servers:
		server_ip = s[2]

	try:
		cfg = f'/tmp/{server_ip}.cfg'
	except Exception as e:
		data = {server_id: {"error": f"Cannot find the server with the service {service}: {e}"}}
		return dict(error=data)
	try:
		config_mod.get_config(server_ip, cfg, service=service, config_file_name=kwargs.get('config_path'))
	except Exception as e:
		data = {server_id: {"error": f"Cannot get config {e}"}}
		return dict(error=data)
	try:
		os.system("sed -i 's/\\n/\n/g' " + cfg)
	except Exception as e:
		data = {server_id: {"error": f"Cannot edit config {e}"}}
		return dict(error=data)
	try:
		conf = open(cfg, "r")
		config_read = conf.read()
		conf.close()
	except IOError as e:
		data = {server_id: {"error": f"Cannot read config {e}"}}
		return dict(error=data)

	data = {server_id: config_read}

	return dict(config=data)


def get_section(server_id):
	section_name = request.headers.get('section-name')
	servers = check_permit_to_server(server_id)
	for s in servers:
		cfg = '/tmp/' + s[2] + '.cfg'

		config_mod.get_config(s[2], cfg)
		start_line, end_line, config_read = section_mod.get_section_from_config(cfg, section_name)

	data = {server_id: {section_name: {'start_line': start_line, 'end_line': end_line, 'config_read': config_read}}}
	return dict(section=data)


def edit_section(server_id, delete=0):
	body = request.body.getvalue().decode('utf-8')
	section_name = request.headers.get('section-name')
	save = request.headers.get('action')
	token = request.headers.get('token')
	servers = check_permit_to_server(server_id)
	hap_configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)

	if save == '':
		save = 'save'
	elif save == 'restart':
		save = ''
	elif save == 'reload':
		save = 'reload'

	if delete == 1:
		body = ''
		action = 'deleted'
	else:
		action = 'edited'

	for s in servers:
		ip = s[2]
		cfg = f'/tmp/{ip}.cfg'

		out = config_mod.get_config(ip, cfg)
		start_line, end_line, config_read = section_mod.get_section_from_config(cfg, section_name)
		returned_config = section_mod.rewrite_section(start_line, end_line, cfg, body)
		time_zone = sql.get_setting('time_zone')
		get_date = roxy_wi_tools.GetDate(time_zone)
		cur_date = get_date.return_date('config')

		try:
			cfg_for_save = f'{hap_configs_dir}{ip}-{cur_date}.cfg'

			try:
				with open(cfg, "w") as conf:
					conf.write(returned_config)
				return_mess = 'section has been updated'
				os.system(f"/bin/cp {cfg} {cfg_for_save}")
				out = config_mod.master_slave_upload_and_restart(ip, cfg, save, login=login)
				roxywi_common.logging('localhost', f" section {section_name} has been {action} via API", login=login)
				roxywi_common.logging(
					ip, f'Section {section_name} has been {action} via API', roxywi=1,
					login=login, keep_history=1, service='haproxy'
				)

				if out:
					return_mess = out
			except IOError:
				return_mess = "cannot upload config"

			data = {server_id: return_mess}
		except Exception as e:
			data = {server_id: {"error": str(e)}}
			return dict(error=data)

		return dict(config=data)


def upload_config(server_id, **kwargs):
	service = kwargs.get('service')
	if service not in ('apache', 'nginx', 'haproxy', 'keepalived'):
		return dict(status='wrong service')

	body = request.body.getvalue().decode('utf-8')
	save = request.headers.get('action')
	token = request.headers.get('token')
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)
	nginx = ''
	apache = ''

	if service == 'nginx':
		configs_dir = get_config_var.get_config_var('configs', 'nginx_save_configs_dir')
		service_name = 'Apache'
		nginx = 1
	elif service == 'apache':
		configs_dir = get_config_var.get_config_var('configs', 'apache_save_configs_dir')
		service_name = 'NGINX'
		apache = 1
	else:
		configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
		service_name = 'HAProxy'

	if save == '':
		save = 'save'
	elif save == 'restart':
		save = ''
	elif save == 'reload':
		save = 'reload'

	try:
		servers = check_permit_to_server(server_id)

		for s in servers:
			ip = s[2]
		cfg = f'/tmp/{ip}.cfg'
		time_zone = sql.get_setting('time_zone')
		get_date = roxy_wi_tools.GetDate(time_zone)
		cur_date = get_date.return_date('config')
		cfg_for_save = f'{configs_dir}{ip}-{cur_date}.cfg'

		try:
			with open(cfg, "w") as conf:
				conf.write(body)
			return_mess = 'config has been uploaded'
			os.system("/bin/cp %s %s" % (cfg, cfg_for_save))

			if kwargs.get('service') == 'nginx':
				out = config_mod.master_slave_upload_and_restart(ip, cfg, save, login=login, nginx=nginx, config_file_name=kwargs.get('config_path'))
			elif kwargs.get('service') == 'apache':
				out = config_mod.master_slave_upload_and_restart(ip, cfg, save, login=login, apache=apache, config_file_name=kwargs.get('config_path'))
			else:
				out = config_mod.master_slave_upload_and_restart(ip, cfg, save, login=login)

			roxywi_common.logging('localhost', " config has been uploaded via API", login=login)
			roxywi_common.logging(
				ip, 'Config has been uploaded via API', roxywi=1, login=login, keep_history=1, service=service_name
			)

			if out:
				return_mess = out
		except IOError as e:
			return_mess = f"cannot upload config {e}"

		data = {server_id: return_mess}
	except Exception as e:
		data = {server_id: {"error": str(e)}}
		return dict(error=data)

	return dict(config=data)


def add_to_config(server_id):
	data = {}
	body = request.body.getvalue().decode('utf-8')
	save = request.headers.get('action')
	hap_configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
	token = request.headers.get('token')
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)
	time_zone = sql.get_setting('time_zone')
	get_date = roxy_wi_tools.GetDate(time_zone)

	if save == '':
		save = 'save'
	elif save == 'restart':
		save = ''

	try:
		servers = check_permit_to_server(server_id)

		for s in servers:
			ip = s[2]
		cfg = f'/tmp/{ip}.cfg'
		cur_date = get_date.return_date('config')
		cfg_for_save = f'{hap_configs_dir}{ip}-{cur_date}.cfg'
		out = config_mod.get_config(ip, cfg)
		try:
			with open(cfg, "a") as conf:
				conf.write('\n' + body + '\n')

			return_mess = 'section has been added to the config'
			os.system(f"/bin/cp {cfg} {cfg_for_save}")
			roxywi_common.logging('localhost', " section has been added via REST API", login=login)
			out = config_mod.upload_and_restart(ip, cfg, just_save=save)

			if out:
				return_mess = out
		except IOError:
			return_mess = "cannot upload config"

		data = {server_id: return_mess}
	except Exception:
		data[server_id] = {"error": "cannot find the server"}
		return dict(error=data)

	return dict(config=data)


def show_log(server_id):
	data = {}
	rows = request.headers.get('rows')
	waf = request.headers.get('waf')
	grep = request.headers.get('grep')
	hour = request.headers.get('start_hour')
	minute = request.headers.get('start_minute')
	hour1 = request.headers.get('end_hour')
	minute1 = request.headers.get('end_minute')

	if rows is None:
		rows = '10'
	if waf is None:
		waf = '0'
	if hour is None:
		hour = '00'
	if minute is None:
		minute = '00'
	if hour1 is None:
		hour1 = '24'
	if minute1 is None:
		minute1 = '00'

	try:
		servers = check_permit_to_server(server_id)

		for s in servers:
			ip = s[2]
	except Exception:

		data[server_id] = {"error": "Cannot find the server"}
		return dict(error=data)

	out = roxywi_logs.show_roxy_log(ip, rows=rows, waf=str(waf), grep=grep, hour=str(hour), minut=str(minute), hour1=str(hour1), minut1=str(minute1), html=0)
	data = {server_id: out}

	return dict(log=data)


def add_acl(server_id):
	body = request.body.getvalue().decode('utf-8')
	json_loads = json.loads(body)
	save = json_loads['action']
	section_name = json_loads['section-name']

	acl = generate_acl(with_newline=1)
	servers = check_permit_to_server(server_id)
	status = ''

	for s in servers:
		cfg = '/tmp/' + s[2] + '.cfg'
		server_ip = s[2]

	try:
		out = config_mod.get_config(server_ip, cfg)
		start_line, end_line, config_read = section_mod.get_section_from_config(cfg, section_name)
	except Exception as e:
		data = {server_id: {"error": f"Cannot read section: {e}"}}
		return dict(error=data)

	try:
		config_read += acl
		config = section_mod.rewrite_section(start_line, end_line, cfg, config_read)
		try:
			with open(cfg, "w") as conf:
				conf.write(config)
		except IOError as e:
			data = {server_id: {"error": f"Cannot read import config file: {e}"}}
			return dict(error=data)
	except Exception as e:
		data = {server_id: {"error": f"{e}"}}
		return dict(error=data)

	try:
		out = config_mod.master_slave_upload_and_restart(server_ip, cfg, just_save=save)
		if out != '':
			status = out
		else:
			status = 'ACL has been added'
	except Exception as e:
		data = {server_id: {"error": f"{e}"}}
		return dict(error=data)

	data = {'acl': status}
	return dict(data)


def del_acl(server_id):
	body = request.body.getvalue().decode('utf-8')
	json_loads = json.loads(body)
	save = json_loads['action']
	section_name = json_loads['section-name']
	acl = generate_acl()
	servers = check_permit_to_server(server_id)

	for s in servers:
		server_ip = s[2]
		cfg = f'/tmp/{server_ip}.cfg'
	try:
		out = config_mod.get_config(server_ip, cfg)
		start_line, end_line, config_read = section_mod.get_section_from_config(cfg, section_name)
	except Exception as e:
		data = {server_id: {"error": f"{e}"}}
		return dict(error=data)

	try:
		config_new_read = ''
		for line in config_read.split('\n'):
			if not line.startswith(acl):
				if line != '':
					config_new_read += line + '\n'
	except Exception as e:
		data = {server_id: {"error": f"Cannot delete ACL: {e}"}}
		return dict(error=data)

	try:
		config = config_mod.master_slave_upload_and_restart(start_line, end_line, cfg, config_new_read)
		try:
			with open(cfg, "w") as conf:
				conf.write(config)
		except IOError as e:
			data = {server_id: {"error": f"Cannot read import config file: {e}"}}
			return dict(error=data)
	except Exception as e:
		data = {server_id: {"error": f"Cannot delete ACL: {e}"}}
		return dict(error=data)

	try:
		out = config_mod.master_slave_upload_and_restart(server_ip, cfg, just_save=save)
		if out != '':
			status = out
		else:
			status = 'ACL has been deleted'
	except Exception as e:
		data = {server_id: {"error": f"{e}"}}
		return dict(error=data)

	return dict(acl=status)


def generate_acl(**kwargs):
	body = request.body.getvalue().decode('utf-8')
	json_loads = json.loads(body)
	if_value = json_loads['if_value']
	then_value = json_loads['then_value']
	if_acl = json_loads['if']
	then_acl = json_loads['then']
	acl = ''

	if if_acl == 'host_starts':
		acl_if_word = 'hdr_beg(host) -i '
	elif if_acl == 'host_ends':
		acl_if_word = 'hdr_end(host) -i '
	elif if_acl == 'path_starts':
		acl_if_word = 'path_beg -i '
	elif if_acl == 'path_ends':
		acl_if_word = 'path_end -i '
	elif if_acl == 'src_ip':
		acl_if_word = 'src ip '
	else:
		acl_if_word = ''

	if then_acl == 'use_backend':
		acl += '    use_backend '
	elif then_acl == 'redirect':
		acl += '    http-request redirect location '
	elif then_acl == 'allow':
		acl += '    http-request allow'
	elif then_acl == 'deny':
		acl += '    http-request deny'
	elif then_acl == 'return':
		acl += '    return '
	elif then_acl == 'set-header':
		acl += '    set-header '

	newline = '\n' if kwargs.get('with_newline') else ''
	acl += then_value + ' if { ' + acl_if_word + if_value + ' } ' + newline

	return acl


def user_list():
	data = {}
	token = request.headers.get('token')
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)
	users = sql.select_users(by_group_id=group_id)
	for user in users:
		data[user.user_id] = {
			'login': user.username,
			'email': user.email,
			'role': user.role,
			'ldap': user.ldap_user,
			'enabled': user.activeuser,
			'last_login_ip': user.last_login_ip,
		}
	data = {'users': data}
	return dict(data)


def create_user():
	body = request.body.getvalue().decode('utf-8')
	json_loads = json.loads(body)
	name = json_loads['name']
	email = json_loads['email']
	password = json_loads['password']
	role = json_loads['role']
	token = request.headers.get('token')
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)

	if roxywi_user.create_user(name, email, password, role, 1, group_id, role_id=role_id, token=token):
		data = {'status': 'done'}
		return dict(data)
	else:
		data = {'status': 'something went wrong'}
		return dict(data)


def ssh_list():
	data = {}
	token = request.headers.get('token')
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)
	sshs = sql.select_ssh(group=group_id)
	for ssh in sshs:
		data[ssh.id] = {
			'name': ssh.name,
			'username': ssh.username,
			'key_enabled': ssh.enable,
		}
	data = {'creds': data}
	return dict(data)


def create_ssh():
	body = request.body.getvalue().decode('utf-8')
	json_loads = json.loads(body)
	name = json_loads['name']
	enable = json_loads['key_enabled']
	username = json_loads['username']
	password = json_loads['password']
	token = request.headers.get('token')
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)
	if ssh_mod.create_ssh_cread_api(name, enable, group_id, username, password):
		data = {'status': 'done'}
		return dict(data)
	else:
		data = {'status': 'error: check all fields'}
		return dict(data)


def upload_ssh_key():
	body = request.body.getvalue().decode('utf-8')
	json_loads = json.loads(body)
	name = json_loads['name']
	key = json_loads['key']
	token = request.headers.get('token')
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)
	groups = sql.select_groups(id=group_id)
	for group in groups:
		user_group = group.name
	try:
		ssh_mod.upload_ssh_key(f'{name}_{user_group}', user_group, key)
		data = {'status': 'done'}
		return dict(data)
	except Exception as e:
		data = {'status': f'{e}'}
		return dict(data)


def create_server():
	body = request.body.getvalue().decode('utf-8')
	json_loads = json.loads(body)
	hostname = json_loads['hostname']
	ip = json_loads['ip']
	port = json_loads['port']
	virt = json_loads['virt']
	master_id = json_loads['master_id']
	cred_id = json_loads['cred_id']
	desc = json_loads['description']
	token = request.headers.get('token')
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)

	try:
		if server_mod.create_server(hostname, ip, group_id, virt, 1, master_id, cred_id, port, desc, 0, 0, 0, 0, role_id=role_id, token=token):
			data = {'status': 'done'}
			roxywi_common.logging(ip, f'A new server {hostname} has been created', roxywi=1, keep_history=1, service='server')
			return dict(data)
	except Exception as e:
		data = {'status': f'error: {e}'}
		return dict(data)


def cluster_list():
	token = request.headers.get('token')
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)
	clusters = sql.select_clusters(group_id)
	data = {}
	for cluster in clusters:
		data.setdefault(cluster.id, cluster.name)

	return dict(data)


def create_ha_cluster():
	token = request.headers.get('token')
	body = request.body.getvalue().decode('utf-8')
	json_loads = json.loads(body)
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)
	data = {'status': dict()}

	try:
		cluster_id = ha_cluster.create_cluster(json_loads, group_id)
	except Exception as e:
		data['status'] = f'error: Cannot create HA cluster: {e}'
		return data['status']
	else:
		data['status'].setdefault('cluster', 'done')
	try:
		json_loads['cluster_id'] = cluster_id
		json_dump = json.dumps(json_loads)
		service_mod.install_service('keepalived', json_dump)
	except Exception as e:
		data['status'].setdefault('keepalived', f'error: {e}')
	else:
		data['status'].setdefault('keepalived', 'done')

	if json_loads['services']['haproxy']['enabled']:
		try:
			service_mod.install_service('haproxy', body)
		except Exception as e:
			data['status'].setdefault('haproxy', f'error: {e}')
		else:
			data['status'].setdefault('haproxy', 'done')

	if json_loads['services']['nginx']['enabled']:
		try:
			service_mod.install_service('nginx', body)
		except Exception as e:
			data['status'].setdefault('nginx', f'error: {e}')
		else:
			data['status'].setdefault('nginx', 'done')

	return dict(data)


def update_cluster():
	token = request.headers.get('token')
	body = request.body.getvalue().decode('utf-8')
	json_loads = json.loads(body)
	login, group_id, role_id = sql.get_username_groupid_from_api_token(token)
	data = {'status': dict()}

	try:
		ha_cluster.update_cluster(json_loads, group_id)
	except Exception as e:
		data['status'] = f'error: Cannot create HA cluster: {e}'
		return data['status']

	if json_loads['services']['haproxy']['enabled']:
		try:
			service_mod.install_service('haproxy', body)
		except Exception as e:
			data['status'].setdefault('haproxy', f'error: {e}')
		else:
			data['status'].setdefault('haproxy', 'done')

	if json_loads['services']['nginx']['enabled']:
		try:
			service_mod.install_service('nginx', body)
		except Exception as e:
			data['status'].setdefault('nginx', f'error: {e}')
		else:
			data['status'].setdefault('nginx', 'done')

	return dict(data)


def delete_ha_cluster():
	body = request.body.getvalue().decode('utf-8')
	json_loads = json.loads(body)
	cluster_id = json_loads['cluster_id']
	data = {'status': dict()}
	try:
		ha_cluster.delete_cluster(cluster_id)
	except Exception as e:
		data['status'] = f'error: {e}'
	else:
		data['status'] = 'done'
	return dict(data)
