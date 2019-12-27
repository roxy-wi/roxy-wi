# -*- coding: utf-8 -*-"
import cgi
import os, sys

form = cgi.FieldStorage()
serv = form.getvalue('serv')

def get_app_dir():
	d = sys.path[0]
	d = d.split('/')[-1]		
	return sys.path[0] if d == "app" else os.path.dirname(sys.path[0])	

def get_config_var(sec, var):
	from configparser import ConfigParser, ExtendedInterpolation
	try:
		path_config = "/var/www/haproxy-wi/app/haproxy-wi.cfg"
		config = ConfigParser(interpolation=ExtendedInterpolation())
		config.read(path_config)
	except:
		print('Content-type: text/html\n')
		print('<center><div class="alert alert-danger">Check the config file, whether it exists and the path. Must be: app/haproxy-webintarface.config</div>')
	try:
		return config.get(sec, var)
	except:
		print('Content-type: text/html\n')
		print('<center><div class="alert alert-danger">Check the config file. Presence section %s and parameter %s</div>' % (sec, var))
					
def get_data(type):
	from datetime import datetime
	from pytz import timezone
	import sql
	try:
		now_utc = datetime.now(timezone(sql.get_setting('time_zone')))
	except:
		now_utc = datetime.now(timezone('UTC'))
	if type == 'config':
		fmt = "%Y-%m-%d.%H:%M:%S"
	if type == 'logs':
		fmt = '%Y%m%d'
	if type == "date_in_log":
		fmt = "%b %d %H:%M:%S"
		
	return now_utc.strftime(fmt)
			
def logging(serv, action, **kwargs):
	import sql
	import http.cookies
	log_path = get_config_var('main', 'log_path')
	login = ''
	
	if not os.path.exists(log_path):
		os.makedirs(log_path)
		
	try:
		IP = cgi.escape(os.environ["REMOTE_ADDR"])
	except:
		IP = ''
	try:
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_uuid = cookie.get('uuid')
		login = sql.get_user_name_by_uuid(user_uuid.value)
	except:	
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
	elif kwargs.get('haproxywi') == 1:
		if kwargs.get('login'):
			mess = get_data('date_in_log') + " from " + IP + " user: " + login + " " + action + " for: " + serv + "\n"
		else:
			mess = get_data('date_in_log') + action + "\n"
		log = open(log_path + "/haproxy-wi-"+get_data('logs')+".log", "a")
	else:
		mess = get_data('date_in_log') + " from " + IP + " user: " + login + " " + action + " for: " + serv + "\n"
		log = open(log_path + "/config_edit-"+get_data('logs')+".log", "a")
	try:	
		log.write(mess)
		log.close
	except IOError as e:
		print('<center><div class="alert alert-danger">Can\'t write log. Please check log_path in config %e</div></center>' % e)
		pass
	
def telegram_send_mess(mess, **kwargs):
	import telebot
	from telebot import apihelper
	import sql
	
	telegrams = sql.get_telegram_by_ip(kwargs.get('ip'))
	proxy = sql.get_setting('proxy')
	
	for telegram in telegrams:
		token_bot = telegram[1]
		channel_name = telegram[2]
			
	if proxy is not None and proxy != '' and proxy != 'None':
		apihelper.proxy = {'https': proxy}
	try:
		bot = telebot.TeleBot(token=token_bot)
		bot.send_message(chat_id=channel_name, text=mess)
	except:
		mess = " Fatal: Can't send message. Add Telegram chanel before use alerting at this servers group"
		print(mess)
		logging('localhost', mess, haproxywi=1)
		sys.exit()
	
def check_login(**kwargs):
	import sql
	import http.cookies
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_uuid = cookie.get('uuid')
	ref = os.environ.get("SCRIPT_NAME")

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
	except:
		role = 3
		pass
	level = kwargs.get("level")
		
	if level is None:
		level = 1
		
	try:
		return True if role <= level else False
	except:
		return False
		pass

def page_for_admin(**kwargs):
	give_level = 1
	give_level = kwargs.get("level")
		
	if not is_admin(level=give_level):
		print('<center><h3 style="color: red">How did you get here?! O_o You do not have need permissions</h>')
		print('<meta http-equiv="refresh" content="5; url=/">')
		import sys
		sys.exit()	
	
	
def return_ssh_keys_path(serv):
	import sql
	fullpath = get_config_var('main', 'fullpath')
	ssh_enable = ''
	ssh_port = ''
	ssh_user_name = ''
	ssh_user_password = ''
	
	for sshs in sql.select_ssh(serv=serv):
		ssh_enable = sshs[3]
		ssh_user_name = sshs[4]
		ssh_user_password = sshs[5]
		ssh_key_name = fullpath+'/keys/%s.pem' % sshs[2]
		
	return ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name
	
				
def ssh_connect(serv, **kwargs):
	import paramiko
	from paramiko import SSHClient
	import sql
	
	ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = return_ssh_keys_path(serv)

	servers = sql.select_servers(server=serv)
	for server in servers:
		ssh_port = server[10]

	ssh = SSHClient()
	ssh.load_system_host_keys()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	try:
		if ssh_enable == 1:
			k = paramiko.RSAKey.from_private_key_file(ssh_key_name)
			ssh.connect(hostname = serv, port =  ssh_port, username = ssh_user_name, pkey = k)
		else:
			ssh.connect(hostname = serv, port =  ssh_port, username = ssh_user_name, password = ssh_user_password)
		return ssh
	except paramiko.AuthenticationException:
		return 'Authentication failed, please verify your credentials'
		pass
	except paramiko.SSHException as sshException:
		return 'Unable to establish SSH connection: %s ' % sshException
		pass
	except paramiko.BadHostKeyException as badHostKeyException:
		return 'Unable to verify server\'s host key: %s ' % badHostKeyException
		pass
	except Exception as e:
		if e == "No such file or directory":
			return '%s. Check ssh key' % e
			pass
		elif e == "Invalid argument":
			error = 'Check the IP of the server'
			pass
		else:
			error = e	
			pass
		return str(error)

def get_config(serv, cfg, **kwargs):
	import sql

	config_path = "/etc/keepalived/keepalived.conf" if kwargs.get("keepalived") else sql.get_setting('haproxy_config_path')	
	ssh = ssh_connect(serv)
	try:
		sftp = ssh.open_sftp()
		sftp.get(config_path, cfg)
		sftp.close()
		ssh.close()
	except Exception as e:
		ssh = str(e)
		logging('localhost', ssh, haproxywi=1)
		return ssh
	
def diff_config(oldcfg, cfg):
	log_path = get_config_var('main', 'log_path')
	diff = ""
	date = get_data('date_in_log') 
	cmd="/bin/diff -ub %s %s" % (oldcfg, cfg)
	
	output, stderr = subprocess_execute(cmd)
	
	for line in output:
		diff += date + " " + line + "\n"
	try:		
		log = open(log_path + "/config_edit-"+get_data('logs')+".log", "a")
		log.write(diff)
		log.close
	except IOError:
		print('<center><div class="alert alert-danger">Can\'t read write change to log. %s</div></center>' % stderr)
		pass
		
		
def get_sections(config):
	record = False
	return_config = list()
	with open(config, 'r') as f:
		for line in f:		
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
				line.startswith('userlist')
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
			if line.startswith(section):
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
					line.startswith('userlist')
					):
						record = False
						end_line = index
						end_line = end_line - 1
				else:
					return_config += line
		
	if end_line == "":
		f = open (config,"r" )
		lineList = f.readlines()
		end_line = len(lineList)
			
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

	
def install_haproxy(serv, **kwargs):
	import sql
	script = "install_haproxy.sh"
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	stats_port = sql.get_setting('stats_port')
	server_state_file = sql.get_setting('server_state_file')
	stats_user = sql.get_setting('stats_user')
	stats_password = sql.get_setting('stats_password')
	proxy = sql.get_setting('proxy')
	hapver = kwargs.get('hapver')
	ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = return_ssh_keys_path(serv)
	
	if ssh_enable == 0:
		ssh_key_name = ''
		
	os.system("cp scripts/%s ." % script)
	
	if hapver is None:
		hapver = '2.0.7-1'
	
	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy 
	else:
		proxy_serv = ''
		
	syn_flood_protect = '1' if kwargs.get('syn_flood') == "1" else ''
		
	commands = [ "chmod +x "+script +" &&  ./"+script +" PROXY=" + proxy_serv+ 
				" SOCK_PORT="+haproxy_sock_port+" STAT_PORT="+stats_port+" STAT_FILE="+server_state_file+
				" STATS_USER="+stats_user+" STATS_PASS="+stats_password+" HAPVER="+hapver +" SYN_FLOOD="+syn_flood_protect+" HOST="+serv+
				" USER="+ssh_user_name+" PASS="+ssh_user_password+" KEY="+ssh_key_name ]
				
	output, error = subprocess_execute(commands[0])
	
	if error:
		logging('localhost', error, haproxywi=1)
		print('error: '+error)
	else:
		for l in output:
			if "msg" in l or "FAILED" in l:
				try:
					l = l.split(':')[1]
					l = l.split('"')[1]
					print(l+"<br>")
					break
				except:
					print(output)
					break
		else:
			print('success: HAProxy was installed<br>')
			
	os.system("rm -f %s" % script)
	
	
def waf_install(serv, **kwargs):
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
	
	commands = [ "sudo chmod +x "+tmp_config_path+script+" && " +tmp_config_path+script +" PROXY=" + proxy_serv+ 
				" HAPROXY_PATH="+haproxy_dir +" VERSION="+ver ]
	
	error = str(upload(serv, tmp_config_path, script))
	if error:
		print('error: '+error)
		logging('localhost', error, haproxywi=1)
	os.system("rm -f %s" % script)
	
	stderr = ssh_command(serv, commands, print_out="1")
	if stderr is None:
		sql.insert_waf_metrics_enable(serv, "0")
		
		
def update_haproxy_wi():
	cmd = 'sudo -S yum  -y update haproxy-wi'
	output, stderr = subprocess_execute(cmd)
	print(output)
	print(stderr)
	

def check_haproxy_version(serv):
	import sql
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	ver = ""
	cmd="echo 'show info' |nc %s %s |grep Version |awk '{print $2}'" % (serv, haproxy_sock_port)
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
		error = e
		logging('localhost', str(e.args[0]), haproxywi=1)
		pass
		
	try:
		sftp = ssh.open_sftp()
	except Exception as e:
		logging('localhost', str(e.args[0]), haproxywi=1)
		
	try:
		file = sftp.put(file, full_path)
	except Exception as e:
		logging('localhost', ' Cannot upload '+file+' to '+full_path+'. Error: '+str(e.args), haproxywi=1)
		pass
		
	try:
		sftp.close()
		ssh.close()
	except Exception as e:
		error = e.args
		logging('localhost', str(error[0]), haproxywi=1)
		pass

	return str(error)
	
	
def upload_and_restart(serv, cfg, **kwargs):
	import sql
	tmp_file = sql.get_setting('tmp_config_path') + "/" + get_data('config') + ".cfg"
	error = ""

	try:
		os.system("dos2unix "+cfg)
	except OSError:
		return 'Please install dos2unix' 
		pass
	
	if kwargs.get("keepalived") == 1:
		if kwargs.get("just_save") == "save":
			commands = [ "sudo mv -f " + tmp_file + " /etc/keepalived/keepalived.conf" ]
		else:
			commands = [ "sudo mv -f " + tmp_file + " /etc/keepalived/keepalived.conf && sudo systemctl restart keepalived" ]
	else:
		if kwargs.get("just_save") == "test":
			commands = [ "sudo haproxy  -q -c -f " + tmp_file + "&& sudo rm -f " + tmp_file ]
		elif kwargs.get("just_save") == "save":
			commands = [ "sudo haproxy  -q -c -f " + tmp_file + "&& sudo mv -f " + tmp_file + " " + sql.get_setting('haproxy_config_path') ]
		elif kwargs.get("just_save") == "reload":
			commands = [ "sudo haproxy  -q -c -f " + tmp_file + "&& sudo mv -f " + tmp_file + " " + sql.get_setting('haproxy_config_path') + " && sudo " + sql.get_setting('reload_command') ]	
		else:
			commands = [ "sudo haproxy  -q -c -f " + tmp_file + "&& sudo mv -f " + tmp_file + " " + sql.get_setting('haproxy_config_path') + " && sudo " + sql.get_setting('restart_command') ]	
		if sql.get_setting('firewall_enable') == "1":
			commands.extend(open_port_firewalld(cfg))
	error += str(upload(serv, tmp_file, cfg, dir='fullpath'))

	try:
		error += ssh_command(serv, commands)
	except Exception as e:
		error += e
	if error:
		logging('localhost', error, haproxywi=1)
	
	return error
		
		
def master_slave_upload_and_restart(serv, cfg, just_save):
	import sql
	MASTERS = sql.is_master(serv)
	error = ""
	for master in MASTERS:
		if master[0] != None:
			error += upload_and_restart(master[0], cfg, just_save=just_save)
		
	error += upload_and_restart(serv, cfg, just_save=just_save)
	return error
	
		
def open_port_firewalld(cfg):
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Can\'t read export config file</div>')
	
	firewalld_commands = []
	
	for line in conf:
		if "bind" in line:
			bind = line.split(":")
			bind[1] = bind[1].strip(' ')
			bind = bind[1].split("ssl")
			bind = bind[0].strip(' \t\n\r')
			firewalld_commands.append('sudo firewall-cmd --zone=public --add-port=%s/tcp --permanent' % bind)
				
	firewalld_commands.append('sudo firewall-cmd --reload')
	return firewalld_commands
	
	
def check_haproxy_config(serv):
	import sql
	commands = [ "haproxy  -q -c -f %s" % sql.get_setting('haproxy_config_path') ]
	ssh = ssh_connect(serv)
	for command in commands:
		stdin , stdout, stderr = ssh.exec_command(command, get_pty=True)
		if not stderr.read():
			return True
		else:
			return False
	ssh.close()
		
		
def show_log(stdout, **kwargs):
	i = 0
	out = ''
	for line in stdout:		
		if kwargs.get("html") != 0:
			i = i + 1
			line_class = "line3" if i % 2 == 0 else "line"
			out += '<div class="'+line_class+'">' + escape_html(line) + '</div>'
		else:
			out += line
		
	return out
		
		
def show_haproxy_log(serv, rows=10, waf='0', grep=None, hour='00', minut='00', hour1='24', minut1='00', **kwargs):
	import sql
	date = hour+':'+minut
	date1 = hour1+':'+minut1
	if grep is not None:
        	grep_act  = '|grep'
	else:
		grep_act = ''
		grep = ''

	syslog_server_enable = sql.get_setting('syslog_server_enable')
	if syslog_server_enable is None or syslog_server_enable == "0":
		local_path_logs = sql.get_setting('local_path_logs')
		syslog_server = serv	
		commands = [ "sudo cat %s| awk '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s  %s %s" % (local_path_logs, date, date1, rows, grep_act, grep) ]		
	else:
		commands = [ "sudo cat /var/log/%s/syslog.log | sed '/ %s:00/,/ %s:00/! d' |tail -%s  %s %s" % (serv, date, date1, rows, grep_act, grep) ]
		syslog_server = sql.get_setting('syslog_server')
	
	if waf == "1":
		local_path_logs = '/var/log/modsec_audit.log'
		commands = [ "sudo cat %s |tail -%s  %s %s" % (local_path_logs, rows, grep_act, grep) ]	
		
	
	if kwargs.get('html') == 0:
		a = ssh_command(syslog_server, commands)
		return show_log(a, html=0)	
	else:
		return ssh_command(syslog_server, commands, show_log='1')

	
def haproxy_wi_log():
	log_path = get_config_var('main', 'log_path')
	cmd = "find "+log_path+"/haproxy-wi-* -type f -exec stat --format '%Y :%y %n' '{}' \; | sort -nr | cut -d: -f2- | head -1 |awk '{print $4}' |xargs tail|sort -r"
	output, stderr = subprocess_execute(cmd)

	return output
			
			
def show_ip(stdout):
	for line in stdout:
		print(line)
		
		
def server_status(stdout):	
	proc_count = ""
	
	for line in stdout:
		if "Ncat: " not in line:
			for k in line:
				proc_count = k.split(":")[1]
		else:
			proc_count = 0
	return proc_count		


def ssh_command(serv, commands, **kwargs):
	ssh = ssh_connect(serv)
		  
	for command in commands:
		try:
			stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
		except:
			continue
				
		if kwargs.get("ip") == "1":
			show_ip(stdout)
		elif kwargs.get("show_log") == "1":
			return show_log(stdout)
		elif kwargs.get("server_status") == "1":
			server_status(stdout)
		elif kwargs.get('print_out'):
			print(stdout.read().decode(encoding='UTF-8'))
			return stdout.read().decode(encoding='UTF-8')
		elif kwargs.get('retunr_err') == 1:
			return stderr.read().decode(encoding='UTF-8')
		else:
			return stdout.read().decode(encoding='UTF-8')
			
		for line in stderr.read().decode(encoding='UTF-8'):
			if line:
				print("<div class='alert alert-warning'>"+line+"</div>")
				logging('localhost', ' '+line, haproxywi=1)
	try:	
		ssh.close()
	except:
		logging('localhost', ' '+str(ssh), haproxywi=1)
		return "<div class='alert alert-danger' style='margin: 0;'>"+str(ssh)+"<a title='Close' id='errorMess'><b>X</b></a></div>"
		pass


def escape_html(text):
	return cgi.escape(text, quote=True)
	
	
def subprocess_execute(cmd):
	import subprocess 
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
	stdout, stderr = p.communicate()
	output = stdout.splitlines()
	
	return output, stderr


def show_backends(serv, **kwargs):
	import json
	import sql
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	cmd='echo "show backend" |nc %s %s' % (serv, haproxy_sock_port)
	output, stderr = subprocess_execute(cmd)
	if stderr:
		logging('localhost', ' '+stderr, haproxywi=1)
	if kwargs.get('ret'):
		ret = list()
	else:
		ret = ""
	for line in output:
		if "#" in  line or "stats" in line or "MASTER" in line:
			continue
		if len(line) > 1:
			back = json.dumps(line).split("\"")
			if kwargs.get('ret'):
				ret.append(back[1])
			else:
				print(back[1], end="<br>")
		
	if kwargs.get('ret'):
		return ret
		
		
def get_files(dir = get_config_var('configs', 'haproxy_save_configs_dir'), format = 'cfg', **kwargs):
	import glob
	if format == 'log':
		file = []
	else:
		file = set()
	return_files = set()
	
	for files in glob.glob(os.path.join(dir,'*.'+format)):	
		if format == 'log':
			file += [(files.split('/')[5], files.split('/')[5])]
		else:
			file.add(files.split('/')[-1])
	files = sorted(file, reverse=True)

	if format == 'cfg':
		for file in files:
			ip = file.split("-")
			if serv == ip[0]:
				return_files.add(file)
		return sorted(return_files, reverse=True)
	else: 
		return files
	
	
def get_key(item):
	return item[0]
	
	
def check_ver():
	import sql
	return sql.get_ver()
	
	
def check_new_version():
	import requests
	import sql	

	proxy = sql.get_setting('proxy')
	
	try:
		if proxy is not None and proxy != '' and proxy != 'None':
			proxyDict = { "https" : proxy, "http" : proxy }
			response = requests.get('https://haproxy-wi.org/update.py?last_ver=1', timeout=1,  proxies=proxyDict)
		else:	
			response = requests.get('https://haproxy-wi.org/update.py?last_ver=1', timeout=1)
		
		res = response.content.decode(encoding='UTF-8')
	except requests.exceptions.RequestException as e:
		e = str(e)
		logging('localhost', ' '+e, haproxywi=1)
		
	return res
	
	
def versions():	
	try: 
		current_ver = check_ver()
		current_ver_without_dots = current_ver.split('.')
		current_ver_without_dots = ''.join(current_ver_without_dots)
		current_ver_without_dots = current_ver_without_dots.replace('\n', '')
		if len(current_ver_without_dots)  == 2:
			current_ver_without_dots += '00'
		if len(current_ver_without_dots) == 3:
			current_ver_without_dots += '0'
		current_ver_without_dots = int(current_ver_without_dots)
	except:
		current_ver = "Sorry cannot get current version"
		current_ver_without_dots = 0

	try:
		new_ver = check_new_version()
		new_ver_without_dots = new_ver.split('.')
		new_ver_without_dots = ''.join(new_ver_without_dots)
		new_ver_without_dots = new_ver_without_dots.replace('\n', '')
		if len(new_ver_without_dots)  == 2:
			new_ver_without_dots += '00'
		if len(new_ver_without_dots) == 3:
			new_ver_without_dots += '0'
		new_ver_without_dots = int(new_ver_without_dots)
	except:
		new_ver = "Sorry cannot get new version"
		new_ver_without_dots = 0
	
	return current_ver, new_ver, current_ver_without_dots, new_ver_without_dots
	
	
def get_hash(value):
	if value is None:
		return value
	import hashlib
	h = hashlib.md5(value.encode('utf-8'))
	p = h.hexdigest()
	return p
