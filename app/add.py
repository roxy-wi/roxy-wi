#!/usr/bin/env python3
import html
import cgi
import os
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
	user_group = sql.get_user_group_by_uuid(user_id.value)
	token = sql.get_token(user_id.value)
except:
	pass

output_from_parsed_template = template.render(title = "Add",
												role = sql.get_user_role_by_uuid(user_id.value),
												user = user,
												selects = servers,
												add = form.getvalue('add'),
												conf_add = form.getvalue('conf'),
												group = user_group,
												token = token)										
print(output_from_parsed_template)

hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
cert_path = sql.get_setting('cert_path')

if form.getvalue('mode') is not None: 
	serv = form.getvalue('serv')
	port = form.getvalue('port')
	force_close = form.getvalue('force_close')
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
		name = "\nlisten " + form.getvalue('listner')
		backend = ""
		end_name = form.getvalue('listner')
	elif form.getvalue('frontend') is not None:
		name = "\nfrontend " + form.getvalue('frontend')
		backend = "    default_backend " + form.getvalue('backend') + "\n"
		end_name = form.getvalue('frontend')
	elif form.getvalue('new_backend') is not None: 
		name = "\nbackend " + form.getvalue('new_backend')
		backend = ""
		end_name = form.getvalue('new_backend')
				
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
		
	if force_close == "1":
		options_split += "    option http-server-close\n"
	elif force_close == "2":
		options_split += "    option forceclose\n"
	elif force_close == "3":
		options_split += "    option http-pretend-keepalive\n"
		
	if form.getvalue('blacklist') is not None:
		options_split += "    tcp-request connection reject if { src -f /etc/haproxy/black/"+form.getvalue('blacklist')+" }\n"
		
	if form.getvalue('cookie'):
		cookie = "    cookie "+form.getvalue('cookie_name')
		if form.getvalue('cookie_domain'):
			cookie += " domain "+form.getvalue('cookie_domain')
		if form.getvalue('rewrite'):
			rewrite = form.getvalue('rewrite')
		else:
			rewrite = ""
		if form.getvalue('prefix'):
			prefix = form.getvalue('prefix')
		else:
			prefix = ""
		if form.getvalue('nocache'):
			nocache = form.getvalue('nocache')
		else:
			nocache = ""
		if form.getvalue('postonly'):
			postonly = form.getvalue('postonly')
		else:
			postonly = ""
		if form.getvalue('dynamic'):
			dynamic = form.getvalue('dynamic')
		else:
			dynamic = ""
		cookie += " "+rewrite+" "+prefix+" "+nocache+" "+postonly+" "+dynamic+"\n"
		options_split += cookie
		if form.getvalue('dynamic'):
			options_split += "    dynamic-cookie-key " + form.getvalue('dynamic-cookie-key')+"\n"
		
	if form.getvalue('servers') is not None:	
		servers = form.getvalue('servers')
		i = servers.split("\n")
		servers_split = ""
		for j in i:	
			j = j.strip('\t\n\r')
			servers_split += "    server " + j + check + "\n"
	else:
		servers_split = ""
		
	compression = form.getvalue("compression")
	cache = form.getvalue("cache")
	compression_s = ""
	cache_s = ""
	cache_set = ""
	filter = ""
	if compression == "1" or cache == "2":
		filter = "    filter compression\n"
		if compression == "1":
			compression_s = "    compression algo gzip\n    compression type text/html text/plain text/css\n"
		if cache == "2":
			cache_s = "    http-request cache-use "+end_name+"\n    http-response cache-store "+end_name+"\n"
			cache_set = "cache "+end_name+"\n    total-max-size 4\n    max-age 240\n"
	
	config_add = name + "\n" + bind +  mode  + "\n" + balance + options_split + filter + compression_s + cache_s + backend + servers_split + "\n" + cache_set
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
	
	stderr = funct.upload_and_restart(serv, cfg)
	if stderr:
		print('<div class="alert alert-danger">%s</div>' % stderr)
	else:
		print('<meta http-equiv="refresh" content="0; url=add.py?add=%s&conf=%s">' % (name, config_add))
		
	print('</div>')

	
