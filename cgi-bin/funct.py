import cgi
import os
import paramiko
import http.cookies
from paramiko import SSHClient
import listserv as listhap
from datetime import datetime
from pytz import timezone
import configparser

def check_config():
	path_config = "haproxy-webintarface.config"
	config = configparser.ConfigParser()
	config.read(path_config)
		
	for section in [ 'main', 'configs', 'ssh', 'logs', 'haproxy' ]:
		if not config.has_section(section):
			print('<b style="color: red">Check config file, no %s section</b>' % section)


path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)

fullpath = config.get('main', 'fullpath')
ssh_keys = config.get('ssh', 'ssh_keys')
ssh_user_name = config.get('ssh', 'ssh_user_name')
haproxy_configs_server = config.get('configs', 'haproxy_configs_server')
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')
haproxy_config_path  = config.get('haproxy', 'haproxy_config_path')
tmp_config_path = config.get('haproxy', 'tmp_config_path')
restart_command = config.get('haproxy', 'restart_command')
time_zone = config.get('main', 'time_zone')

def logging(serv, action):
	dateFormat = "%b  %d %H:%M:%S"
	now_utc = datetime.now(timezone(time_zone))
	IP = cgi.escape(os.environ["REMOTE_ADDR"])
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	login = cookie.get('login')
	mess = now_utc.strftime(dateFormat) + " from " + IP + " user: " + login.value + " " + action + " for: " + serv + "\n"
	log = open(fullpath + "log/config_edit.log", "a")
	log.write(mess)
	log.close
	
	if config.get('telegram', 'enable') == "1": telegram_send_mess(mess)

def telegram_send_mess(mess):
	import telegram
	token_bot = config.get('telegram', 'token')
	channel_name = config.get('telegram', 'channel_name')
	proxy = config.get('telegram', 'proxy')
	
	if proxy is not None:
		pp = telegram.utils.request.Request(proxy_url=proxy)
	bot = telegram.Bot(token=token_bot, request=pp)
	bot.send_message(chat_id=channel_name, text=mess)
	
def check_login(**kwargs):
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	login = cookie.get('login')
	role = cookie.get('role')
	ref = os.environ.get("SCRIPT_NAME")
	
	if kwargs.get("admins_area") == "1" and role.value != "admin":
		print('<meta http-equiv="refresh" content="0; url=/">')
		
	if login is None:
		print('<meta http-equiv="refresh" content="0; url=login.py?ref=%s">' % ref)
		
def show_login_links():
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	login = cookie.get('login')
	
	if login is None:
		print('<li><a href=/cgi-bin/login.py? title="Login">Login</a></li>')	
	else:
		print('<li><a href=/cgi-bin/login.py?logout=logout title="Logout, user name: %s">Logout</a></li>' % login.value)
		
def is_admin():
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	role = cookie.get('role')	
	
	try:
		if role.value == "admin":
			return True
		else:
			return False
	except:
		return False
		pass
	
def mode_admin(button, **kwargs):
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	role = cookie.get('role')	
	level = kwargs.get("level")

	if level is None:
		level = "editor"
		
	if role.value == "admin" and level == "admin":
		print('<button type="submit" class="btn btn-default">%s</button>' % button)
	elif role.value == "admin" or role.value == "editor" and level == "editor":
		print('<button type="submit" class="btn btn-default">%s</button>' % button)

def head(title):
	print('Content-type: text/html\n')
	print('<html><head><title>%s</title>' % title)
	print('<link href="/favicon.ico" rel="icon" type="image/png" />'
		'<meta charset="UTF-8">'
		'<link href="/inc/style.css" rel="stylesheet">'
		'<link rel="stylesheet" href="http://code.jquery.com/ui/1.12.1/themes/base/jquery-ui.css">'
		'<script src="https://code.jquery.com/jquery-1.12.4.js"></script>'
		'<script src="https://code.jquery.com/ui/1.12.1/jquery-ui.js"></script>'
		'<script src="/inc/js-cookie.js"></script>'
		'<script src="/inc/script.js"></script>'		
		'</head>'
			'<body>'
				'<a name="top"></a>'
				'<div class="show_menu" style="display: none;">'
					'<a href="#" id="show_menu" title="Show menu" style="margin-top: 30px;position: absolute;">'
						'<span class="ui-state-default ui-corner-all">'
							'<span class="ui-icon ui-icon-arrowthick-1-e" id="arrow"></span>'
						'</span>'
					'</a>'
				'</div>'
				'<div class="top-menu">'
					'<div class="LogoText">'
						'<span style="padding: 10px;">HAproxy-WI</span>'
						'<a href="#" id="hide_menu" title="Hide menu" style="margin-left: 7px;margin-top: -6px;position: absolute;">'
							'<span class="ui-state-default ui-corner-all">'
								'<span class="ui-icon ui-icon-arrowthick-1-w" id="arrow"></span>'
							'</span>'
						'</a>'
					'</div>')
	if config.get('main', 'logo_enable') == "1":
		print('<div><img src="%s" title="Logo" class="logo"></div>' % config.get('main', 'logo_path'))
	print('<div class="top-link">')
	links()
	print('</div></div><div class="container">')
	
def links():
	print('<nav class="menu">'
			'<ul>'
				'<li><a href=/ title="Home Page" style="size:5">Home Page</a></li>'
				'<li><a href="#" title="Statistics, monitoring and logs">Stats</a>'
					'<ul>'
						'<li><a href=/cgi-bin/overview.py title="Server and service status">Overview</a> </li>'
						'<li><a href=/cgi-bin/viewsttats.py title="View Stats">Stats</a> </li>'
						'<li><a href=/cgi-bin/logs.py title="View logs">Logs</a></li>'
						'<li><a href=/cgi-bin/map.py title="View map">Map</a></li>'
					'</ul>'
				'</li>'
				'<li><a href=/cgi-bin/edit.py title="Runtime API" style="size:5">Runtime API</a> </li>'
				'<li><a href="#">Configs</a>'
					'<ul>'
						'<li><a href=/cgi-bin/configshow.py title="Show Config">Show</a></li> '
						'<li><a href=/cgi-bin/diff.py title="Compare Configs">Compare</a></li>'
						'<li><a href=/cgi-bin/add.py#listner title="Add single listen">Add listen</a></li>'
						'<li><a href=/cgi-bin/add.py#frontend title="Add single frontend">Add frontend</a></li>'
						'<li><a href=/cgi-bin/add.py#backend title="Add single backend">Add backend</a></li>'
						'<li><a href=/cgi-bin/config.py title="Edit Config">Edit</a> </li>'
					'</ul>'
				'</li>'
				'<li><a href="#">Versions</a>'
					'<ul>'
						'<li><a href=/cgi-bin/configver.py title="Upload old versions configs">Upload</a></li>')
	if is_admin():
		print('<li><a href=/cgi-bin/delver.py title="Delete old versions configs">Delete</a></li>')
	print('</ul>'
			'</li>')
	show_login_links()
	print('</ul>'
		  '</nav>')	
	
def footer():
	print('</center></div>'
			'<center style="margin-left: 12%;">'
				'<h3>'
					'<a class="ui-button ui-widget ui-corner-all" href="#top" title="Move up">UP</a>'
				'</h3><br />'
			'</center>'
			'<!--<div class="footer">'
				'<div class="footer-link">'
					'<span class="LogoText">HAproxy-WI</span>'
				'</div>'
			'</div>--></body></html>')

def ssh_connect(serv):
	ssh = SSHClient()
	ssh.load_system_host_keys()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	try:
		if config.get('ssh', 'ssh_keys_enable') == "1":
			k = paramiko.RSAKey.from_private_key_file(ssh_keys)
			ssh.connect(hostname = serv, username = ssh_user_name, pkey = k )
		else:
			ssh.connect(hostname = serv, username = ssh_user_name, password = config.get('ssh', 'ssh_pass'))
		return ssh
	except paramiko.AuthenticationException:
		print("Authentication failed, please verify your credentials: %s")
	except paramiko.SSHException as sshException:
		print("Unable to establish SSH connection: %s" % sshException)
	except paramiko.BadHostKeyException as badHostKeyException:
		print("Unable to verify server's host key: %s" % badHostKeyException)
	except Exception as e:
		print(e.args)	

def get_config(serv, cfg):
	os.chdir(hap_configs_dir)
	ssh = ssh_connect(serv)
	try:
		sftp = ssh.open_sftp()
		sftp.get(haproxy_config_path, cfg)
		sftp.close()
		ssh.close()
	except Exception as e:
		print("!!! There was an issue, " + str(e))
	
def show_config(cfg):
	print('</center><div style="margin-left: 16%" class="configShow">')
	conf = open(cfg, "r")
	i = 0
	for line in conf:
		i = i + 1
		if not line.find("global"):
			print('<span class="param">' + line + '</span><div>')
			continue
		if not line.find("defaults"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if not line.find("listen"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if not line.find("frontend"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if not line.find("backend"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if "acl" in line or "option" in line or "server" in line:
			if "timeout" not in line and "default-server" not in line and "#use_backend" not in line:
				print('<span class="paramInSec"><span class="numRow">')
				print(i)
				print('</span>' + line + '</span><br />')
				continue
		if "#" in line:
			print('<span class="comment"><span class="numRow">')
			print(i)
			print(line + '</span></span><br />')
			continue	
		if line.__len__() < 1:
			print('</div>')
		if line.__len__() > 1:
			print('<span class="configLine"><span class="numRow">')
			print(i)
			print('</span>' + line + '</span><br />')					
	print('</div></div>')
	conf.close
	
def upload_and_restart(serv, cfg):
	fmt = "%Y-%m-%d.%H:%M:%S"
	now_utc = datetime.now(timezone(config.get('main', 'time_zone')))
	tmp_file = tmp_config_path + "/" + now_utc.strftime(fmt) + ".cfg"

	ssh = ssh_connect(serv)
	print("connected<br />")
	sftp = ssh.open_sftp()
	sftp.put(cfg, tmp_file)
	sftp.close()
	commands = [ "/sbin/haproxy  -q -c -f " + tmp_file, "mv -f " + tmp_file + " " + haproxy_config_path, restart_command ]
	i = 0
	for command in commands:
		i = i + 1
		print("</br>Executing: {}".format( command ))
		print("</br>")
		stdin , stdout, stderr = ssh.exec_command(command)
		print(stdout.read().decode(encoding='UTF-8'))
		if i == 1:
			if not stderr.read():
				print('<h3 style="color: #23527c">Config ok</h3>')
			else:
				print('<h3 style="color: red">In your config have errors, please check, and try again</h3>')
				print(stderr.read().decode(encoding='UTF-8'))
				return False
				break
		if i is not 1:
			print("</br>Errors:")	
			print(stderr.read().decode(encoding='UTF-8'))
			print("</br>")
	
	return True	
			
	ssh.close()
	
def compare(stdout):
	i = 0
	minus = 0
	plus = 0
	total_change = 0
	
	print('</center><div class="out">')
	print('<div class="diff">')
		
	for line in stdout:
		i = i + 1

		if i is 1:
			print('<div class="diffHead">' + line + '<br />')
		elif i is 2:
			print(line + '</div>')
		elif line.find("-") == 0 and i is not 1:
			print('<div class="lineDiffMinus">' + line + '</div>')
			minus = minus + 1
		elif line.find("+") == 0 and i is not 2:
			print('<div class="lineDiffPlus">' + line + '</div>')	
			plus = plus + 1					
		elif line.find("@") == 0:
			print('<div class="lineDog">' + line + '</div>')
		else:
			print('<div class="lineDiff">' + line + '</div>')				
			
		total_change = minus + plus
	print('<div class="diffHead">Total change: %s, additions: %s & deletions: %s </div>' % (total_change, minus, plus))	
	print('</div></div>')
		
def show_log(stdout):
	i = 0
	for line in stdout:
		i = i + 1
		if i % 2 == 0: 
			print('<div class="line3">' + line + '</div>')
		else:
			print('<div class="line">' + line + '</div>')
			
def show_ip(stdout):
	for line in stdout:
		print(line)
		
def server_status(stdout):
	proc_count = ""
	for line in stdout.read().decode(encoding='UTF-8'):
		proc_count += line
		if "0" != line:
			err = 0
		else:
			err = 1
	if err == 0:
		print('<span class="serverUp"> UP</span> running %s processes' % proc_count)
	else:
		print('<span class="serverDown"> DOWN</span> running %s processes' % proc_count)	
	
def ssh_command(serv, commands, **kwargs):
	ssh = ssh_connect(serv)
		  
	for command in commands:
		try:
			stdin, stdout, stderr = ssh.exec_command(command)
		except:
			continue
				
		if kwargs.get("ip") == "1":
			show_ip(stdout)
		elif kwargs.get("compare") == "1":
			compare(stdout)
		elif kwargs.get("show_log") == "1":
			show_log(stdout)
		elif kwargs.get("server_status") == "1":
			server_status(stdout)
		else:
			print('<div style="margin: -10px;">'+stdout.read().decode(encoding='UTF-8')+'</div>')
			
		print(stderr.read().decode(encoding='UTF-8'))

def get_group_permit():
	import json
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	login = cookie.get('login')
	USERS = fullpath + '/cgi-bin/users'

	try:
		with open(USERS, "r") as user:
			pass
	except IOError:
		print("Can't load users DB")
		
	for f in open(USERS, 'r'):
		users = json.loads(f)
		if login.value in users['login']:
			group = users['group']
	
	GROUPS = fullpath + '/cgi-bin/groups'
	try:
		with open(GROUPS, "r") as user:
			pass
	except IOError:
		print("Can't load groups DB")
	
	for f in open(GROUPS, 'r'):
		groups = json.loads(f)
		if group in groups['name']:
			list = groups['lists']
			break
		else:
			list = ""

	return list
	
def get_dick_after_permit():
	list_serv = get_group_permit()
	
	if list_serv == "all":
		from listserv import listhap as listhap
	elif list_serv == "web":
		from listserv import web as listhap
	elif list_serv == "mysql":
		from listserv import mysql as listhap
	else:
		from listserv import no_group as listhap
	
	return listhap

def choose_only_select(serv, **kwargs):
	listhap = get_dick_after_permit()
		
	if kwargs.get("servNew"):
		servNew = kwargs.get("servNew")
	else:
		servNew = ""
		
	for i in sorted(listhap):
		if listhap.get(i) == serv or listhap.get(i) == servNew:
			selected = 'selected'
		else:
			selected = ''

		print('<option value="%s" %s>%s</option>' % (listhap.get(i), selected, i))	

def chooseServer(formName, title, note):
	print('<h2>' + title + '</h2><center>')
	print('<h3>Choose server</h3>')
	print('<form action=' + formName + ' method="get">')
	print('<p><select autofocus required name="serv" id="chooseServer">')
	print('<option disabled>Choose server</option>')

	form = cgi.FieldStorage()
	serv = form.getvalue('serv')
	servNew = form.getvalue('serNew')
	
	choose_only_select(serv, servNew=servNew)

	print('</select>')
	print('<button type="submit" value="open" name="open" class="btn btn-default">Open</button></p></form>')
	if note == "y":
		print('<p><b>Note:</b> If you reconfigure First server, second will reconfigured automatically</p>')
		
def choose_server_with_vip(serv):
	listhap.listhap = merge_two_dicts(listhap.listhap, listhap.listhap_vip)
	for i in sorted(listhap.listhap):
		if listhap.listhap.get(i) == serv:
			selected = 'selected'
		else:
			selected = ''
		print('<option value="%s" %s>%s</option>' % (listhap.listhap.get(i), selected, i))

def merge_two_dicts(x, y):
    z = x.copy()
    z.update(y)
    return z		
	
	
	
