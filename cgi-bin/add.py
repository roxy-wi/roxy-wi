#!/usr/bin/env python3
import html
import cgi
import listserv as listhap
import os
import funct
import paramiko
import configparser
import http.cookies
from paramiko import SSHClient
from datetime import datetime
from pytz import timezone

funct.head("Add")
funct.check_config()
funct.check_login("add.py")

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)

haproxy_configs_server = config.get('configs', 'haproxy_configs_server')
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')
form = cgi.FieldStorage()

if form.getvalue('mode') is not None: 
	serv = form.getvalue('serv')
	port = form.getvalue('port')
	mode = "    mode " + form.getvalue('mode')
	
	if form.getvalue('balance')	 is not None:
		balance = "    balance " + form.getvalue('balance')	+ "\n"
	else:
		balance = ""
	
	if form.getvalue('ip') is not None:
		ip = form.getvalue('ip')
	else:
		ip = ""
	
	if form.getvalue('listner') is not None:
		name = "listen " + form.getvalue('listner')
		backend = ""
	elif form.getvalue('frontend') is not None:
		name = "\nfrontend " + form.getvalue('frontend')
		backend = "    default_backend " + form.getvalue('backend') + "\n"
	elif form.getvalue('backend') is not None: 
		name = "backend " + form.getvalue('backend')
		backend = ""
				
	if not ip and form.getvalue('port') is not None:
		bind = "    bind *:"+ port + "\n" 
	elif port is not None:
		bind = "    bind " + ip + ":" + port + "\n"
	else:
		bind = ""

	if form.getvalue('option') is not None:
		options = form.getvalue('option')
		i = options.split("\n")
		options_split = ""
		for j in i:	
			options_split += "    " + j + "\n"
	else:
		options_split = ""
		
	if form.getvalue('servers') is not None:	
		servers = form.getvalue('servers')
		i = servers.split("\n")
		servers_split = ""
		for j in i:	
			servers_split += "    " + j + "\n"
	else:
		servers_split = ""
	
	config_add = name + "\n" + bind +  mode  + "\n" + balance + options_split + backend + servers_split + "\n"

	os.chdir(config.get('configs', 'haproxy_save_configs_dir'))
	
	fmt = "%Y-%m-%d.%H:%M:%S"
	now_utc = datetime.now(timezone(config.get('main', 'time_zone')))
	cfg = hap_configs_dir + serv + "-" + now_utc.strftime(fmt) + ".cfg"
	
	funct.get_config(serv, cfg)
	try:
		with open(cfg, "a") as conf:
			conf.write(config_add)			
			#print('<meta http-equiv="refresh" content="50; url=add.py?add=%s&conf=%s">' % (name, config_add))
	except IOError:
		print("Can't read import config file")
	
	funct.logging(serv, "add.py add new %s" % name)
	print('<div class="line3">')
	if funct.upload_and_restart(serv, cfg):
		print('<meta http-equiv="refresh" content="30; url=add.py?add=%s&conf=%s">' % (name, config_add))
		
	print('</div>')
	
if form.getvalue('add') is not None:
	print('<h3 class="addSuc">  ' + form.getvalue('add') + ' was successfully added</h3>')
	print('<div class="line3">')
	print(form.getvalue('conf'))
	print('</div>')
	
print('<div id="tabs">'
			'<ul>'
				'<li><a href="#listner">Listner</a></li>'
				'<li><a href="#frontend">Frontend</a></li>'
				'<li><a href="#backend">Backend</a></li>'
			'</ul>'
			'<div id="listner">'
				'<form name="add-listner" action="add.py">'
					'<table>'
							'<caption>Add listner</caption>'
								'<tr>'
									'<td class="addName">Select server: </td>'
									'<td class="addOption">'
										'<select required name="serv" id="serv">'
											'<option disabled selected>Choose server</option>')

for i in sorted(listhap.listhap):
	print('<option value="%s">%s</option>' % (listhap.listhap.get(i), i))
	
print('</select>'
				'</td>'
			'</tr>'
		'<tr>'
			'<td class="addName">Name:</td>'
			'<td class="addOption">'
				'<input type="text" name="listner" id="name" required title="Name Listner" placeholder="web_80">'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">IP and Port:</td>'
			'<td class="addOption">'
				'<input type="text" name="ip" id="ip" title="" size="15" placeholder="172.28.0.1"><b>:</b>'
				'<input type="text" name="port" required title="Port for bind listner" size="5" placeholder="8080">'
				'<div class="tooltip tooltipTop">IP for bind listner, if empty will be assignet on all IPs. Start typing ip, or press down.</div>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Mode: </td>'
			'<td class="addOption">'
				'<select required name="mode">'
					'<option value="http" selected>http</option>'
					'<option value="tcp">tcp</option>'
				'</select>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Balance: </td>'
			'<td class="addOption">'
				'<select required name="balance">'
					'<option value="roundrobin" selected>roundrobin</option>'
					'<option value="source">source</option>'
					'<option value="leastconn">leastconn</option>'
					'<option value="first">first</option>'
					'<option value="rdp-cookie">rdp-cookie</option>'
				'</select>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Optinons:</td>'
			'<td class="addOption">'
				'<div class="tooltip">'
					'<span style="padding-right: 10px;">Start typing options: </span>'
					'<input type="text" id="options" >'
					'<span style="padding-left: 10px;">'
						'or press down. <a href="http://cbonte.github.io/haproxy-dconv/1.7/configuration.html" target="_blanck" style="color: #23527c" title="HAproxy docs">Read more about options</a>'
					'</span>'
				'</div>'
				'<textarea name="option" title="Options thru" id="optionsInput" cols=80 placeholder="acl test hdr_beg(host) -i some_host"></textarea>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Servers:</td>'
			'<td class="addOption">'
				'<textarea name="servers" required title="Backend servers" cols=80 placeholder="server server.local 172.28.0.1:8080 check"></textarea>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addButton">')
funct.mode_admin("Add Listner")
print('</td>'
		'</tr>'
		'</form>'
		'</table></div>'
		
		'<!-- Second tabs -->'
		
		'<div id="frontend">'
			'<form name="add-frontend" action="add.py">'
				'<table>'
					'<caption>Add frontend</caption>'
						'<tr>'
							'<td class="addName">Select server: </td>'
							'<td class="addOption">'
								'<select required name="serv" id="serv2">'
									'<option disabled selected>Choose server</option>')

for i in sorted(listhap.listhap):
	print('<option value="%s">%s</option>' % (listhap.listhap.get(i), i))
	
print('</select>'
				'</td>'
			'</tr>'
		'<tr>'
			'<td class="addName">Name:</td>'
			'<td class="addOption">'
				'<input type="text" name="frontend" id="frontend" required title="Name frontend"  placeholder="web_80" >'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">IP and Port:</td>'
			'<td class="addOption">'
				'<input type="text" name="ip" id="ip1" size="15" placeholder="172.28.0.1"><b>:</b>'
				'<input type="text" name="port" required title="Port for bind listner" size="5" placeholder="8080">'
				'<div class="tooltip tooltipTop">IP for bind listner, if empty will be assignet on all IPs. Start typing ip, or press down.</div>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Mode: </td>'
			'<td class="addOption">'
				'<select required name="mode">'
					'<option value="http" selected>http</option>'
					'<option value="tcp">tcp</option>'
				'</select>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Optinons:</td>'
			'<td class="addOption">'
				'<div style="font-size: 12px; padding-bottom: 10px;">'
					'<span style="padding-right: 10px;">Start typing options: </span>'
					'<input type="text" id="options1" >'
					'<span style="padding-left: 10px;">'
						'or press down. <a href="http://cbonte.github.io/haproxy-dconv/1.7/configuration.html" target="_blanck"  style="color: #23527c" title="HAproxy docs">Read more about options</a>'
					'</span>'
				'</div>'
				'<textarea name="option" title="Options thru" cols=80 id="optionsInput1" placeholder="acl test hdr_beg(host) -i some_host"></textarea>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Default backend</td>'
			'<td class="addOption">'
				'<div style="font-size: 12px; padding-bottom: 10px;">Start typing backend, or press down</div>'
				'<input  name="backend" id="backends" required size="30" placeholder="some_backend">'
				'<span style="font-size: 12px; padding-left: 10px;"> .</span>'
				'<p style="font-size: 12px"><b>Note:</b> If backend don\'t exist, you must <a href="#" style="color: #23527c"  title="Create backend" id="redirectBackend">create backend first</a>.</p>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addButton">')
funct.mode_admin("Add Frontend")
print('</td>'
		'</tr>'
		'</form></table>'
		'</div>'
		
		
				'<!-- Third tabs -->'
		
		'<div id="backend">'
			'<form name="add-backend" action="add.py">'
				'<table>'
					'<caption>Add frontend</caption>'
						'<tr>'
							'<td class="addName">Select server: </td>'
							'<td class="addOption">'
								'<select required name="serv">'
									'<option disabled selected>Choose server</option>')

for i in sorted(listhap.listhap):
	print('<option value="%s">%s</option>' % (listhap.listhap.get(i), i))
	
print('</select>'
				'</td>'
			'</tr>'
		'<tr>'
			'<td class="addName">Name:</td>'
			'<td class="addOption">'
				'<input type="text" name="backend" id="backend" required title="Name backend"  placeholder="web_80" >'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Mode: </td>'
			'<td class="addOption">'
				'<select required name="mode">'
					'<option value="http" selected>http</option>'
					'<option value="tcp">tcp</option>'
				'</select>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Balance: </td>'
			'<td class="addOption">'
				'<select required name="balance">'
					'<option value="roundrobin" selected>roundrobin</option>'
					'<option value="source">source</option>'
					'<option value="leastconn">leastconn</option>'
					'<option value="first">first</option>'
					'<option value="rdp-cookie">rdp-cookie</option>'
				'</select>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Optinons:</td>'
			'<td class="addOption">'
				'<div style="font-size: 12px; padding-bottom: 10px;">'
					'<span style="padding-right: 10px;">Start typing options: </span>'
					'<input type="text" id="options2" >'
					'<span style="padding-left: 10px;">'
						'or press down. <a href="http://cbonte.github.io/haproxy-dconv/1.7/configuration.html" target="_blanck" style="color: #23527c" title="HAproxy docs">Read more about options</a>'
					'</span>'
				'</div>'
				'<textarea name="option" title="Options thru" cols=80 id="optionsInput2" placeholder="acl test hdr_beg(host) -i some_host"></textarea>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Servers:</td>'
			'<td class="addOption">'
				'<textarea name="servers" title="Backend servers" required cols=80 placeholder="server server.local 172.28.0.1:8080 check"></textarea>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addButton">')
funct.mode_admin("Add Backend")
print('</td>'
		'</tr>'
		'</form></div></table>'
		
		'</div></div>')
				
funct.footer()