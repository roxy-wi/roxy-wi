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
	firstName = cookie.get('FirstName')
	lastName = cookie.get('LastName')
	mess = now_utc.strftime(dateFormat) + " from " + IP + " user: " + firstName.value + " " + lastName.value + " " + action + " for: " + serv + "\n"
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
	
def check_login():
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	login = cookie.get('login')
	ref = os.environ.get("SCRIPT_NAME")

	if login is None:
		print('<meta http-equiv="refresh" content="0; url=login.py?ref=%s">' % ref)
		
def show_login_links():
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	login = cookie.get('login')
	
	if login is None:
		print('<li><a href=/cgi-bin/login.py? title="Login">Login</a></li>')	
	else:
		print('<li><a href=/cgi-bin/login.py?logout=logout title="Logout">Logout</a></li>')
		
def mode_admin(button, **kwargs):
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	role = cookie.get('role')	
	level = kwargs.get("level")

	if level is None:
		level = "editor"
		
	if role.value == "admin" and level == "admin":
		print('<button type="submit">%s</button>' % button)
	elif role.value == "admin" or role.value == "editor" and level == "editor":
		print('<button type="submit">%s</button>' % button)
		
def links():
	print('<nav class="menu">'
			'<ul>'
				'<li><a href=/ title="Home Page" style="size:5">Home Page</a></li>'
				'<li><a href="#" title="Statistics, monitoring and logs">Stats</a>'
					'<ul>'
						'<li><a href=/cgi-bin/overview.py title="Server and service status">Overview</a> </li>'
						'<li><a href=/cgi-bin/viewsttats.py title="View Stats">Stats</a> </li>'
						'<li><a href="http://172.28.5.106:3000/d/000000002/haproxy?refresh=1m&orgId=1" title="Mon" target="_blanck">Monitoring</a> </li>'
						'<li><a href=/cgi-bin/logs.py title="View logs">Logs</a></li>'
					'</ul>'
				'</li>'
				'<li><a href=/cgi-bin/edit.py title="Edit settings" style="size:5">Edit settings</a> </li>'
				'<li><a href="#">Configs</a>'
					'<ul>'
						'<li><a href=/cgi-bin/configshow.py title="Show Config">Show</a></li> '
						'<li><a href=/cgi-bin/diff.py title="Compare Configs">Compare</a></li>'
						'<li><a href=/cgi-bin/add.py#listner title="Add single listen">Add listen</a></li>'
						'<li><a href=/cgi-bin/add.py#frontend title="Add single frontend">Add frontend</a></li>'
						'<li><a href=/cgi-bin/add.py#backend title="Add single backend">Add backend</a></li>'
						'<li><a href=/cgi-bin/config.py title="Edit Config" style="size:5">Edit</a> </li>'
					'</ul>'
				'</li>'
				'<li><a href="#">Versions</a>'
					'<ul>'
						'<li><a href=/cgi-bin/configver.py title="Upload old versions configs" style="size:5">Upload</a></li>'	
						'<li><a href=/cgi-bin/delver.py title="Delete old versions configs" style="size:5">Delete</a></li>'
					'</ul>'
				'</li>')
	show_login_links()
	print('</ul>'
		  '</nav>')	
	
	
def head(title):
	print('Content-type: text/html\n')
	print('<html><head><title>%s</title>' % title)
	print('<link href="/favicon.ico" rel="icon" type="image/png" />'
		'<link href="/style.css" rel="stylesheet"><meta charset="UTF-8">'
		'<link rel="stylesheet" href="http://code.jquery.com/ui/1.12.1/themes/base/jquery-ui.css">'
		'<script src="https://code.jquery.com/jquery-1.12.4.js"></script>'
		'<script src="https://code.jquery.com/ui/1.12.1/jquery-ui.js"></script>'
		'<script src="/script.js"></script>'
		'</head>'
			'<body>'
				'<a name="top"></a>'
				'<div class="top-menu">'
					'<span class="LogoText">HAproxy-WI</span>')
	if config.get('main', 'logo_enable') == "1":
		print('<img src="%s" title="Logo" class="logo">' % config.get('main', 'logo_path'))
	print('<div class="top-link">')
	links()
	print('</div></div><div class="conteiner">')

def footer():
	print('<center>'
				'<h3>'
					'<a href="#top" title="UP">UP</a>'
				'</h3>'
			'</center>'
			'</center></div>'
			'<div class="footer">'
				'<div class="footer-link">'
					'<span class="LogoText">HAproxy-WI</span>'
				'</div>'
			'</div></body></html>')

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
	print('</center><div class="configShow">')
	conf = open(cfg, "r")
	i = 0
	for line in conf:
		i = i + 1
		if not line.find("global"):
			print('<div class="param">' + line + '</div>')
			continue
		if not line.find("defaults"):
			print('<div class="param">' + line + '</div>')
			continue
		if not line.find("listen"):
			print('<div class="param">' + line + '</div>')
			continue
		if not line.find("frontend"):
			print('<div class="param">' + line + '</div>')
			continue
		if not line.find("backend"):
			print('<div class="param">' + line + '</div>')
			continue
		if "acl" in line or "option" in line or "server" in line:
			print('<div class="paramInSec"><span class="numRow">')
			print(i)
			print('</span>' + line + '</div>')
			continue
		if "#" in line:
			print('<div class="comment"><span class="numRow">')
			print(i)
			print(line + '</span></div>')
			continue			
		print('<div class="configLine"><span class="numRow">')
		print(i)
		print('</span>' + line + '</div>')					
	print('</div>')
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
	commands = [ "/sbin/haproxy  -q -c -f " + tmp_file, "mv -f " + tmp_file + " " + haproxy_config_path, restart_command]
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
	if " " not in stdout.read().decode(encoding='UTF-8'):
		print('<span class="serverUp"> UP</span> running 3 processes')
	else:
		print('<span lass="serverDown"> DOWN</span> running 0 processes')		
		
def ssh_command(serv, commands, **kwargs):
	ssh = ssh_connect(serv)
			
	for command in commands:
		try:
			stdin, stdout, stderr = ssh.exec_command(command)
		except:
			continue
				
		if kwargs.get("ip") == "1":
			show_ip(stdout)
		if kwargs.get("compare") == "1":
			compare(stdout)
		if kwargs.get("show_log") == "1":
			show_log(stdout)
		if kwargs.get("server_status") == "1":
			server_status(stdout)
		else:
			print(stdout.read().decode(encoding='UTF-8'))
			
		print(stderr.read().decode(encoding='UTF-8'))
	
def chooseServer(formName, title, note):
	print('<center><h2>' + title + '</h2>')
	print('<h3>Choose server</h3>')
	print('<form action=' + formName + ' method="get">')
	print('<p><select autofocus required name="serv" id="chooseServer">')
	print('<option disabled>Choose server</option>')

	form = cgi.FieldStorage()
	serv = form.getvalue('serv')
	servNew = form.getvalue('serNew')

	for i in sorted(listhap.listhap):
		if listhap.listhap.get(i) == serv or listhap.listhap.get(i) == servNew:
			selected = 'selected'
		else:
			selected = ''

		print('<option value="%s" %s>%s</option>' % (listhap.listhap.get(i), selected, i))

	print('</select>')
	print('<p><button type="submit" value="open" name="open">Open</button></p></form>')
	if note == "y":
		print('<p><b>Note:</b> If you reconfigure First server, second will reconfigured automatically</p>')
		
def choose_server_with_vip(serv):
	import listserv as listhap
	listhap.listhap = merge_two_dicts(listhap.listhap, listhap.list_hap_vip)
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
	
	
	
