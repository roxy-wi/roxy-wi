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
restart_command = config.get('haproxy', 'restart_command')

def logging(serv, action):
	dateFormat = "%b  %d %H:%M:%S"
	now_utc = datetime.now(timezone('Asia/Almaty'))
	IP = cgi.escape(os.environ["REMOTE_ADDR"])
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	firstName = cookie.get('FirstName')
	lastName = cookie.get('LastName')
	mess = now_utc.strftime(dateFormat) + " from " + IP + " user: " + firstName.value + " " + lastName.value + " " + action + " for: " + serv + "\n"
	log = open(fullpath + "log/config_edit.log", "a")
	log.write(mess)
	log.close

def head(title):
	print("Content-type: text/html\n")
	print('<html><head><title>%s</title>' % title)
	print('<link href="/favicon.ico" rel="icon" type="image/png" />')
	print('<link href="/style.css" rel="stylesheet"><meta charset="UTF-8"></head><body>')
	print('<a name="top"></a>')
	print('<div class="top-menu"><div class="top-link">')
	print('<a href=/ title="Home Page" style="size:5">Home Page</a> ')
	print('<a href=/cgi-bin/viewsttats.py title="View Stats" style="size:5">Stats</a> ')	
	print('<a href=/cgi-bin/edit.py title="Edit settings" style="size:5">Edit settings</a> ')
	print('<a href=/cgi-bin/logs.py title="Logs" style="size:6">Logs</a>')
	print('<span style="color: #fff">  | Configs: </span>')
	print('<a href=/cgi-bin/configshow.py title="Show Config">Show</a> ')
	print('<a href=/cgi-bin/diff.py title="Compare Configs">Compare</a> ')
	print('<a href=/cgi-bin/config.py title="Edit Config" style="size:5">Edit</a> ')
	print('<a href=/cgi-bin/configver.py title="Upload old config" style="size:5">Upload old</a>')	
	print('</div></div><div class="conteiner">')

def footer():
	print('</center></div><div class="footer"><div class="footer-link">')
	print('<a href=/ title="Home Page" style="size:5">Home Page</a> ')
	print('<a href=/cgi-bin/viewsttats.py title="View Stats" style="size:5">Stats</a> ')	
	print('<a href=/cgi-bin/edit.py title="Edit settings" style="size:5">Edit settings</a> ')
	print('<a href=/cgi-bin/logs.py title="Logs" style="size:6">Logs</a>')
	print('<span style="color: #fff">  | Configs: </span>')
	print('<a href=/cgi-bin/configshow.py title="Show Config">Show</a> ')
	print('<a href=/cgi-bin/diff.py title="Compare Configs">Compare</a> ')
	print('<a href=/cgi-bin/config.py title="Edit Config" style="size:5">Edit</a> ')
	print('<a href=/cgi-bin/configver.py title="Upload old config" style="size:5">Upload old</a>')	
	print('</div></div></body></html>')
	
def get_config(serv, cfg):
	os.chdir(hap_configs_dir)
	
	ssh = SSHClient()
	ssh.load_system_host_keys()
	k = paramiko.RSAKey.from_private_key_file(ssh_keys)
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	ssh.connect(hostname = serv, username = ssh_user_name, pkey = k )
	sftp = ssh.open_sftp()
	sftp.get(haproxy_config_path, cfg)
	sftp.close()
	ssh.close()
	
def upload_and_restart(serv, cfg):
	ssh = SSHClient()
	ssh.load_system_host_keys()
	k = paramiko.RSAKey.from_private_key_file(ssh_keys)
	ssh = paramiko.SSHClient()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	print("connecting<br />")
	ssh.connect( hostname = serv, username = ssh_user_name, pkey = k )
	print("connected<br />")
	sftp = ssh.open_sftp()
	sftp.put(cfg, haproxy_config_path)
	sftp.close()
	commands = [ "service haproxy restart" ]
	for command in commands:
		print("</br>Executing: {}".format( command ))
		print("</br>")
		stdin , stdout, stderr = ssh.exec_command(command)
		print(stdout.read().decode(encoding='UTF-8'))
		print("</br>Errors:")
		print(stderr.read().decode(encoding='UTF-8'))
		print("</br>")
	ssh.close()

def ssh_command(serv, commands):
	ssh = SSHClient()
	ssh.load_system_host_keys()
	k = paramiko.RSAKey.from_private_key_file(ssh_keys)
	ssh = paramiko.SSHClient()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	ssh.connect( hostname = serv, username = ssh_user_name, pkey = k )
	for command in commands:
		stdin , stdout, stderr = ssh.exec_command(command)
		print('<pre>')
		print(stdout.read().decode(encoding='UTF-8'))
		print('</pre>')
	ssh.close()
	
def chooseServer(formName, title, note):
	print('<center><h2>' + title + '</h2>')
	print('<h3>Choose server</h3>')
	print('<form action=' + formName + ' method="get">')
	print('<p><select autofocus required name="serv">')
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
		print('<p><b>Note:</b> If you reconfigure First server, second will reconfigured automatically</p><br />')
		
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
