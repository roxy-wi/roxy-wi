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
		path_config = get_app_dir()+"/haproxy-wi.cfg"
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
	now_utc = datetime.now(timezone(sql.get_setting('time_zone')))
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
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_uuid = cookie.get('uuid')
		login = sql.get_user_name_by_uuid(user_uuid.value)
	except:
		pass
		
	if kwargs.get('alerting') == 1:
		mess = get_data('date_in_log') + action + "\n"
		log = open(log_path + "/checker-"+get_data('logs')+".log", "a")
	elif kwargs.get('metrics') == 1:
		mess = get_data('date_in_log') + action + "\n"
		log = open(log_path + "/metrics-"+get_data('logs')+".log", "a")
	elif kwargs.get('keep_alive') == 1:
		mess = get_data('date_in_log') + action + "\n"
		log = open(log_path + "/keep_alive-"+get_data('logs')+".log", "a")
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
			
	if proxy is not None:
		apihelper.proxy = {'https': proxy}
	try:
		bot = telebot.TeleBot(token=token_bot)
		bot.send_message(chat_id=channel_name, text=mess)
	except:
		print("Fatal: Can't send message. Add Telegram chanel before use alerting at this servers group")
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
	else:
		print('<meta http-equiv="refresh" content="0; url=login.py?ref=%s">' % ref)
				
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
		
	if not is_admin(level = give_level):
		print('<center><h3 style="color: red">How did you get here?! O_o You do not have need permissions</h>')
		print('<meta http-equiv="refresh" content="5; url=/">')
		import sys
		sys.exit()
				
def ssh_connect(serv, **kwargs):
	import paramiko
	from paramiko import SSHClient
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
		
def install_haproxy(serv, **kwargs):
	import sql
	script = "install_haproxy.sh"
	tmp_config_path = sql.get_setting('tmp_config_path')
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	stats_port = sql.get_setting('stats_port')
	server_state_file = sql.get_setting('server_state_file')
	stats_user = sql.get_setting('stats_user')
	stats_password = sql.get_setting('stats_password')
	proxy = sql.get_setting('proxy')
	os.system("cp scripts/%s ." % script)
	
	proxy_serv = proxy if proxy is not None else ""
		
	commands = [ "sudo chmod +x "+tmp_config_path+script+" && " +tmp_config_path+"/"+script +" PROXY=" + proxy_serv+ 
				" SOCK_PORT="+haproxy_sock_port+" STAT_PORT="+stats_port+" STAT_FILE="+server_state_file+
				" STATS_USER="+stats_user+" STATS_PASS="+stats_password ]
	
	error = str(upload(serv, tmp_config_path, script))
	if error:
		print('error: '+error)
		
	os.system("rm -f %s" % script)
	ssh_command(serv, commands, print_out="1")
	
	if kwargs.get('syn_flood') == "1":
		syn_flood_protect(serv)
	
def syn_flood_protect(serv, **kwargs):
	import sql
	script = "syn_flood_protect.sh"
	tmp_config_path = sql.get_setting('tmp_config_path')
	
	enable = "disable" if kwargs.get('enable') == "0" else "disable"

	os.system("cp scripts/%s ." % script)
	
	commands = [ "sudo chmod +x "+tmp_config_path+script, tmp_config_path+script+ " "+enable ]
	
	error = str(upload(serv, tmp_config_path, script))
	if error:
		print('error: '+error)
	os.system("rm -f %s" % script)
	ssh_command(serv, commands, print_out="1")
	
def waf_install(serv, **kwargs):
	import sql
	script = "waf.sh"
	tmp_config_path = sql.get_setting('tmp_config_path')
	proxy = sql.get_setting('proxy')
	haproxy_dir = sql.get_setting('haproxy_dir')
	ver = check_haproxy_version(serv)

	os.system("cp scripts/%s ." % script)
	
	commands = [ "sudo chmod +x "+tmp_config_path+script+" && " +tmp_config_path+script +" PROXY=" + proxy+ 
				" HAPROXY_PATH="+haproxy_dir +" VERSION="+ver ]
	
	error = str(upload(serv, tmp_config_path, script))
	if error:
		print('error: '+error)
	os.system("rm -f %s" % script)
	
	stderr = ssh_command(serv, commands, print_out="1")
	if stderr is None:
		sql.insert_waf_metrics_enable(serv, "0")

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
		pass
	try:
		sftp = ssh.open_sftp()
		file = sftp.put(file, full_path)
		sftp.close()
		ssh.close()
	except Exception as e:
		error = e
		pass
		
	return error
	
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
		
def show_log(stdout):
	i = 0
	for line in stdout:
		i = i + 1
		line_class = "line3" if i % 2 == 0 else "line"
		print('<div class="'+line_class+'">' + escape_html(line) + '</div>')
			
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
			show_log(stdout)
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
	try:	
		ssh.close()
	except:
		print("<div class='alert alert-danger' style='margin: 0;'>"+str(ssh)+"<a title='Close' id='errorMess'><b>X</b></a></div>")
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
	ret = ""
	for line in output:
		if "#" in  line or "stats" in line:
			continue
		if line != "":
			back = json.dumps(line).split("\"")
			if kwargs.get('ret'):
				ret += back[1]
				ret += "<br />"
			else:
				print(back[1], end="<br>")
		
	if kwargs.get('ret'):
		return ret
		
def get_files(dir = get_config_var('configs', 'haproxy_save_configs_dir'), format = 'cfg', **kwargs):
	import glob
	file = set()
	return_files = set()
	
	for files in glob.glob(os.path.join(dir,'*.'+format)):				
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