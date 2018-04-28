#!/usr/bin/env python3
import html
import cgi
import os
import funct
import sql
from configparser import ConfigParser, ExtendedInterpolation

funct.head("Add")
funct.check_config()
funct.check_login()

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)
funct.page_for_admin(level = 2)

hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')
cert_path = config.get('haproxy', 'cert_path')
listhap = sql.get_dick_permit()
form 	= cgi.FieldStorage()

if form.getvalue('mode') is not None: 
	serv = form.getvalue('serv')
	port = form.getvalue('port')
	mode = "    mode " + form.getvalue('mode')
	ssl = ""
	
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
				
	if form.getvalue('ssl') == "https" and form.getvalue('mode') != "tcp":
		ssl = "ssl crt " + cert_path + form.getvalue('cert')
		if form.getvalue('ssl-check') == "ssl-check":
			ssl_check = " ssl verify none"
		else:
			ssl_check = " ssl verify"
	else:
		ssl_check = ""
		
	
		
	if not ip and form.getvalue('port') is not None:
		bind = "    bind *:"+ port + " " + ssl + "\n" 
	elif port is not None:
		bind = "    bind " + ip + ":" + port + " " + ssl + "\n"
	else:
		bind = ""
		
	if form.getvalue('default-check') == "1":
		if form.getvalue('check-servers') == "1":
			check = " check inter " + form.getvalue('inter') + " rise " + form.getvalue('rise') + " fall " + form.getvalue('fall') + ssl_check
		else:
			check = ""
	else:
		if form.getvalue('check-servers') != "1":
			check = ""
		else:
			check = " check" + ssl_check
		
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
			j = j.strip('\t\n\r')
			servers_split += "    server " + j + check + "\n"
	else:
		servers_split = ""
	
	config_add = name + "\n" + bind +  mode  + "\n" + balance + options_split + backend + servers_split + "\n"

	os.chdir(config.get('configs', 'haproxy_save_configs_dir'))

	cfg = hap_configs_dir + serv + "-" + funct.get_data('config') + ".cfg"
	
	funct.get_config(serv, cfg)
	try:
		with open(cfg, "a") as conf:
			conf.write(config_add)			
	except IOError:
		print("Can't read import config file")
	
	funct.logging(serv, "add.py add new %s" % name)
	print('<div class="line3">')
	
	MASTERS = sql.is_master(serv)
	for master in MASTERS:
		if master[0] != None:
			funct.upload_and_restart(master[0], cfg)
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
				'<li><a href="#listen">Listen</a></li>'
				'<li><a href="#frontend">Frontend</a></li>'
				'<li><a href="#backend">Backend</a></li>'
				'<li><a href="#ssl">SSL certificates</a></li>'
			'</ul>'
			'<div id="listen">'
				'<form name="add-listner" action="add.py">'
					'<table>'
						'<caption><h3 style="margin-left: 20px; margin-bottom: 10px;">Add listen</h3></caption>'
						'<tr>'
							'<td class="addName">Select server: </td>'
							'<td class="addOption">'
								'<select required name="serv" id="serv">'
									'<option disabled selected>Choose server</option>')

for i in listhap:
	print('<option value="%s">%s</option>' % (i[2], i[1]))
	
print('</select>'
		'<div class="tooltip tooltipTop"><b>Note:</b> If you reconfigure Master server, Slave will reconfigured automatically</div>'
				'</td>'
			'</tr>'
		'<tr>'
			'<td class="addName">Name:</td>'
			'<td class="addOption">'
				'<input type="text" name="listner" id="name" required title="Name Listner" placeholder="web_80" class="form-control">'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">IP and Port:</td>'
			'<td class="addOption">'
				'<input type="text" name="ip" id="ip" title="" size="15" placeholder="172.28.0.1" class="form-control"><b>:</b>'
				'<input type="number" name="port" id="listen-port" required title="Port for bind listen" size="5" placeholder="8080" class="form-control">'
				'<div class="tooltip tooltipTop">IP for bind listner, <b>if empty will be assignet on all IPs</b>. Start typing ip, or press down.<br>If you use <b>VRRP keep in blank</b>. If you assign an IP, the slave will not start</div>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Mode: </td>'
			'<td class="addOption">'
				'<select required name="mode" id="listen-mode-select">'
					'<option value="http" selected>http</option>'
					'<option value="tcp">tcp</option>'
				'</select>'
				'<span id="https-listen-span">'
					'<label for="https-listen" style="margin-top: 5px;" title="Enable ssl">ssl?</label>'
					'<input type="checkbox" id="https-listen" name="ssl" value="https" >'
				'</span>'
				'<div id="https-hide-listen" style="display: none;">'
					'<br /><span class="tooltip tooltipTop">Enter name to pem file, or press down:</span><br />'
					'<input type="text" name="cert" placeholder="some_cert.pem" class="form-control" size="39" id="path-cert-listen"> or upload: <input type="file" name="file"><br />'
					'<label for="ssl-check-listen" style="margin-top: 5px;">Disable ssl verify on servers?</label><input type="checkbox" id="ssl-check-listen" name="ssl-check" value="ssl-check" checked>'
				'</div>'
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
				'<label for="options-listen-show" style="margin-top: 5px;" title="Set options">Set</label><input type="checkbox" id="options-listen-show">'
				'<div id="options-listen-show-div" style="display: none;">'
					'<div class="tooltip">'
						'<span style="padding-right: 10px;" class="form-control">Start typing options: </span>'
						'<input type="text" id="options" class="form-control">'
						'<span style="padding-left: 10px;">'
							'or press down. <a href="http://cbonte.github.io/haproxy-dconv/1.7/configuration.html" target="_blanck" style="color: #23527c" title="HAproxy docs">Read more about options</a>'
						'</span>'
					'</div>'
					'<textarea name="option" title="Options thru" id="optionsInput" cols=80 placeholder="acl test hdr_beg(host) -i some_host"></textarea>'
				'</div>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Servers:</td>'
			'<td class="addOption">'
				'<textarea name="servers" required title="Backend servers" cols=80 placeholder="hostname ip:port"></textarea>'
				'<div>'
					'<label for="controlgroup-listen-show" style="margin-top: 5px;" title="Change default check">Cusmot check params</label>'
					'<input type="checkbox" id="controlgroup-listen-show" name="default-check" value="1">'
					'<span class="tooltip tooltipTop"> Default params: inter 2000 rise 2 fall 5</span>'
				'</div>'
				'<div class="controlgroup" id="controlgroup-listen" style="display: none;">'
					'<label for="check-servers-listen" title="Ebable servers check">Check</label>'
					'<input type="checkbox" id="check-servers-listen" name="check-servers" checked value="1">'
					'<select name="inter" id="inter-listen">'
						'<option value="inter" disabled selected>inter</option>'
						'<option value="1000">1000</option>'
						'<option value="2000">2000</option>'
						'<option value="3000">3000</option>'
					'</select>'
					'<select name="rise" id="rise-listen">'
						'<option value="rise" disabled selected>rise</option>'
						'<option value="1">1</option>'
						'<option value="2">2</option>'
						'<option value="3">3</option>'
					'</select>'
					'<select name="fall" id="fall-listen">'
						'<option value="fall" disabled selected>fall</option>'
						'<option value="4">4</option>'
						'<option value="5">5</option>'
						'<option value="6">6</option>'
					'</select>'
				'</div>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addButton">')
funct.get_button("Add Listen")
print('</td>'
		'</tr>'
		'</form>'
		'</table></div>'
		
		'<!-- Second tabs -->'
		
		'<div id="frontend">'
			'<form name="add-frontend" action="add.py">'
				'<table>'
					'<caption><h3 style="margin-left: 20px; margin-bottom: 10px;">Add frontend</h3></caption>'
					'<tr>'
						'<td class="addName">Select server: </td>'
						'<td class="addOption">'
							'<select required name="serv" id="serv2">'
								'<option disabled selected>Choose server</option>')

for i in listhap:
	print('<option value="%s">%s</option>' % (i[2], i[1]))
	
print('</select>'
		'<div class="tooltip tooltipTop"><b>Note:</b> If you reconfigure Master  server, Slave will reconfigured automatically</div>'
				'</td>'
			'</tr>'
		'<tr>'
			'<td class="addName">Name:</td>'
			'<td class="addOption">'
				'<input type="text" name="frontend" id="frontend" required title="Name frontend"  placeholder="web_80" class="form-control">'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">IP and Port:</td>'
			'<td class="addOption">'
				'<input type="text" name="ip" id="ip1" size="15" placeholder="172.28.0.1" class="form-control"><b>:</b>'
				'<input type="number" name="port" required title="Port for bind frontend" placeholder="8080" class="form-control">'
				'<div class="tooltip tooltipTop">IP for bind listner, <b>if empty will be assignet on all IPs</b>. Start typing ip, or press down.<br>If you use <b>VRRP keep in blank</b>. If you assign an IP, the slave will not start</div>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Mode: </td>'
			'<td class="addOption">'
				'<select required name="mode" id="frontend-mode-select">'
					'<option value="http" selected>http</option>'
					'<option value="tcp">tcp</option>'
				'</select>'
				'<span id="https-frontend-span">'
					'<label for="https-frontend" style="margin-top: 5px;">ssl?</label>'
					'<input type="checkbox" id="https-frontend" name="ssl" value="https">'
				'</span>'
				'<div id="https-hide-frontend" style="display: none;">'
					'<br /><span class="tooltip tooltipTop">Enter name to pem file, or press down:</span><br />'
					'<input type="text" name="cert" placeholder="some_cert.pem" class="form-control" size="39" id="path-cert-frontend">'					
				'</div>'				
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Optinons:</td>'
			'<td class="addOption">'
				'<label for="options-frontend-show" style="margin-top: 5px;" title="Set options">Set</label><input type="checkbox" id="options-frontend-show">'
				'<div id="options-frontend-show-div" style="display: none;">'
					'<div style="font-size: 12px; padding-bottom: 10px;">'
						'<span style="padding-right: 10px;">Start typing options: </span>'
						'<input type="text" id="options1" class="form-control">'
						'<span style="padding-left: 10px;">'
							'or press down. <a href="http://cbonte.github.io/haproxy-dconv/1.7/configuration.html" target="_blanck"  style="color: #23527c" title="HAproxy docs">Read more about options</a>'
						'</span>'
					'</div>'
					'<textarea name="option" title="Options thru" cols=80 id="optionsInput1" placeholder="acl test hdr_beg(host) -i some_host"></textarea>'
				'</div>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Default backend</td>'
			'<td class="addOption">'
				'<div style="font-size: 12px; padding-bottom: 10px;">Start typing backend, or press down</div>'
				'<input  name="backend" id="backends" required size="30" placeholder="some_backend" class="form-control">'
				'<span style="font-size: 12px; padding-left: 10px;"> .</span>'
				'<p style="font-size: 12px"><b>Note:</b> If backend don\'t exist, you must <a href="#" style="color: #23527c"  title="Create backend" id="redirectBackend">create backend first</a>.</p>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addButton">')
funct.get_button("Add Frontend")
print('</td>'
		'</tr>'
		'</form></table>'
		'</div>'
		
		
				'<!-- Third tabs -->'
		
		'<div id="backend">'
			'<form name="add-backend" action="add.py">'
				'<table>'
					'<caption><h3 style="margin-left: 20px; margin-bottom: 10px;">Add backend</h3></caption>'
					'<tr>'
						'<td class="addName">Select server: </td>'
						'<td class="addOption">'
							'<select required name="serv" id="serv3">'
								'<option disabled selected>Choose server</option>')

for i in listhap:
	print('<option value="%s">%s</option>' % (i[2], i[1]))
	
print('</select>'
		'<div class="tooltip tooltipTop"><b>Note:</b> If you reconfigure Master server, Slave will reconfigured automatically</div>'
				'</td>'
			'</tr>'
		'<tr>'
			'<td class="addName">Name:</td>'
			'<td class="addOption">'
				'<input type="text" name="backend" id="backend" required title="Name backend"  placeholder="web_80" class="form-control">'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Mode: </td>'
			'<td class="addOption">'
				'<select required name="mode" id="backend-mode-select">'
					'<option value="http" selected>http</option>'
					'<option value="tcp">tcp</option>'
				'</select>'
				'<span id="https-backend-span">'
					'<label for="https-backend" style="margin-top: 5px;">Ssl enabled on frontend?</label>'
					'<input type="checkbox" id="https-backend" name="ssl" value="https">'
				'</span>'
				'<div id="https-hide-backend" style="display: none;">'
					'<br /><span class="tooltip tooltipTop">Enter name to pem file, or press down:</span><br />'
					'<input type="text" name="cert" placeholder="some_cert.pem" class="form-control" size="39" id="path-cert-backend"><br />'
					'<label for="ssl-check" style="margin-top: 5px;">Disable ssl verify on servers?</label><input type="checkbox" id="ssl-check" name="ssl-check" value="ssl-check" checked>'
				'</div>'				
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
				'<label for="options-backend-show" style="margin-top: 5px;" title="Set options">Set</label><input type="checkbox" id="options-backend-show">'
					'<div id="options-backend-show-div" style="display: none;">'
					'<div style="font-size: 12px; padding-bottom: 10px;">'
						'<span style="padding-right: 10px;">Start typing options: </span>'
						'<input type="text" id="options2" class="form-control">'
						'<span style="padding-left: 10px;">'
							'or press down. <a href="http://cbonte.github.io/haproxy-dconv/1.7/configuration.html" target="_blanck" style="color: #23527c" title="HAproxy docs">Read more about options</a>'
						'</span>'
					'</div>'
					'<textarea name="option" title="Options thru" cols=80 id="optionsInput2" placeholder="acl test hdr_beg(host) -i some_host"></textarea>'
				'</div>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addName">Servers:</td>'
			'<td class="addOption">'
				'<textarea name="servers" title="Backend servers" required cols=80 placeholder="hostname ip:port"></textarea>'
				'<div>'
					'<label for="controlgroup-backend-show" style="margin-top: 5px;" title="Change default check"	>Cusmot check params</label>'
					'<input type="checkbox" id="controlgroup-backend-show" name="default-check">'
					'<span class="tooltip tooltipTop"> Default params: inter 2000 rise 2 fall 5</span>'
				'</div>'
				'<div class="controlgroup" id="controlgroup-backend" style="display: none;">'
					'<label for="check-servers-backend" title="Ebable servers check">Check</label>'
					'<input type="checkbox" id="check-servers-backend" name="check-servers" checked value="1">'
					'<select name="inter" id="inter-backend">'
						'<option value="inter" disabled selected>inter</option>'
						'<option value="1000">1000</option>'
						'<option value="2000">2000</option>'
						'<option value="3000">3000</option>'
					'</select>'
					'<select name="rise" id="rise-backend">'
						'<option value="rise" disabled selected>rise</option>'
						'<option value="1">1</option>'
						'<option value="2">2</option>'
						'<option value="3">3</option>'
					'</select>'
					'<select name="fall" id="fall-backend">'
						'<option value="fall" disabled selected>fall</option>'
						'<option value="4">4</option>'
						'<option value="5">5</option>'
						'<option value="6">6</option>'
					'</select>'
				'</div>'
			'</td>'
		'</tr>'
		'<tr>'
			'<td class="addButton">')
funct.get_button("Add Backend")
print('</td>'
		'</tr>'
		'</form></table></div>'
		
		'<div id="ssl">'
			'<table>'
				'<tr class="overviewHead">'
					'<td class="padding10 first-collumn">Upload SSL certificates</td>'
					'<td>'
						'Certificate name'
					'</td>'
					'<td>'
						'<span title="This pem file will be used to create https connection with haproxy">Paste certificate content here(?)</span>'
					'</td>'
				'</tr>'
				'<tr style="width: 50%;">'
					'<td class="first-collumn" valign="top" style="padding-top: 15px;">'
						'<select required id="serv4">'
							'<option disabled selected>Choose server</option>')

for i in listhap:
	print('<option value="%s">%s</option>' % (i[2], i[1]))
	
print('</select>'
		'</td>'
		'<td valign="top" style="padding-top: 27px;">'
			'<input type="text" id="ssl_name" class="form-control">'
		'</td>'
		'<td style="padding-top: 15px; padding-bottom: 15px;">'
			'<textarea id="ssl_cert" cols="50" rows="5"></textarea><br /><br />'
			'<a class="ui-button ui-widget ui-corner-all" id="ssl_key_upload" title="Upload ssl certificates">Upload</a>'	
		'</td>'	
		'</tr>'
		'</table>'
		'<div id="ajax-ssl"></div>'
		'</div>')

				
funct.footer()