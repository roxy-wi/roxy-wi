#!/usr/bin/env python3
import cgi
import os
import funct
import sql
import http.cookies
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('add.html')
form = funct.form
serv = form.getvalue('serv')

if form.getvalue('add'):
	c = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	c["restart"] = form.getvalue('serv')
	print(c)
	
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
	
dir = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')
white_dir = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')+"/"+user_group+"/white"
black_dir = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')+"/"+user_group+"/black"
if not os.path.exists(dir):
    os.makedirs(dir)
if not os.path.exists(dir+"/"+user_group):
    os.makedirs(dir+"/"+user_group)
if not os.path.exists(white_dir):
    os.makedirs(white_dir)
if not os.path.exists(black_dir):
    os.makedirs(black_dir)
	
white_lists = funct.get_files(dir=white_dir, format="lst")
black_lists = funct.get_files(dir=black_dir, format="lst")


template = template.render(title = "Add",
							role = sql.get_user_role_by_uuid(user_id.value),
							user = user,
							selects = servers,
							add = form.getvalue('add'),
							conf_add = form.getvalue('conf'),
							group = user_group,
							versions = funct.versions(),
							options = sql.select_options(),
							saved_servers = sql.select_saved_servers(),
							white_lists = white_lists,
							black_lists = black_lists,
							token = token)										
print(template)

if form.getvalue('mode') is not None: 
	cert_path = sql.get_setting('cert_path')
	haproxy_dir = sql.get_setting('haproxy_dir')
	port = form.getvalue('port')
	bind = ""
	ip = ""
	force_close = form.getvalue('force_close')
	balance = ""
	mode = "    mode " + form.getvalue('mode') + "\n"
	maxconn = ""
	options_split = ""
	ssl = ""
	ssl_check = ""
	
	if form.getvalue('balance')	 is not None:
		balance = "    balance " + form.getvalue('balance')	+ "\n"
	
	if form.getvalue('ip') is not None:
		ip = form.getvalue('ip')
	
	if form.getvalue('listner') is not None:
		name = "listen " + form.getvalue('listner')
		backend = ""
		end_name = form.getvalue('listner')
	elif form.getvalue('frontend') is not None:
		name = "frontend " + form.getvalue('frontend')
		backend = "    default_backend " + form.getvalue('backends') + "\n"
		end_name = form.getvalue('frontend')
	elif form.getvalue('new_backend') is not None: 
		name = "backend " + form.getvalue('new_backend')
		backend = ""
		end_name = form.getvalue('new_backend')
		
	if form.getvalue('maxconn'):
		maxconn = "    maxconn " + form.getvalue('maxconn') + "\n"
				
	if form.getvalue('ssl') == "https" and form.getvalue('mode') != "tcp":
		ssl = "ssl crt " + cert_path + form.getvalue('cert')
		if form.getvalue('ssl-check') == "ssl-check":
			ssl_check = " ssl verify none"
		else:
			ssl_check = " ssl verify"
				
	if not ip and port is not None:
		bind = "    bind *:"+ port + " " + ssl + "\n" 
	elif port is not None:
		bind = "    bind " + ip + ":" + port + " " + ssl + "\n"
		
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
		for j in i:	
			options_split += "    " + j + "\n"
		
	if force_close == "1":
		options_split += "    option http-server-close\n"
	elif force_close == "2":
		options_split += "    option forceclose\n"
	elif force_close == "3":
		options_split += "    option http-pretend-keepalive\n"
		
	if form.getvalue('blacklist') is not None:
		options_split += "    tcp-request connection reject if { src -f "+haproxy_dir+"/black/"+form.getvalue('blacklist')+" }\n"
		
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
			
	servers_split = ""	
	if form.getvalue('servers') is not None:	
		servers = form.getlist('servers')
		server_port = form.getlist('server_port')
		i = 0
		for server in servers:
			if form.getvalue('template') is None:
				servers_split += "    server "+server+" " + server +":"+server_port[i]+ check + "\n"
			else:
				servers_split += "    server-template "+form.getvalue('prefix')+" "+form.getvalue('template-number')+"  "+ server +":"+server_port[i]+ check + "\n"
			i += 1
		
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
			
	waf = ""
	if form.getvalue('waf') is not None:
		waf = "    filter spoe engine modsecurity config "+haproxy_dir+"/waf.conf\n"
		waf += "    http-request deny if { var(txn.modsec.code) -m int gt 0 }\n"
	
	config_add = "\n" + name + "\n" + bind + mode + maxconn +  balance + options_split + filter + compression_s + cache_s + waf + backend + servers_split + "\n" + cache_set

if form.getvalue('new_userlist') is not None:
	name = "userlist "+form.getvalue('new_userlist')+ "\n"
	
	new_userlist_groups = ""	
	if form.getvalue('userlist-group') is not None:	
		groups = form.getlist('userlist-group')
		for group in groups:
			new_userlist_groups += "    group "+group+ "\n"
			
	new_users_list = ""	
	if form.getvalue('userlist-user') is not None:	
		users = form.getlist('userlist-user')
		passwords = form.getlist('userlist-password')
		userlist_user_group = form.getlist('userlist-user-group')
		i = 0
		print(userlist_user_group)
		for user in users:
			try: 
				group = ' groups '+userlist_user_group[i]
			except:
				group = ''
			new_users_list += "    user "+user+" insecure-password " + passwords[i] +group+ "\n"
			i += 1
		
	config_add = "\n" + name + new_userlist_groups + new_users_list
	
try:
	if config_add:
		hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
		cfg = hap_configs_dir + serv + "-" + funct.get_data('config') + ".cfg"
		
		funct.get_config(serv, cfg)
		try:
			with open(cfg, "a") as conf:
				conf.write(config_add)			
		except IOError:
			print("Can't read import config file")
		
		funct.logging(serv, "add.py add new %s" % name)
		print('<div class="line3" style="position: absolute;top: 35px;left: 200px;">')
		
		MASTERS = sql.is_master(serv)
		for master in MASTERS:
			if master[0] != None:
				funct.upload_and_restart(master[0], cfg)
		
		stderr = funct.upload_and_restart(serv, cfg, just_save="save")
		if stderr:
			print('<div class="alert alert-danger">%s</div><div id="close"><span title="Close" style="cursor: pointer; float: right;">X</span></div>' % stderr)
		else:
			print('<meta http-equiv="refresh" content="0; url=add.py?add=%s&conf=%s&serv=%s">' % (name, config_add, serv))
			
		print('</div>')
except:
	pass

	
