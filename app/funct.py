# -*- coding: utf-8 -*-
import cgi
import os
import sys

form = cgi.FieldStorage()
serv = form.getvalue('serv')


def get_app_dir():
	d = sys.path[0]
	d = d.split('/')[-1]		
	return sys.path[0] if d == "app" else os.path.dirname(sys.path[0])	


def get_config_var(sec, var):
	from configparser import ConfigParser, ExtendedInterpolation
	try:
		path_config = "/var/www/haproxy-wi/app/roxy-wi.cfg"
		config = ConfigParser(interpolation=ExtendedInterpolation())
		config.read(path_config)
	except Exception:
		print('Content-type: text/html\n')
		print('<center><div class="alert alert-danger">Check the config file, whether it exists and the path. Must be: app/roxy-wi.cfg</div>')
	try:
		return config.get(sec, var)
	except Exception:
		print('Content-type: text/html\n')
		print('<center><div class="alert alert-danger">Check the config file. Presence section %s and parameter %s</div>' % (sec, var))
					
					
def get_data(log_type):
	from datetime import datetime
	from pytz import timezone
	import sql
	fmt = "%Y-%m-%d.%H:%M:%S"

	try:
		now_utc = datetime.now(timezone(sql.get_setting('time_zone')))
	except Exception:
		now_utc = datetime.now(timezone('UTC'))

	if log_type == 'config':
		fmt = "%Y-%m-%d.%H:%M:%S"
	elif log_type == 'logs':
		fmt = '%Y%m%d'
	elif log_type == "date_in_log":
		fmt = "%b %d %H:%M:%S"
	elif log_type == 'regular':
		fmt = "%Y-%m-%d %H:%M:%S"

	return now_utc.strftime(fmt)


def get_user_group(**kwargs):
	import sql
	import http.cookies

	try:
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_group_id = cookie.get('group')
		user_group_id1 = user_group_id.value
		groups = sql.select_groups(id=user_group_id1)
		for g in groups:
			if g.group_id == int(user_group_id1):
				if kwargs.get('id'):
					user_group = g.group_id
				else:
					user_group = g.name
	except Exception:
		check_user_group()

	return user_group


def logging(serv, action, **kwargs):
	import sql
	import http.cookies
	log_path = get_config_var('main', 'log_path')
	try:
		user_group = get_user_group()
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	except:
		user_group = ''

	if not os.path.exists(log_path):
		os.makedirs(log_path)

	try:
		ip = cgi.escape(os.environ["REMOTE_ADDR"])
	except Exception:
		ip = ''

	try:
		user_uuid = cookie.get('uuid')
		login = sql.get_user_name_by_uuid(user_uuid.value)
	except Exception:
		login = ''

	if kwargs.get('alerting') == 1:
		mess = get_data('date_in_log') + action + "\n"
		log = open(log_path + "/checker-"+get_data('logs')+".log", "a")
	elif kwargs.get('metrics') == 1:
		mess = get_data('date_in_log') + action + "\n"
		log = open(log_path + "/metrics-"+get_data('logs')+".log", "a")
	elif kwargs.get('keep_alive') == 1:
		mess = get_data('date_in_log') + action + "\n"
		log = open(log_path + "/keep_alive-"+get_data('logs')+".log", "a")
	elif kwargs.get('port_scanner') == 1:
		mess = get_data('date_in_log') + action + "\n"
		log = open(log_path + "/port_scanner-"+get_data('logs')+".log", "a")
	elif kwargs.get('haproxywi') == 1:
		if kwargs.get('login'):
			mess = get_data('date_in_log') + " from " + ip + " user: " + login + ", group: " + user_group + ", " + \
				action + " for: " + serv + "\n"
		else:
			mess = get_data('date_in_log') + " " + action + " from " + ip + "\n"
		log = open(log_path + "/roxy-wi-"+get_data('logs')+".log", "a")
	elif kwargs.get('provisioning') == 1:
		mess = get_data('date_in_log') + " from " + ip + " user: " + login + ", group: " + user_group + ", " + \
				action + "\n"
		log = open(log_path + "/provisioning-"+get_data('logs')+".log", "a")
	else:
		mess = get_data('date_in_log') + " from " + ip + " user: " + login + ", group: " + user_group + ", " + \
				action + " for: " + serv + "\n"
		log = open(log_path + "/config_edit-"+get_data('logs')+".log", "a")
	try:	
		log.write(mess)
		log.close()
	except IOError as e:
		print('<center><div class="alert alert-danger">Can\'t write log. Please check log_path in config %e</div></center>' % e)


def telegram_send_mess(mess, **kwargs):
	import telebot
	from telebot import apihelper
	import sql
	token_bot = ''
	channel_name = ''

	if kwargs.get('telegram_channel_id'):
		telegrams = sql.get_telegram_by_id(kwargs.get('telegram_channel_id'))
	else:
		telegrams = sql.get_telegram_by_ip(kwargs.get('ip'))
		slack_send_mess(mess, ip=kwargs.get('ip'))

	proxy = sql.get_setting('proxy')

	for telegram in telegrams:
		token_bot = telegram.token
		channel_name = telegram.chanel_name

	if token_bot == '' or channel_name == '':
		mess = " error: Can't send message. Add Telegram channel before use alerting at this servers group"
		print(mess)
		logging('localhost', mess, haproxywi=1)
		sys.exit()
		
	if proxy is not None and proxy != '' and proxy != 'None':
		apihelper.proxy = {'https': proxy}
	try:
		bot = telebot.TeleBot(token=token_bot)
		bot.send_message(chat_id=channel_name, text=mess)
	except Exception as e:
		print(str(e))
		logging('localhost', str(e), haproxywi=1)


def slack_send_mess(mess, **kwargs):
	import sql
	from slack_sdk import WebClient
	from slack_sdk.errors import SlackApiError
	slack_token = ''
	channel_name = ''

	if kwargs.get('slack_channel_id'):
		slacks = sql.get_slack_by_id(kwargs.get('slack_channel_id'))
	else:
		slacks = sql.get_slack_by_ip(kwargs.get('ip'))

	proxy = sql.get_setting('proxy')

	for slack in slacks:
		slack_token = slack[1]
		channel_name = slack[2]

	if proxy is not None and proxy != '' and proxy != 'None':
		proxies = dict(https=proxy, http=proxy)
		client = WebClient(token=slack_token, proxies=proxies)
	else:
		client = WebClient(token=slack_token)

	try:
		client.chat_postMessage(channel='#'+channel_name, text=mess)
	except SlackApiError as e:
		print('error: ' + str(e))
		logging('localhost', str(e), haproxywi=1)


def check_login():
	import sql
	import http.cookies
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_uuid = cookie.get('uuid')
	ref = os.environ.get("REQUEST_URI")

	sql.delete_old_uuid()

	if user_uuid is not None:
		sql.update_last_act_user(user_uuid.value)
		if sql.get_user_name_by_uuid(user_uuid.value) is None:
			print('<meta http-equiv="refresh" content="0; url=login.py?ref=%s">' % ref)
			return False
	else:
		print('<meta http-equiv="refresh" content="0; url=login.py?ref=%s">' % ref)
		return False


def is_admin(**kwargs):
	import sql
	import http.cookies
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	try:
		role = sql.get_user_role_by_uuid(user_id.value)
	except Exception:
		role = 4
		pass
	level = kwargs.get("level")

	if level is None:
		level = 1

	try:
		return True if role <= level else False
	except Exception as e:
		print('error: '+str(e))
		# return False


def page_for_admin(**kwargs):
	if kwargs.get("level"):
		give_level = kwargs.get("level")
	else:
		give_level = 1

	if not is_admin(level=give_level):
		print('<meta http-equiv="refresh" content="0; url=/">')
		import sys
		sys.exit()	


def return_ssh_keys_path(serv, **kwargs):
	import sql
	full_path = get_config_var('main', 'fullpath')
	ssh_enable = ''
	ssh_user_name = ''
	ssh_user_password = ''
	ssh_key_name = ''

	if kwargs.get('id'):	
		for sshs in sql.select_ssh(id=kwargs.get('id')):
			ssh_enable = sshs.enable
			ssh_user_name = sshs.username
			ssh_user_password = sshs.password
			ssh_key_name = full_path+'/keys/%s.pem' % sshs.name
	else:
		for sshs in sql.select_ssh(serv=serv):
			ssh_enable = sshs.enable
			ssh_user_name = sshs.username
			ssh_user_password = sshs.password
			ssh_key_name = full_path+'/keys/%s.pem' % sshs.name

	return ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name


def ssh_connect(serv):
	import paramiko
	from paramiko import SSHClient
	import sql

	ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = return_ssh_keys_path(serv)
	servers = sql.select_servers(server=serv)
	ssh_port = 22

	for server in servers:
		ssh_port = server[10]

	ssh = SSHClient()
	ssh.load_system_host_keys()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

	try:
		if ssh_enable == 1:
			cloud = sql.is_cloud()
			if cloud != '':
				k = paramiko.pkey.load_private_key_file(ssh_key_name, password=cloud)
			else:
				k = paramiko.pkey.load_private_key_file(ssh_key_name)
			ssh.connect(hostname=serv, port=ssh_port, username=ssh_user_name, pkey=k, timeout=11, banner_timeout=200)
		else:
			ssh.connect(hostname=serv, port=ssh_port, username=ssh_user_name, password=ssh_user_password, timeout=11, banner_timeout=200)
		return ssh
	except paramiko.AuthenticationException as e:
		logging('localhost', ' ' + str(e), haproxywi=1)
		print('error: Authentication failed, please verify your credentials')
	except paramiko.SSHException as sshException:
		logging('localhost', ' ' + str(sshException), haproxywi=1)
		print('error: Unable to establish SSH connection: %s ') % sshException
	except paramiko.PasswordRequiredException as e:
		logging('localhost', ' ' + str(e), haproxywi=1)
		print('error: %s ') % e
	except paramiko.BadHostKeyException as badHostKeyException:
		logging('localhost', ' ' + str(badHostKeyException), haproxywi=1)
		print('error: Unable to verify server\'s host key: %s ') % badHostKeyException
	except Exception as e:
		logging('localhost', ' ' + str(e), haproxywi=1)
		if e == "No such file or directory":
			print('error: %s. Check SSH key') % e
		elif e == "Invalid argument":
			print('error: Check the IP of the server')
		else:
			print(str(e))


def get_config(serv, cfg, **kwargs):
	import sql

	if kwargs.get("keepalived"):
		config_path = "/etc/keepalived/keepalived.conf"  
	elif kwargs.get("nginx"):
		config_path = sql.get_setting('nginx_config_path')
	else: 
		config_path = sql.get_setting('haproxy_config_path')	

	ssh = ssh_connect(serv)
	try:
		sftp = ssh.open_sftp()
	except Exception as e:
		logging('localhost', str(e), haproxywi=1)
	try:
		sftp.get(config_path, cfg)
	except Exception as e:
		logging('localhost', str(e), haproxywi=1)
	try:	
		sftp.close()
		ssh.close()
	except Exception as e:
		ssh = str(e)
		logging('localhost', ssh, haproxywi=1)
		return ssh


def diff_config(oldcfg, cfg):
	import http.cookies
	import sql
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	log_path = get_config_var('main', 'log_path')
	user_group = get_user_group()
	diff = ""
	date = get_data('date_in_log') 
	cmd = "/bin/diff -ub %s %s" % (oldcfg, cfg)

	try:
		user_uuid = cookie.get('uuid')
		login = sql.get_user_name_by_uuid(user_uuid.value)
	except Exception:
		login = ''

	output, stderr = subprocess_execute(cmd)

	for line in output:
		diff += date + " user: " + login + ", group: " + user_group + " " + line + "\n"
	try:		
		log = open(log_path + "/config_edit-"+get_data('logs')+".log", "a")
		log.write(diff)
		log.close()
	except IOError:
		print('<center><div class="alert alert-danger">Can\'t read write change to log. %s</div></center>' % stderr)
		pass


def get_sections(config, **kwargs):
	return_config = list()
	with open(config, 'r') as f:
		for line in f:		
			if kwargs.get('service') == 'nginx':
				if 'server_name' in line:
					line = line.split('server_name')[1]
					line = line.split(';')[0]
					line = line.strip()
					return_config.append(line)
			elif kwargs.get('service') == 'keepalived':
				import re
				ip_pattern = re.compile('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
				find_ip = re.findall(ip_pattern,line)
				if find_ip:
					return_config.append(find_ip[0])
			else:	
				if ( 
					line.startswith('listen') or 
					line.startswith('frontend') or 
					line.startswith('backend') or 
					line.startswith('cache') or 
					line.startswith('defaults') or 
					line.startswith('global') or 
					line.startswith('#HideBlockEnd') or 
					line.startswith('#HideBlockStart') or
					line.startswith('peers') or
					line.startswith('resolvers') or
					line.startswith('userlist') or
					line.startswith('http-errors')
					):
					line = line.strip()
					return_config.append(line)

	return return_config


def get_section_from_config(config, section):
	record = False
	start_line = ""
	end_line = ""
	return_config = ""
	with open(config, 'r') as f:
		for index, line in enumerate(f):
			if line.startswith(section + '\n'):
				start_line = index
				return_config += line
				record = True 
				continue
			if record:
				if ( 
					line.startswith('listen') or 
					line.startswith('frontend') or 
					line.startswith('backend') or 
					line.startswith('cache') or 
					line.startswith('defaults') or 
					line.startswith('global') or 
					line.startswith('#HideBlockEnd') or 
					line.startswith('#HideBlockStart') or
					line.startswith('peers') or
					line.startswith('resolvers') or
					line.startswith('userlist') or
					line.startswith('http-errors')
					):
					record = False
					end_line = index
					end_line = end_line - 1
				else:
					return_config += line

	if end_line == "":
		f = open(config, "r")
		line_list = f.readlines()
		end_line = len(line_list)

	return start_line, end_line, return_config


def rewrite_section(start_line, end_line, config, section):
	record = False
	start_line = int(start_line)
	end_line = int(end_line)
	return_config = ""
	with open(config, 'r') as f:
		for index, line in enumerate(f):
			index = int(index)
			if index == start_line:
				record = True
				return_config += section
				return_config += "\n"
				continue
			if index == end_line:
				record = False
				continue
			if record:
				continue

			return_config += line

	return return_config


def get_userlists(config):
	return_config = ''
	with open(config, 'r') as f:
		for line in f:
			if line.startswith('userlist'):
				line = line.strip()
				return_config += line + ','

	return return_config


def get_backends_from_config(serv, backends=''):
	configs_dir = get_config_var('configs', 'haproxy_save_configs_dir')
	format_cfg = 'cfg'

	try:
		cfg = configs_dir+get_files(dir=configs_dir, format=format_cfg)[0]
	except Exception as e:
		logging('localhost', str(e), haproxywi=1)
		try:
			cfg = configs_dir + serv + "-" + get_data('config') + '.'+format_cfg
		except Exception:
			logging('localhost', ' Cannot generate cfg path', haproxywi=1)
		try:
			error = get_config(serv, cfg)
		except Exception:
			logging('localhost', ' Cannot download config', haproxywi=1)
			print('error: Cannot get backends')
			sys.exit()

	with open(cfg, 'r') as f:
		for line in f:	
			if backends == 'frontend':
				if (line.startswith('listen') or line.startswith('frontend')) and 'stats' not in line:
					line = line.strip()
					print(line.split(' ')[1], end="<br>")


def get_all_stick_table():
	import sql
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	cmd = 'echo "show table"|nc %s %s |awk \'{print $3}\' | tr -d \'\n\' | tr -d \'[:space:]\'' % (serv, hap_sock_p)
	output, stderr = subprocess_execute(cmd)
	return output[0]


def get_stick_table(table):
	import sql
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	cmd = 'echo "show table %s"|nc %s %s |awk -F"#" \'{print $2}\' |head -1 | tr -d \'\n\'' % (table, serv, hap_sock_p)
	output, stderr = subprocess_execute(cmd)
	tables_head = []
	for i in output[0].split(','):
		i = i.split(':')[1]
		tables_head.append(i)

	cmd = 'echo "show table %s"|nc %s %s |grep -v "#"' % (table, serv, hap_sock_p)
	output, stderr = subprocess_execute(cmd)

	return tables_head, output


def show_installation_output(error, output, service):
	if error and "WARNING" not in error:
		logging('localhost', error, haproxywi=1)
		print('error: '+error)
	else:
		for l in output:
			if "Traceback" in l or "FAILED" in l:
				try:
					print(l)
					break
				except Exception:
					print(output)
					break
		else:
			print('success: ' + service + ' has been installed')


def install_haproxy(serv, **kwargs):
	import sql
	script = "install_haproxy.sh"
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	stats_port = sql.get_setting('stats_port')
	server_state_file = sql.get_setting('server_state_file')
	stats_user = sql.get_setting('stats_user')
	stats_password = sql.get_setting('stats_password')
	proxy = sql.get_setting('proxy')
	haproxy_ver = kwargs.get('hapver')
	server_for_installing = kwargs.get('server')
	ssh_port = 22
	ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = return_ssh_keys_path(serv)

	if ssh_enable == 0:
		ssh_key_name = ''

	servers = sql.select_servers(server=serv)
	for server in servers:
		ssh_port = str(server[10])

	os.system("cp scripts/%s ." % script)

	if haproxy_ver is None:
		haproxy_ver = '2.3.0-1'

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy 
	else:
		proxy_serv = ''

	syn_flood_protect = '1' if kwargs.get('syn_flood') == "1" else ''

	commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv +
				" SOCK_PORT=" + hap_sock_p + " STAT_PORT=" + stats_port + " STAT_FILE="+server_state_file +
				" SSH_PORT=" + ssh_port + " STATS_USER=" + stats_user +
				" STATS_PASS=" + stats_password + " HAPVER=" + haproxy_ver + " SYN_FLOOD=" + syn_flood_protect +
				" HOST=" + serv + " USER=" + ssh_user_name + " PASS=" + ssh_user_password + " KEY=" + ssh_key_name]

	output, error = subprocess_execute(commands[0])
	if server_for_installing:
		service = server_for_installing + ' HAProxy'
	else:
		service = ' HAProxy'
	show_installation_output(error, output, service)

	os.system("rm -f %s" % script)
	sql.update_haproxy(serv)


def waf_install(serv):
	import sql
	script = "waf.sh"
	tmp_config_path = sql.get_setting('tmp_config_path')
	proxy = sql.get_setting('proxy')
	haproxy_dir = sql.get_setting('haproxy_dir')
	ver = check_haproxy_version(serv)

	os.system("cp scripts/%s ." % script)

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy 
	else:
		proxy_serv = ''

	commands = ["sudo chmod +x " + tmp_config_path+script + " && " + tmp_config_path+script + " PROXY=" + proxy_serv +
				" HAPROXY_PATH=" + haproxy_dir + " VERSION=" + ver]

	error = str(upload(serv, tmp_config_path, script))
	if error:
		print('error: '+error)
		logging('localhost', error, haproxywi=1)
	os.system("rm -f %s" % script)

	stderr = ssh_command(serv, commands, print_out="1")

	sql.insert_waf_metrics_enable(serv, "0")
	sql.insert_waf_rules(serv)


def install_nginx(serv, **kwargs):
	import sql
	script = "install_nginx.sh"	
	stats_user = sql.get_setting('nginx_stats_user')
	stats_password = sql.get_setting('nginx_stats_password')
	stats_port = sql.get_setting('nginx_stats_port')
	stats_page = sql.get_setting('nginx_stats_page')
	config_path = sql.get_setting('nginx_config_path')
	server_for_installing = kwargs.get('server')
	proxy = sql.get_setting('proxy')
	ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = return_ssh_keys_path(serv)

	if ssh_enable == 0:
		ssh_key_name = ''

	os.system("cp scripts/%s ." % script)

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy 
	else:
		proxy_serv = ''

	servers = sql.select_servers(server=serv)
	for server in servers:
		ssh_port = str(server[10])

	syn_flood_protect = '1' if form.getvalue('syn_flood') == "1" else ''

	commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv + " STATS_USER=" + stats_user +
				" STATS_PASS=" + stats_password + " SSH_PORT=" + ssh_port + " CONFIG_PATH=" + config_path +
				" STAT_PORT=" + stats_port + " STAT_PAGE=" + stats_page+" SYN_FLOOD=" + syn_flood_protect +
				" HOST=" + serv + " USER=" + ssh_user_name + " PASS=" + ssh_user_password + " KEY=" + ssh_key_name]

	output, error = subprocess_execute(commands[0])
	if server_for_installing:
		service = server_for_installing + ' Nginx'
	else:
		service = ' Nginx'
	show_installation_output(error, output, service)

	os.system("rm -f %s" % script)
	sql.update_nginx(serv)


def update_haproxy_wi(service):
	if service != 'roxy-wi':
		try:
			if service != 'keep_alive':
				service = service.split('_')[0]
		except Exception:
			pass
		# service = 'roxy-wi-'+service
	cmd = 'sudo -S yum -y update ' + service +' && sudo systemctl restart ' + service
	output, stderr = subprocess_execute(cmd)
	print(output)
	print(stderr)


def check_haproxy_version(serv):
	import sql
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	ver = ""
	cmd = "echo 'show info' |nc %s %s |grep Version |awk '{print $2}'" % (serv, hap_sock_p)
	output, stderr = subprocess_execute(cmd)
	for line in output:
		ver = line

	return ver


def upload(serv, path, file, **kwargs):
	error = ""
	full_path = path + file
	if kwargs.get('dir') == "fullpath":
		full_path = path
	
	try:
		ssh = ssh_connect(serv)
	except Exception as e:
		error = e.args
		logging('localhost', str(e.args[0]), haproxywi=1)
		print(' Cannot upload '+file+' to '+full_path+' to server: '+serv+' error: '+str(e.args))

	try:
		sftp = ssh.open_sftp()
	except Exception as e:
		error = e.args
		logging('localhost', str(e.args[0]), haproxywi=1)
		print('Cannot upload '+file+' to '+full_path+' to server: '+serv+' error: '+str(e.args))
		
	try:
		file = sftp.put(file, full_path)
	except Exception as e:
		error = e.args
		print('Cannot upload '+file+' to '+full_path+' to server: '+serv+' error: '+str(e.args))
		logging('localhost', ' Cannot upload '+file+' to '+full_path+' to server: '+serv+' Error: '+str(e.args), haproxywi=1)

	try:
		sftp.close()
		ssh.close()
	except Exception as e:
		error = e.args
		logging('localhost', str(error[0]), haproxywi=1)
		print('Cannot upload '+file+' to '+full_path+' to server: '+serv+' error: '+str(e.args))

	return str(error)


def upload_and_restart(serv, cfg, **kwargs):
	import sql
	error = ""

	if kwargs.get("nginx"):
		config_path = sql.get_setting('nginx_config_path')
		tmp_file = sql.get_setting('tmp_config_path') + "/" + get_data('config') + ".conf"
	else:
		config_path = sql.get_setting('haproxy_config_path')
		tmp_file = sql.get_setting('tmp_config_path') + "/" + get_data('config') + ".cfg"

	try:
		os.system("dos2unix "+cfg)
	except OSError:
		return 'Please install dos2unix' 

	if kwargs.get("keepalived") == 1:
		if kwargs.get("just_save") == "save":
			commands = ["sudo mv -f " + tmp_file + " /etc/keepalived/keepalived.conf"]
		elif kwargs.get("just_save") == "reload":
			commands = [
				"sudo mv -f " + tmp_file + " /etc/keepalived/keepalived.conf && sudo systemctl reload keepalived"]
		else:
			commands = ["sudo mv -f " + tmp_file + " /etc/keepalived/keepalived.conf && sudo systemctl restart keepalived"]
	elif kwargs.get("nginx"):
		if kwargs.get("just_save") == "save":
			commands = ["sudo mv -f " + tmp_file + " " + config_path + " && sudo nginx -t -q"]
		elif kwargs.get("just_save") == "reload":
			commands = ["sudo mv -f " + tmp_file + " " + config_path + " && sudo nginx -t -q && sudo systemctl reload nginx"]
		else:
			commands = ["sudo mv -f " + tmp_file + " " + config_path + " && sudo nginx -t -q && sudo systemctl restart nginx"]
		if sql.return_firewall(serv):
			commands[0] += open_port_firewalld(cfg, serv=serv, service='nginx')
	else:
		haproxy_enterprise = sql.get_setting('haproxy_enterprise')

		if haproxy_enterprise == '1':
			haproxy_service_name = "hapee-2.0-lb"
		else:
			haproxy_service_name = "haproxy"

		if kwargs.get("just_save") == "test":
			commands = ["sudo "+haproxy_service_name+"  -q -c -f " + tmp_file + " && sudo rm -f " + tmp_file]
		elif kwargs.get("just_save") == "save":
			commands = ["sudo "+haproxy_service_name+"  -q -c -f " + tmp_file + " && sudo mv -f " + tmp_file + " " + config_path]
		elif kwargs.get("just_save") == "reload":
			commands = ["sudo "+haproxy_service_name+"  -q -c -f " + tmp_file + " && sudo mv -f " + tmp_file + " " + config_path + " && sudo systemctl reload "+haproxy_service_name+""]
		else:
			commands = ["sudo "+haproxy_service_name+"  -q -c -f " + tmp_file + " && sudo mv -f " + tmp_file + " " + config_path + " && sudo systemctl restart "+haproxy_service_name+""]
		if sql.return_firewall(serv):
			commands[0] += open_port_firewalld(cfg, serv=serv)
	error += str(upload(serv, tmp_file, cfg, dir='fullpath'))

	try:
		error += ssh_command(serv, commands)
	except Exception as e:
		error += e
	if error:
		logging('localhost', error, haproxywi=1)

	return error


def master_slave_upload_and_restart(serv, cfg, just_save, **kwargs):
	import sql
	masters = sql.is_master(serv)
	error = ""
	for master in masters:
		if master[0] is not None:
			error += upload_and_restart(master[0], cfg, just_save=just_save, nginx=kwargs.get('nginx'))

	error += upload_and_restart(serv, cfg, just_save=just_save, nginx=kwargs.get('nginx'))

	return error


def open_port_firewalld(cfg, serv, **kwargs):
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Cannot read exported config file</div>')
	
	firewalld_commands = ' &&'
	ports = ''

	for line in conf:
		if kwargs.get('service') == 'nginx':
			if "listen " in line and '#' not in line:
				try:
					listen = ' '.join(line.split())
					listen = listen.split(" ")[1]
					listen = listen.split(";")[0]
					try:
						listen = int(listen)
						ports += str(listen)+' '
						firewalld_commands += ' sudo firewall-cmd --zone=public --add-port=%s/tcp --permanent -q &&' % str(listen)
					except Exception:
						pass
				except Exception:
					pass
		else:
			if "bind" in line:
				try:
					bind = line.split(":")
					bind[1] = bind[1].strip(' ')
					bind = bind[1].split("ssl")
					bind = bind[0].strip(' \t\n\r')
					try:
						bind = int(bind)
						firewalld_commands += ' sudo firewall-cmd --zone=public --add-port=%s/tcp --permanent -q &&' % str(bind)
						ports += str(bind)+' '
					except Exception:
						pass
				except Exception:
					pass

	firewalld_commands += 'sudo firewall-cmd --reload -q' 
	logging(serv, ' Next ports have been opened: ' + ports)
	return firewalld_commands


def check_haproxy_config(serv):
	import sql
	commands = ["haproxy  -q -c -f %s" % sql.get_setting('haproxy_config_path')]
	ssh = ssh_connect(serv)
	for command in commands:
		stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
		if not stderr.read():
			return True
		else:
			return False
	ssh.close()
		
		
def show_log(stdout, **kwargs):
	i = 0
	out = ''
	grep = ''

	if kwargs.get('grep'):
		import re
		grep = kwargs.get('grep')
		grep = re.sub(r'[?|$|.|!|^|*|\]|\[|,| |]', r'', grep)
		
	for line in stdout:		
		if kwargs.get("html") != 0:
			i = i + 1
			if kwargs.get('grep'):
				line = line.replace(grep, '<span style="color: red; font-weight: bold;">'+grep+'</span>')
			line_class = "line3" if i % 2 == 0 else "line"
			out += '<div class="'+line_class+'">' + line + '</div>'
		else:
			out += line
		
	return out
		
		
def show_haproxy_log(serv, rows=10, waf='0', grep=None, hour='00', minut='00', hour1='24', minut1='00', service='haproxy', **kwargs):
	import sql
	exgrep = form.getvalue('exgrep')
	date = hour+':'+minut
	date1 = hour1+':'+minut1
	
	if grep is not None:
		grep_act = '|egrep "%s"' % grep
	else:
		grep_act = ''
		
	if exgrep is not None:
		exgrep_act = '|egrep -v "%s"' % exgrep
	else:
		exgrep_act = ''

	if service == 'nginx' or service == 'haproxy':
		syslog_server_enable = sql.get_setting('syslog_server_enable')
		if syslog_server_enable is None or syslog_server_enable == "0":
			if service == 'nginx':
				local_path_logs = sql.get_setting('nginx_path_error_logs')
				commands = ["sudo cat %s| awk '$2>\"%s:00\" && $2<\"%s:00\"' |tail -%s %s %s" % (local_path_logs, date, date1, rows, grep_act, exgrep_act)]
			else:
				local_path_logs = sql.get_setting('local_path_logs')
				commands = ["sudo cat %s| awk '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s %s %s" % (local_path_logs, date, date1, rows, grep_act, exgrep_act)]
			syslog_server = serv
		else:
			commands = ["sudo cat /var/log/%s/syslog.log | sed '/ %s:00/,/ %s:00/! d' |tail -%s %s %s %s" % (serv, date, date1, rows, grep_act, grep, exgrep_act)]
			syslog_server = sql.get_setting('syslog_server')
		
		if waf == "1":
			local_path_logs = '/var/log/modsec_audit.log'
			commands = ["sudo cat %s |tail -%s %s %s" % (local_path_logs, rows, grep_act, exgrep_act)]
		
		if kwargs.get('html') == 0:
			a = ssh_command(syslog_server, commands)
			return show_log(a, html=0, grep=grep)	
		else:
			return ssh_command(syslog_server, commands, show_log='1', grep=grep)
	elif service == 'apache':
		apache_log_path = sql.get_setting('apache_log_path')
		
		if serv == 'roxy-wi.access.log':
			cmd = "cat %s| awk -F\"/|:\" '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s %s %s" % (apache_log_path+"/"+serv, date, date1, rows, grep_act, exgrep_act)
		elif serv == 'roxy-wi.error.log':
			cmd = "cat %s| awk '$4>\"%s:00\" && $4<\"%s:00\"' |tail -%s %s %s" % (apache_log_path+"/"+serv, date, date1, rows, grep_act, exgrep_act)
		elif serv == 'fail2ban.log':
			cmd = "cat %s| awk -F\"/|:\" '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s %s %s" % ("/var/log/"+serv, date, date1, rows, grep_act, exgrep_act)

		output, stderr = subprocess_execute(cmd)
		
		return show_log(output, grep=grep)
	elif service == 'internal':
		user_group = get_user_group()

		if user_group != '' and user_group != 'All':
			user_grep = "|grep 'group: " + user_group + "'"
		else:
			user_grep = ''

		log_path = get_config_var('main', 'log_path')
		logs_files = get_files(log_path, format="log")

		for key, value in logs_files:
			if int(serv) == key:
				serv = value
				break
		else:
			print('Haha')
			sys.exit()

		if serv == 'backup.log':
			cmd = "cat %s| awk '$2>\"%s:00\" && $2<\"%s:00\"' %s %s %s |tail -%s" % (log_path + serv, date, date1, user_grep, grep_act, exgrep_act, rows)
		else:
			cmd = "cat %s| awk '$3>\"%s:00\" && $3<\"%s:00\"' %s %s %s |tail -%s" % (log_path + serv, date, date1, user_grep, grep_act, exgrep_act, rows)

		output, stderr = subprocess_execute(cmd)
		
		return show_log(output, grep=grep)
		
	
def haproxy_wi_log(**kwargs):
	log_path = get_config_var('main', 'log_path')
	
	if kwargs.get('log_id'):
		selects = get_files(log_path, format="log")
		for key, value in selects:
			if kwargs.get('with_date'):
				log_file = kwargs.get('file')+get_data('logs')+".log"
			else:
				log_file = kwargs.get('file')+".log"
			if log_file == value:
				return key
	else:
		user_group_id = get_user_group(id=1)
		if user_group_id != 1:
			user_group = get_user_group()
			group_grep = '|grep "group: ' + user_group + '"'
		else:
			group_grep = ''
		cmd = "find "+log_path+"/roxy-wi-* -type f -exec stat --format '%Y :%y %n' '{}' \; | sort -nr | cut -d: -f2- | head -1 |awk '{print $4}' |xargs tail"+group_grep+"|sort -r"
		try:
			output, stderr = subprocess_execute(cmd)
			return output
		except:
			return ''


def show_ip(stdout):
	for line in stdout:
		if "Permission denied" in line:
			print('error: '+line)
		else:
			print(line)
		
		
def server_status(stdout):	
	proc_count = ""
	
	for line in stdout:
		if "Ncat: " not in line:
			for k in line:
				try:
					proc_count = k.split(":")[1]
				except Exception:
					proc_count = 1
		else:
			proc_count = 0
	return proc_count		


def ssh_command(serv, commands, **kwargs):
	ssh = ssh_connect(serv)

	for command in commands:
		try:
			stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
		except Exception as e:
			logging('localhost', ' ' + str(e), haproxywi=1)
				
		if kwargs.get("ip") == "1":
			show_ip(stdout)
		elif kwargs.get("show_log") == "1":
			return show_log(stdout, grep=kwargs.get("grep"))
		elif kwargs.get("server_status") == "1":
			server_status(stdout)
		elif kwargs.get('print_out'):
			print(stdout.read().decode(encoding='UTF-8'))
			return stdout.read().decode(encoding='UTF-8')
		elif kwargs.get('return_err') == 1:
			return stderr.read().decode(encoding='UTF-8')
		elif kwargs.get('raw'):
			return stdout
		else:
			return stdout.read().decode(encoding='UTF-8')
			
		for line in stderr.read().decode(encoding='UTF-8'):
			if line:
				print("<div class='alert alert-warning'>"+line+"</div>")
				logging('localhost', ' '+line, haproxywi=1)

	try:
		ssh.close()
	except Exception:
		logging('localhost', ' '+str(ssh), haproxywi=1)
		return "error: "+str(ssh)


def subprocess_execute(cmd):
	import subprocess 
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
	stdout, stderr = p.communicate()
	output = stdout.splitlines()
	
	return output, stderr


def show_backends(serv, **kwargs):
	import json
	import sql
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	cmd = 'echo "show backend" |nc %s %s' % (serv, hap_sock_p)
	output, stderr = subprocess_execute(cmd)
	if stderr:
		logging('localhost', ' '+stderr, haproxywi=1)
	if kwargs.get('ret'):
		ret = list()
	else:
		ret = ""
	for line in output:
		if "#" in line or "stats" in line or "MASTER" in line:
			continue
		if len(line) > 1:
			back = json.dumps(line).split("\"")
			if kwargs.get('ret'):
				ret.append(back[1])
			else:
				print(back[1], end="<br>")
		
	if kwargs.get('ret'):
		return ret
		
		
def get_files(dir=get_config_var('configs', 'haproxy_save_configs_dir'), format='cfg', **kwargs):
	import glob
	if format == 'log':
		file = []
	else:
		file = set()
	return_files = set()
	i = 0
	for files in sorted(glob.glob(os.path.join(dir, '*.'+format))):
		if format == 'log':
			file += [(i, files.split('/')[5])]
		else:		
			file.add(files.split('/')[-1])
		i += 1
	files = file
	if format == 'cfg' or format == 'conf':
		for file in files:		
			ip = file.split("-")
			if serv == ip[0]:
				return_files.add(file)			
		return sorted(return_files, reverse=True)
	else: 
		return file
	
	
def get_key(item):
	return item[0]
	
	
def check_ver():
	import sql
	return sql.get_ver()
	
	
def check_new_version(**kwargs):
	import requests
	import sql	
	current_ver = check_ver()
	proxy = sql.get_setting('proxy')
	res = ''

	if kwargs.get('service'):
		last_ver = '_'+kwargs.get('service')
	else:
		last_ver = ''

	try:
		if proxy is not None and proxy != '' and proxy != 'None':
			proxy_dict = {"https": proxy, "http": proxy}
			response = requests.get('https://haproxy-wi.org/update.py?last_ver'+last_ver+'=1', timeout=1,  proxies=proxy_dict)
			requests.get('https://haproxy-wi.org/update.py?ver_send='+current_ver, timeout=1,  proxies=proxy_dict)
		else:
			response = requests.get('https://haproxy-wi.org/update.py?last_ver'+last_ver+'=1', timeout=1)
			requests.get('https://haproxy-wi.org/update.py?ver_send='+current_ver, timeout=1)

		res = response.content.decode(encoding='UTF-8')
	except requests.exceptions.RequestException as e:
		logging('localhost', ' '+str(e), haproxywi=1)
		
	return res
	
	
def versions():	
	try: 
		current_ver = check_ver()
		current_ver_without_dots = current_ver.split('.')
		current_ver_without_dots = ''.join(current_ver_without_dots)
		current_ver_without_dots = current_ver_without_dots.replace('\n', '')
		if len(current_ver_without_dots) == 2:
			current_ver_without_dots += '00'
		if len(current_ver_without_dots) == 3:
			current_ver_without_dots += '0'
		current_ver_without_dots = int(current_ver_without_dots)
	except Exception:
		current_ver = "Sorry cannot get current version"
		current_ver_without_dots = 0

	try:
		new_ver = check_new_version()
		new_ver_without_dots = new_ver.split('.')
		new_ver_without_dots = ''.join(new_ver_without_dots)
		new_ver_without_dots = new_ver_without_dots.replace('\n', '')
		if len(new_ver_without_dots) == 2:
			new_ver_without_dots += '00'
		if len(new_ver_without_dots) == 3:
			new_ver_without_dots += '0'
		new_ver_without_dots = int(new_ver_without_dots)
	except Exception:
		new_ver = "Cannot get a new version"
		new_ver_without_dots = 0
	
	return current_ver, new_ver, current_ver_without_dots, new_ver_without_dots
	
	
def get_hash(value):
	if value is None:
		return value
	import hashlib
	h = hashlib.md5(value.encode('utf-8'))
	p = h.hexdigest()
	return p
	
	
def out_error(error):
	error = str(error)
	try:
		logging('localhost', error, haproxywi=1, login=1)
	except Exception:
		logging('localhost', error, haproxywi=1)
	print('error: '+error)
	

def get_users_params(**kwargs):
	import http.cookies
	import sql
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	role = sql.get_user_role_by_uuid(user_id.value)
	token = sql.get_token(user_id.value)
	if kwargs.get('virt'):
		servers = sql.get_dick_permit(virt=1)
	elif kwargs.get('disable'):
		servers = sql.get_dick_permit(disable=0)
	else:
		servers = sql.get_dick_permit()
	
	return user, user_id, role, token, servers


def check_user_group(**kwargs):
	if kwargs.get('token') is not None:
		return True

	import http.cookies
	import os
	import sql
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_uuid = cookie.get('uuid')
	group = cookie.get('group')
	group_id = group.value
	user_id = sql.get_user_id_by_uuid(user_uuid.value)

	if sql.check_user_group(user_id, group_id):
		return True
	else:
		logging('localhost', ' has tried to actions in not his group ', haproxywi=1, login=1)
		print('Atata!')
		sys.exit()


def check_is_server_in_group(serv):
	import sql
	group_id = get_user_group(id=1)
	servers = sql.select_servers(server=serv)
	for s in servers:
		if (s[2] == serv and int(s[3]) == int(group_id)) or group_id == 1:
			return True
		else:
			logging('localhost', ' has tried to actions in not his group server ', haproxywi=1, login=1)
			print('Atata!')
			sys.exit()


def check_service(serv, service_name):
	commands = ["systemctl is-active "+service_name]
	return ssh_command(serv, commands)


def get_services_status():
	services = []
	services_name = {'roxy-wi-checker': 'Checker backends master service',
					 'roxy-wi-keep_alive': 'Auto start service',
					 'roxy-wi-metrics': 'Metrics master service',
					 'roxy-wi-portscanner': 'Port scanner service',
					 'roxy-wi-smon': 'Simple monitoring network ports',
					 'prometheus': 'Prometheus service',
					 'grafana-server': 'Grafana service',
					 'fail2ban': 'Fail2ban service'}
	for s, v in services_name.items():
		cmd = "systemctl is-active %s" % s
		status, stderr = subprocess_execute(cmd)
		if s != 'roxy-wi-keep_alive':
			service_name = s.split('_')[0]
			if s == 'grafana-server':
				service_name = 'grafana'
		else:
			service_name = s
		if service_name == 'prometheus':
			cmd = "prometheus --version 2>&1 |grep prometheus|awk '{print $3}'"
		else:
			cmd = "rpm --query " + service_name + "-* |awk -F\"" + service_name + "\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
		service_ver, stderr = subprocess_execute(cmd)

		try:
			services.append([s, status, v, service_ver[0]])
		except Exception:
			services.append([s, status, v, ''])

	return services


def is_file_exists(serv: str, file: str):
	cmd = ['[ -f ' + file + ' ] && echo yes || echo no']

	out = ssh_command(serv, cmd)
	return True if 'yes' in out else False


def is_service_active(serv: str, service_name: str):
	cmd = ['systemctl is-active ' + service_name]

	out = ssh_command(serv, cmd)
	return True if 'active' in out else False
