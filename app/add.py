#!/usr/bin/env python3
import html
import cgi
import os
from configparser import ConfigParser, ExtendedInterpolation
import funct
import sql
import http
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('add.html')
form = cgi.FieldStorage()

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level = 2)

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit()
except:
	pass

output_from_parsed_template = template.render(title = "Add",
												role = sql.get_user_role_by_uuid(user_id.value),
												user = user,
												selects = servers,
												add = form.getvalue('add'),
												conf_add = form.getvalue('conf'))										
print(output_from_parsed_template)

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')
cert_path = config.get('haproxy', 'cert_path')

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
	
	funct.upload_and_restart(serv, cfg)
	print('<meta http-equiv="refresh" content="5; url=add.py?add=%s&conf=%s">' % (name, config_add))
		
	print('</div>')

	
