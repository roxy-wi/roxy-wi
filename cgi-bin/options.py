#!/usr/bin/env python3
import html
import cgi
import json
import subprocess 
import funct
import ovw
from configparser import ConfigParser, ExtendedInterpolation

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)
funct.check_config()

form = cgi.FieldStorage()
req = form.getvalue('req')
serv = form.getvalue('serv')
act = form.getvalue('act')
backend = form.getvalue('backend')	
print('Content-type: text/html\n')
		
if form.getvalue('getcert') is not None and serv is not None:
	commands = [ "ls -1t /etc/ssl/certs/ |grep pem" ]
	funct.ssh_command(serv, commands, ip="1")
	
	
	
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
	commands = [ "ip a |grep inet |egrep -v  '::1' |awk '{ print $2  }' |awk -F'/' '{ print $1  }'" ]
	funct.ssh_command(serv, commands, ip="1")
	
if form.getvalue('name') is not None:
	name = form.getvalue('name')
	conf = open("/home/ploginov/haproxy/cgi-bin/hap_config/test.cfg", "r")
	s = form.getvalue('s')
	for line in conf:

		if s in line and name in line:
			print("yes")
			break

if form.getvalue('action') is not None and serv is not None:
	serv = form.getvalue('serv')
	action = form.getvalue('action')
	
	if funct.check_haproxy_config(serv):
		commands = [ "systemctl %s haproxy" % action ]
		funct.ssh_command(serv, commands)		
	else:
		print("Bad config, check please")
		
if act == "overview":
	ovw.get_overview()

if serv is not None and act == "stats":
	import requests
	from requests_toolbelt.utils import dump
	
	haproxy_user = config.get('haproxy', 'stats_user')
	haproxy_pass = config.get('haproxy', 'stats_password')
	stats_port = config.get('haproxy', 'stats_port')
	stats_page = config.get('haproxy', 'stats_page')
	try:
		response = requests.get('http://%s:%s/%s' % (serv, stats_port, stats_page), auth=(haproxy_user, haproxy_pass)) 
	except requests.exceptions.ConnectTimeout:
		print('Oops. Connection timeout occured!')
	except requests.exceptions.ReadTimeout:
		print('Oops. Read timeout occured')
	except requests.exceptions.HTTPError as errh:
		print ("Http Error:",errh)
	except requests.exceptions.ConnectionError as errc:
		print ("Error Connecting:",errc)
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

	syslog_server_enable = config.get('logs', 'syslog_server_enable')
	if syslog_server_enable is None or syslog_server_enable == "0":
		local_path_logs = config.get('logs', 'local_path_logs')
		syslog_server = serv	
		commands = [ 'sudo tail -%s %s %s %s' % (rows, local_path_logs, grep_act, grep) ]	
	else:
		commands = [ 'sudo tail -%s /var/log/%s/syslog.log %s %s' % (rows, serv, grep_act, grep) ]
		syslog_server = config.get('logs', 'syslog_server')
	print('<div id"logs">')
	funct.ssh_command(syslog_server, commands, show_log="1")
	print('</div>')

if serv is not None and act == "showMap":
	ovw.get_map(serv)
	
if form.getvalue('servaction') is not None:
	server_state_file = config.get('haproxy', 'server_state_file')
	haproxy_sock = config.get('haproxy', 'haproxy_sock')
	enable = form.getvalue('servaction')
	backend = form.getvalue('servbackend')
	
	cmd='echo "%s %s" |socat stdio %s | cut -d "," -f 1-2,5-10,34-36 | column -s, -t' % (enable, backend, haproxy_sock)
	
	if form.getvalue('save') == "on":
		save_command = 'echo "show servers state" | socat stdio %s > %s' % (haproxy_sock, server_state_file)
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
	
	hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')
	cfg = hap_configs_dir + serv + "-" + funct.get_data('config') + ".cfg"
	
	funct.get_config(serv, cfg)
	
	print('<a name="top"></a>')
	print("<center><h3>Config from %s</h3>" % serv)
	print('<p class="accordion-expand-holder">'
			'<a class="accordion-expand-all ui-button ui-widget ui-corner-all" href="#">Expand all</a>'
		'</p>')
	print('</center>')
	
	funct.show_config(cfg)

	os.system("/bin/rm -f " + cfg)	
	
if form.getvalue('viewlogs') is not None:
	viewlog = form.getvalue('viewlogs')
	log_path = config.get('main', 'log_path')
	log = open(log_path + viewlog, "r")
	print('<center><h3>Shows log: %s</h3></center><br />' % viewlog)
	i = 0
	for line in log:
		i = i + 1
		if i % 2 == 0: 
			print('<div class="line3">' + line + '</div>')
		else:
			print('<div class="line">' + line + '</div>')
	
if form.getvalue('tailf_stop') is not None:
	serv = form.getvalue('serv')
	commands = [ "ps ax |grep python3 |grep -v grep |awk '{ print $1 }' |xargs kill" ]
	funct.ssh_command(serv, commands)