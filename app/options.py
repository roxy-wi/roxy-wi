#!/usr/bin/env python3
# -*- coding: utf-8 -*-"
import html
import cgi
import os, sys
import json
import subprocess 
import funct
import sql
import ovw

form = cgi.FieldStorage()
req = form.getvalue('req')
serv = form.getvalue('serv')
act = form.getvalue('act')
backend = form.getvalue('backend')	
print('Content-type: text/html\n')
		
if form.getvalue('getcert') is not None and serv is not None:
	commands = [ "ls -1t /etc/ssl/certs/ |grep pem" ]
	try:
		funct.ssh_command(serv, commands, ip="1")
	except:
		print('<div class="alert alert-danger" style="margin:0">Can not connect to the server</div>')
		
if form.getvalue('ssh_cert'):
	ssh_keys = funct.get_config_var('ssh', 'ssh_keys')
	
	try:
		with open(ssh_keys, "w") as conf:
			conf.write(form.getvalue('ssh_cert'))
	except IOError:
		print('<div class="alert alert-danger">Can\'t save ssh keys file. Check ssh keys path in config</div>')
	else:
		print('<div class="alert alert-success">Ssh key was save into: %s </div>' % ssh_keys)
	try:
		funct.logging("local", "users.py#ssh upload new ssl cert %s" % ssh_keys)
	except:
		pass
			
if serv and form.getvalue('ssl_cert'):
	cert_local_dir = funct.get_config_var('main', 'cert_local_dir')
	cert_path = funct.get_config_var('haproxy', 'cert_path')
	
	if form.getvalue('ssl_name') is None:
		print('<div class="alert alert-danger">Please enter desired name</div>')
	else:
		name = form.getvalue('ssl_name') + '.pem'
	
	try:
		with open(name, "w") as ssl_cert:
			ssl_cert.write(form.getvalue('ssl_cert'))
	except IOError:
		print('<div class="alert alert-danger">Can\'t save ssl keys file. Check ssh keys path in config</div>')
	else:
		print('<div class="alert alert-success">SSL file was upload to %s into: %s </div>' % (serv, cert_path))
		
	MASTERS = sql.is_master(serv)
	for master in MASTERS:
		if master[0] != None:
			funct.upload(master[0], cert_path, name)
	try:
		funct.upload(serv, cert_path, name)
	except:
		pass
	
	os.system("mv %s %s" % (name, cert_local_dir))
	funct.logging(serv, "add.py#ssl upload new ssl cert %s" % name)
	
if backend is not None:
	
	cmd='echo "show backend" |nc %s 1999' % serv 
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
	stdout, stderr = p.communicate()
	output = stdout.splitlines()
	
	for line in output:
		if "#" in  line or "stats" in line:
			continue
		if backend != "1":
			if backend in line:
				print(json.dumps(line))
				continue
		if backend == "1":
			print(json.dumps(line))
			continue


if form.getvalue('ip') is not None and serv is not None:
	commands = [ "sudo ip a |grep inet |egrep -v  '::1' |awk '{ print $2  }' |awk -F'/' '{ print $1  }'" ]
	funct.ssh_command(serv, commands, ip="1")
	
if form.getvalue('showif'):
	commands = ["sudo ip link|grep 'UP' | awk '{print $2}'  |awk -F':' '{print $1}'"]
	funct.ssh_command(serv, commands, ip="1")
	
if form.getvalue('action_hap') is not None and serv is not None:
	serv = form.getvalue('serv')
	action = form.getvalue('action_hap')
	
	if funct.check_haproxy_config(serv):
		commands = [ "sudo systemctl %s haproxy" % action ]
		funct.ssh_command(serv, commands)		
	else:
		print("Bad config, check please")
		
if act == "overview":
	ovw.get_overview()

if act == "overviewServers":
	ovw.get_overviewServers()
	
if form.getvalue('action'):
	import requests
	from requests_toolbelt.utils import dump
	
	haproxy_user = funct.get_config_var('haproxy', 'stats_user')
	haproxy_pass = funct.get_config_var('haproxy', 'stats_password')
	stats_port = funct.get_config_var('haproxy', 'stats_port')
	stats_page = funct.get_config_var('haproxy', 'stats_page')
	
	postdata = {
		'action' : form.getvalue('action'),
		's' : form.getvalue('s'),
		'b' : form.getvalue('b')
	}

	headers = {
		'User-Agent' : 'Mozilla/5.0 (Windows NT 5.1; rv:20.0) Gecko/20100101 Firefox/20.0',
		'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
		'Accept-Language' : 'en-US,en;q=0.5',
		'Accept-Encoding' : 'gzip, deflate'
	}

	q = requests.post('http://'+serv+':'+stats_port+'/'+stats_page, headers=headers, data=postdata, auth=(haproxy_user, haproxy_pass))
	
if serv is not None and act == "stats":
	import requests
	from requests_toolbelt.utils import dump
	
	haproxy_user = funct.get_config_var('haproxy', 'stats_user')
	haproxy_pass = funct.get_config_var('haproxy', 'stats_password')
	stats_port = funct.get_config_var('haproxy', 'stats_port')
	stats_page = funct.get_config_var('haproxy', 'stats_page')
	try:
		response = requests.get('http://%s:%s/%s' % (serv, stats_port, stats_page), auth=(haproxy_user, haproxy_pass)) 
	except requests.exceptions.ConnectTimeout:
		print('Oops. Connection timeout occured!')
	except requests.exceptions.ReadTimeout:
		print('Oops. Read timeout occured')
	except requests.exceptions.HTTPError as errh:
		print ("Http Error:",errh)
	except requests.exceptions.ConnectionError as errc:
		print ('<div class="alert alert-danger">Error Connecting: %s</div>' % errc)
	except requests.exceptions.Timeout as errt:
		print ("Timeout Error:",errt)
	except requests.exceptions.RequestException as err:
		print ("OOps: Something Else",err)
		
	data = response.content
	print(data.decode('utf-8'))

if serv is not None and form.getvalue('rows') is not None:
	rows = form.getvalue('rows')
	grep = form.getvalue('grep')
	
	if grep is not None:
        	grep_act  = '|grep'
	else:
		grep_act = ''
		grep = ''

	syslog_server_enable = funct.get_config_var('logs', 'syslog_server_enable')
	if syslog_server_enable is None or syslog_server_enable == "0":
		local_path_logs = funct.get_config_var('logs', 'local_path_logs')
		syslog_server = serv	
		commands = [ 'sudo tail -%s %s %s %s' % (rows, local_path_logs, grep_act, grep) ]	
	else:
		commands = [ 'sudo tail -%s /var/log/%s/syslog.log %s %s' % (rows, serv, grep_act, grep) ]
		syslog_server = funct.get_config_var('logs', 'syslog_server')
	print('<div id="logs">')
	funct.ssh_command(syslog_server, commands, show_log="1")
	print('</div>')

if serv is not None and form.getvalue('rows1') is not None:
	rows = form.getvalue('rows1')
	grep = form.getvalue('grep')
	
	if grep is not None:
        	grep_act  = '|grep'
	else:
		grep_act = ''
		grep = ''
	
	cmd='tail -%s %s %s %s' % (rows, '/var/log/httpd/'+serv, grep_act, grep)
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
	stdout, stderr = p.communicate()
	output = stdout.splitlines()

	funct.show_log(output)
	print(stderr)
		
if serv is not None and act == "showMap":
	ovw.get_map(serv)
	
if form.getvalue('servaction') is not None:
	server_state_file = funct.get_config_var('haproxy', 'server_state_file')
	haproxy_sock = funct.get_config_var('haproxy', 'haproxy_sock')
	enable = form.getvalue('servaction')
	backend = form.getvalue('servbackend')
	
	cmd='echo "%s %s" |sudo socat stdio %s | cut -d "," -f 1-2,5-10,18,34-36 | column -s, -t' % (enable, backend, haproxy_sock)
	
	if form.getvalue('save') == "on":
		save_command = 'echo "show servers state" | sudo socat stdio %s > %s' % (haproxy_sock, server_state_file)
		command = [ cmd, save_command ] 
	else:
		command = [ cmd ] 
		
	if enable != "show":
			print('<center><h3>You %s %s on HAproxy %s. <a href="viewsttats.py?serv=%s" title="View stat" target="_blank">Look it</a> or <a href="edit.py" title="Edit">Edit something else</a></h3><br />' % (enable, backend, serv, serv))
			
	funct.ssh_command(serv, command, show_log="1")
	action = 'edit.py ' + enable + ' ' + backend
	funct.logging(serv, action)

if act == "showCompareConfigs":
	ovw.show_compare_configs(serv)
	
if serv is not None and form.getvalue('right') is not None:
	ovw.comapre_show()
	
if serv is not None and act == "configShow":
	import os
	from datetime import datetime
	from pytz import timezone
	hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
	
	if form.getvalue('configver') is None:	
		cfg = hap_configs_dir + serv + "-" + funct.get_data('config') + ".cfg"
		funct.get_config(serv, cfg)
	else: 
		cfg = hap_configs_dir + form.getvalue('configver')
		
	print('<a name="top"></a>')
	print("<center><h3>Config from %s</h3>" % serv)
	print('<p class="accordion-expand-holder">'
			'<a class="accordion-expand-all ui-button ui-widget ui-corner-all" href="#">Expand all</a>'
		'</p>')
	print('</center>')
	
	funct.show_config(cfg)
	
	if form.getvalue('configver') is None:
		os.system("/bin/rm -f " + cfg)	
	else:
		print('<br><center>')
		print('<form action="configver.py#conf" method="get">')
		print('<input type="hidden" value="%s" name="serv">' % serv)
		print('<input type="hidden" value="%s" name="configver">' % form.getvalue('configver'))
		print('<input type="hidden" value="1" name="config">')
		funct.get_button("Just save", value="save")
		funct.get_button("Upload and restart")
		print('</form></center>')
	
if form.getvalue('viewlogs') is not None:
	viewlog = form.getvalue('viewlogs')
	log_path = funct.get_config_var('main', 'log_path')
	
	try:
		log = open(log_path + viewlog, "r",encoding='utf-8', errors='ignore')
	except IOError:
		print('<div class="alert alert-danger">Can\'t read import log file</div>')
		sys.exit()
	
	print('<center><h3>Shows log: %s</h3></center><br />' % viewlog)
	i = 0
	for line in log:
		i = i + 1
		if i % 2 == 0: 
			print('<div class="line3">' + line + '</div>')
		else:
			print('<div class="line">' + line + '</div>')

if form.getvalue('master'):
	master = form.getvalue('master')
	slave = form.getvalue('slave')
	interface = form.getvalue('interface')
	vrrpip = form.getvalue('vrrpip')
	hap = form.getvalue('hap')
	tmp_config_path = funct.get_config_var('haproxy', 'tmp_config_path')
	script = "install_keepalived.sh"
	
	if hap == "1":
		funct.install_haproxy(master)
		funct.install_haproxy(slave)
	
	os.system("cp scripts/%s ." % script)
		
	funct.upload(master, tmp_config_path, script)
	funct.upload(slave, tmp_config_path, script)
	
	commands = [ "chmod +x "+tmp_config_path+script, tmp_config_path+script+" MASTER "+interface+" "+vrrpip ]
	funct.ssh_command(master, commands)
	
	commands = [ "chmod +x "+tmp_config_path+script, tmp_config_path+script+" BACKUP "+interface+" "+vrrpip ]
	funct.ssh_command(slave, commands)
			
	os.system("rm -f %s" % script)
	sql.update_server_master(master, slave)
	
if form.getvalue('masteradd'):
	master = form.getvalue('masteradd')
	slave = form.getvalue('slaveadd')
	interface = form.getvalue('interfaceadd')
	vrrpip = form.getvalue('vrrpipadd')
	kp = form.getvalue('kp')
	tmp_config_path = funct.get_config_var('haproxy', 'tmp_config_path')
	script = "add_vrrp.sh"
	
	os.system("cp scripts/%s ." % script)
		
	funct.upload(master, tmp_config_path, script)
	funct.upload(slave, tmp_config_path, script)
	
	commands = [ "sudo chmod +x "+tmp_config_path+script, tmp_config_path+script+" MASTER "+interface+" "+vrrpip+" "+kp]
	funct.ssh_command(master, commands)
	
	commands = [ "sudo chmod +x "+tmp_config_path+script, tmp_config_path+script+" BACKUP "+interface+" "+vrrpip+" "+kp ]
	funct.ssh_command(slave, commands)
			
	os.system("rm -f %s" % script)
	
if form.getvalue('haproxyaddserv'):
	funct.install_haproxy(form.getvalue('haproxyaddserv'))