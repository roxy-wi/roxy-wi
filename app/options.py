#!/usr/bin/env python3
# -*- coding: utf-8 -*-"
import os, sys
import funct
import sql

form = funct.form
serv = form.getvalue('serv')
act = form.getvalue('act')

if form.getvalue('new_metrics') or form.getvalue('new_waf_metrics'):
	print('Content-type: application/json\n')
else:
	print('Content-type: text/html\n')

if act == "checkrestart":
	servers = sql.get_dick_permit(ip=serv)
	for server in servers:
		if server != "":
			print("ok")
			sys.exit()
	sys.exit()

if not sql.check_token_exists(form.getvalue('token')):
	print("Your token has been expired")
	sys.exit()
		
if form.getvalue('getcerts') is not None and serv is not None:
	cert_path = sql.get_setting('cert_path')
	commands = [ "ls -1t "+cert_path+" |grep pem" ]
	try:
		funct.ssh_command(serv, commands, ip="1")
	except:
		print('<div class="alert alert-danger" style="margin:0">Can not connect to the server</div>')

if form.getvalue('checkSshConnect') is not None and serv is not None:
	try:
		funct.ssh_command(serv, ["ls -1t"])
	except:
		print('<div class="alert alert-danger" style="margin:0">Can not connect to the server</div>')
		
if form.getvalue('getcert') is not None and serv is not None:
	id = form.getvalue('getcert')
	cert_path = sql.get_setting('cert_path')
	commands = [ "cat "+cert_path+"/"+id ]
	try:
		funct.ssh_command(serv, commands, ip="1")
	except:
		print('<div class="alert alert-danger" style="margin:0">Can not connect to the server</div>')
		
			
if serv and form.getvalue('ssl_cert'):
	cert_local_dir = os.path.dirname(os.getcwd())+"/"+sql.get_setting('ssl_local_path')
	cert_path = sql.get_setting('cert_path')
	
	if not os.path.exists(cert_local_dir):
		os.makedirs(cert_local_dir)
	
	if form.getvalue('ssl_name') is None:
		print('<div class="alert alert-danger" style="float: left;">Please enter desired name</div>')
	else:
		name = form.getvalue('ssl_name') + '.pem'
	
	try:
		with open(name, "w") as ssl_cert:
			ssl_cert.write(form.getvalue('ssl_cert'))
	except IOError:
		print('<div class="alert alert-danger style="float: left;"">Can\'t save ssl keys file. Check ssh keys path in config</div>')
	else:
		print('<div class="alert alert-success" style="float: left;">SSL file was upload to %s into: %s  %s</div>' % (serv, cert_path, name))
		
	MASTERS = sql.is_master(serv)
	for master in MASTERS:
		if master[0] != None:
			funct.upload(master[0], cert_path, name)
	try:
		funct.upload(serv, cert_path, name)
	except Exception as e:
		funct.logging('localhost', e.args[0], haproxywi=1)
	try:
		os.system("mv %s %s" % (name, cert_local_dir))
	except OSError as e:
		funct.logging('localhost', e.args[0], haproxywi=1)
		
	funct.logging(serv, "add.py#ssl upload new ssl cert %s" % name)
	
	
if form.getvalue('backend') is not None:
	funct.show_backends(serv)
	
	
if form.getvalue('ip') is not None and serv is not None:
	commands = [ "sudo ip a |grep inet |egrep -v  '::1' |awk '{ print $2  }' |awk -F'/' '{ print $1  }'" ]
	funct.ssh_command(serv, commands, ip="1")
	
	
if form.getvalue('showif'):
	commands = ["sudo ip link|grep 'UP' |grep -v 'lo'| awk '{print $2}'  |awk -F':' '{print $1}'"]
	funct.ssh_command(serv, commands, ip="1")
	
	
if form.getvalue('action_hap') is not None and serv is not None:
	action = form.getvalue('action_hap')
	
	if funct.check_haproxy_config(serv):
		commands = [ "sudo systemctl %s haproxy" % action ]
		funct.ssh_command(serv, commands)		
		funct.logging(serv, 'HAProxy was '+action, haproxywi=1, login=1)
		print("HAproxy was %s" % action)
	else:
		print("Bad config, check please")
		
		
if form.getvalue('action_nginx') is not None and serv is not None:
	action = form.getvalue('action_nginx')
	
	if funct.check_haproxy_config(serv):
		commands = [ "sudo systemctl %s nginx" % action ]
		funct.ssh_command(serv, commands)		
		funct.logging(serv, 'Nginx was '+action, haproxywi=1, login=1)
		print("Nginx was %s" % action)
	else:
		print("Bad config, check please")
		
	
if form.getvalue('action_waf') is not None and serv is not None:
	serv = form.getvalue('serv')
	action = form.getvalue('action_waf')
	funct.logging(serv, 'WAF service was '+action, haproxywi=1, login=1)
	commands = [ "sudo systemctl %s waf" % action ]
	funct.ssh_command(serv, commands)		
	
	
if act == "overviewHapserverBackends":
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/ajax'))
	template = env.get_template('haproxyservers_backends.html')
	
	hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
	try:
		sections = funct.get_sections(hap_configs_dir +funct.get_files()[0])
	except:
		try:
			cfg = hap_configs_dir + serv + "-" + funct.get_data('config') + ".cfg"
		except:
			funct.logging('localhost', ' Cannot generate cfg path', haproxywi=1)
		try:
			error = funct.get_config(serv, cfg)
		except:
			funct.logging('localhost', ' Cannot download config', haproxywi=1)
		try:
			sections = funct.get_sections(cfg)
		except:
			funct.logging('localhost', ' Cannot get sections from config file', haproxywi=1)
			sections = 'Cannot get backends'
			
	template = template.render(backends=sections, serv=serv)
	print(template)
	
	
if act == "overviewHapservers":
	if form.getvalue('service') == 'nginx':
		config_path  = sql.get_setting('nginx_config_path')
	else:
		config_path  = sql.get_setting('haproxy_config_path')
	commands = [ "ls -l %s |awk '{ print $6\" \"$7\" \"$8}'" % config_path ]
	try:
		print(funct.ssh_command(serv, commands))
	except:
		print('Cannot get last date')
	
	
if act == "overview":	
	import asyncio
	async def async_get_overview(serv1, serv2):
		server_status = ()
		commands2 = [ "ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l" ]
		cmd = 'echo "show info" |nc %s %s -w 1|grep -e "Process_num"' % (serv2, sql.get_setting('haproxy_sock_port'))
		keepalived = sql.select_keealived(serv2)
		if keepalived == 1:
			command = [ "ps ax |grep keepalived|grep -v grep|wc -l" ]
			keepalived_process = funct.ssh_command(serv2, command)
		else:
			keepalived_process = ''
		nginx = sql.select_nginx(serv2)
		if nginx == 1:
			command = [ "ps ax |grep nginx:|grep -v grep|wc -l" ]
			nginx_process = funct.ssh_command(serv2, command)
		else:
			nginx_process = ''
		server_status = (serv1, 
						serv2, 
						funct.server_status(funct.subprocess_execute(cmd)), 
						sql.select_servers(server=serv2, keep_alive=1),
						funct.ssh_command(serv2, commands2),
						sql.select_waf_servers(serv2),
						keepalived,
						keepalived_process,
						nginx,
						nginx_process)
		return server_status


	async def get_runner_overview():
		import http.cookies
		from jinja2 import Environment, FileSystemLoader
		env = Environment(loader=FileSystemLoader('templates/ajax'),extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'])
		
		servers = []
		template = env.get_template('overview.html')
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_id = cookie.get('uuid')
		futures = [async_get_overview(server[1], server[2]) for server in sql.select_servers(server=serv)]
		for i, future in enumerate(asyncio.as_completed(futures)):
			result = await future
			servers.append(result)
		servers_sorted = sorted(servers, key=funct.get_key)
		template = template.render(service_status=servers_sorted, role=sql.get_user_role_by_uuid(user_id.value))
		print(template)
	
	
	ioloop = asyncio.get_event_loop()
	ioloop.run_until_complete(get_runner_overview())
	ioloop.close()
	
	
if act == "overviewwaf":	
	import asyncio
	async def async_get_overviewWaf(serv1, serv2):
		haproxy_dir  = sql.get_setting('haproxy_dir')
		server_status = ()
		commands = [ "ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l" ]
		commands1 = [ "cat %s/waf/modsecurity.conf  |grep SecRuleEngine |grep -v '#' |awk '{print $2}'" % haproxy_dir ]
		
		server_status = (serv1,serv2, 
							funct.ssh_command(serv2, commands), 
							funct.ssh_command(serv2, commands1).strip(), 
							sql.select_waf_metrics_enable_server(serv2))
		return server_status


	async def get_runner_overviewWaf():
		import http.cookies
		from jinja2 import Environment, FileSystemLoader
		env = Environment(loader=FileSystemLoader('templates/ajax'),extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'])
		template = env.get_template('overivewWaf.html')
		
		servers = []
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_id = cookie.get('uuid')
		futures = [async_get_overviewWaf(server[1], server[2]) for server in sql.select_servers(server=serv)]
		for i, future in enumerate(asyncio.as_completed(futures)):
			result = await future
			servers.append(result)
		servers_sorted = sorted(servers, key=funct.get_key)
		template = template.render(service_status=servers_sorted, role=sql.get_user_role_by_uuid(user_id.value))
		print(template)
	
	ioloop = asyncio.get_event_loop()
	ioloop.run_until_complete(get_runner_overviewWaf())
	ioloop.close()
	
	
if act == "overviewServers":
	import asyncio	
	async def async_get_overviewServers(serv1, serv2):
		server_status = ()
		commands =  [ "top -u haproxy -b -n 1" ]
		cmd = 'echo "show info" |nc %s %s -w 1|grep -e "Ver\|CurrConns\|Maxco\|MB\|Uptime:"' % (serv2, sql.get_setting('haproxy_sock_port'))
		out = funct.subprocess_execute(cmd)
		out1 = ""
		
		for k in out:
			if "Ncat:" not in k:
				for r in k:
					out1 += r
					out1 += "<br />"
			else:
				out1 = "Can\'t connect to HAproxy"

		server_status = (serv1,serv2, out1, funct.ssh_command(serv2, commands))
		return server_status	
		
	async def get_runner_overviewServers(**kwargs):
		import http.cookies
		from jinja2 import Environment, FileSystemLoader
		env = Environment(loader=FileSystemLoader('templates/ajax'),extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'])
		template = env.get_template('overviewServers.html')	
		
		servers = []	
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_id = cookie.get('uuid')
		role = sql.get_user_role_by_uuid(user_id.value)
		futures = [async_get_overviewServers(kwargs.get('server1'), kwargs.get('server2'))]

		for i, future in enumerate(asyncio.as_completed(futures)):
			result = await future
			servers.append(result)
		servers_sorted = sorted(servers, key=funct.get_key)
		template = template.render(service_status=servers_sorted, role=role, id=kwargs.get('id'))
		print(template)	
	
	id = form.getvalue('id')
	name = form.getvalue('name')
	ioloop = asyncio.get_event_loop()
	ioloop.run_until_complete(get_runner_overviewServers(server1=name, server2=serv, id=id))
	ioloop.close()

	
	
if act == "overviewHapwi":
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
	template = env.get_template('/overviewHapwi.html')
	cmd = "top -b -n 1 |head -12"
	server_status, stderr = funct.subprocess_execute(cmd)
	
	template = template.render(server_status=server_status,stderr=stderr)									
	print(template)
	
	
if form.getvalue('action'):
	import requests
	
	haproxy_user = sql.get_setting('stats_user')
	haproxy_pass = sql.get_setting('stats_password')
	stats_port = sql.get_setting('stats_port')
	stats_page = sql.get_setting('stats_page')
	
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
	
	if form.getvalue('service') == 'nginx':
		haproxy_user = sql.get_setting('nginx_stats_user')
		haproxy_pass = sql.get_setting('nginx_stats_password')
		stats_port = sql.get_setting('nginx_stats_port')
		stats_page = sql.get_setting('nginx_stats_page')
	else:
		haproxy_user = sql.get_setting('stats_user')
		haproxy_pass = sql.get_setting('stats_password')
		stats_port = sql.get_setting('stats_port')
		stats_page = sql.get_setting('stats_page')
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
	if form.getvalue('service') == 'nginx':
		from jinja2 import Environment, FileSystemLoader
		env = Environment(loader=FileSystemLoader('templates/'))
		template = env.get_template('ajax/nginx_stats.html')
		
		servers_with_status = list()
		h = ()
		out1 = []
		for k in data.decode('utf-8').split():
			out1.append(k) 
		h = (out1, )
		servers_with_status.append(h)
		
		template = template.render(out=servers_with_status)
		print(template)
		
		
	else:	
		print(data.decode('utf-8'))
	
	
if serv is not None and form.getvalue('rows') is not None:
	rows = form.getvalue('rows')
	waf = form.getvalue('waf')
	grep = form.getvalue('grep')
	hour = form.getvalue('hour')
	minut = form.getvalue('minut')
	hour1 = form.getvalue('hour1')
	minut1 = form.getvalue('minut1')
	service = form.getvalue('service')
	out = funct.show_haproxy_log(serv, rows=rows, waf=waf, grep=grep, hour=hour, minut=minut, hour1=hour1, minut1=minut1, service=service)
	print(out)
	
	
if serv is not None and form.getvalue('rows1') is not None:
	rows = form.getvalue('rows1')
	grep = form.getvalue('grep')
	hour = form.getvalue('hour')
	minut = form.getvalue('minut')
	hour1 = form.getvalue('hour1')
	minut1 = form.getvalue('minut1')
	date = hour+':'+minut
	date1 = hour1+':'+minut1
	apache_log_path = sql.get_setting('apache_log_path')
	
	if grep is not None:
		grep_act  = '|grep'
	else:
		grep_act = ''
		grep = ''
		
	if serv == 'haproxy-wi.access.log':
		cmd="cat %s| awk -F\"/|:\" '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s  %s %s" % (apache_log_path+"/"+serv, date, date1, rows, grep_act, grep)
	else:
		cmd="cat %s| awk '$4>\"%s:00\" && $4<\"%s:00\"' |tail -%s  %s %s" % (apache_log_path+"/"+serv, date, date1, rows, grep_act, grep)

	output, stderr = funct.subprocess_execute(cmd)

	print(funct.show_log(output))
	print(stderr)
	
		
if form.getvalue('viewlogs') is not None:
	viewlog = form.getvalue('viewlogs')
	log_path = funct.get_config_var('main', 'log_path')
	rows = form.getvalue('rows')
	grep = form.getvalue('grep')
	hour = form.getvalue('hour')
	minut = form.getvalue('minut')
	hour1 = form.getvalue('hour1')
	minut1 = form.getvalue('minut1')
	date = hour+':'+minut
	date1 = hour1+':'+minut1
	
	if grep is not None:
		grep_act  = '|grep'
	else:
		grep_act = ''
		grep = ''

	if viewlog == 'backup.log':
		cmd="cat %s| awk '$2>\"%s:00\" && $2<\"%s:00\"' |tail -%s  %s %s" % (log_path + viewlog, date, date1, rows, grep_act, grep)
	else:
		cmd="cat %s| awk '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s  %s %s" % (log_path + viewlog, date, date1, rows, grep_act, grep)
	output, stderr = funct.subprocess_execute(cmd)

	print(funct.show_log(output))
	print(stderr)
		
		
if serv is not None and act == "showMap":
	from datetime import datetime
	from pytz import timezone
	import networkx as nx
	import matplotlib
	matplotlib.use('Agg')
	import matplotlib.pyplot as plt
	
	stats_port= sql.get_setting('stats_port')
	haproxy_config_path  = sql.get_setting('haproxy_config_path')
	hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
	date = funct.get_data('config')
	cfg = hap_configs_dir + serv + "-" + date + ".cfg"
	
	print('<center>')
	print("<h4>Map from %s</h4><br />" % serv)
	
	G = nx.DiGraph()
	
	error = funct.get_config(serv, cfg)	
	if error:
		print('<div class="alert alert-danger">'+error+'</div>')
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Can\'t read import config file</div>')
	
	node = ""
	line_new2 = [1,""]
	i,k  = 800, 800
	j, m = 0, 0
	for line in conf:
		if line.startswith('listen') or line.startswith('frontend'):
			if "stats" not in line:				
				node = line
				i = i - 750	
		if line.find("backend") == 0: 
			node = line
			i = i - 700	
			G.add_node(node,pos=(k,i),label_pos=(k,i+100))
		
		if "bind" in line or (line.startswith('listen') and ":" in line) or (line.startswith('frontend') and ":" in line):
			try:
				bind = line.split(":")
				if stats_port not in bind[1]:
					bind[1] = bind[1].strip(' ')
					bind = bind[1].split("crt")
					node = node.strip(' \t\n\r')
					node = node + ":" + bind[0]
					G.add_node(node,pos=(k,i),label_pos=(k,i+100))
			except:
				pass

		if "server " in line or "use_backend" in line or "default_backend" in line and "stats" not in line and "#" not in line:
			if "timeout" not in line and "default-server" not in line and "#" not in line and "stats" not in line:
				i = i - 1050
				j = j + 1				
				if "check" in line:
					line_new = line.split("check")
				else:
					line_new = line.split("if ")
				if "server" in line:
					line_new1 = line_new[0].split("server")
					line_new[0] = line_new1[1]	
					line_new2 = line_new[0].split(":")
					line_new[0] = line_new2[0]					
				
				line_new[0] = line_new[0].strip(' \t\n\r')
				line_new2[1] = line_new2[1].strip(' \t\n\r')

				if j % 2 == 0:
					G.add_node(line_new[0],pos=(k+230,i-335),label_pos=(k+225,i-180))
				else:
					G.add_node(line_new[0],pos=(k-230,i-0),label_pos=(k-225,i+180))

				if line_new2[1] != "":	
					G.add_edge(node, line_new[0], port=line_new2[1])
				else:
					G.add_edge(node,line_new[0])

	os.system("/bin/rm -f " + cfg)	

	pos=nx.get_node_attributes(G,'pos')
	pos_label=nx.get_node_attributes(G,'label_pos')
	edge_labels = nx.get_edge_attributes(G,'port')
	
	try:
		plt.figure(10,figsize=(10,15))
		nx.draw(G, pos, with_labels=False, font_weight='bold', width=3, alpha=0.1,linewidths=5)	
		nx.draw_networkx_nodes(G,pos, node_color="skyblue", node_size=100, alpha=0.8, node_shape="p")
		nx.draw_networkx_labels(G,pos=pos_label, alpha=1, font_color="green", font_size=10)
		nx.draw_networkx_edges(G,pos, width=0.5,alpha=0.5, edge_color="#5D9CEB",arrows=False)
		nx.draw_networkx_edge_labels(G, pos,label_pos=0.5,font_color="blue", labels=edge_labels, font_size=8)
		
		plt.savefig("map.png")
		plt.show()
	except Exception as e:
		print('<div class="alert alert-danger">' + str(e) + '</div>')
		
	cmd = "rm -f "+os.path.dirname(os.getcwd())+"/map*.png && mv map.png "+os.path.dirname(os.getcwd())+"/map"+date+".png"
	output, stderr = funct.subprocess_execute(cmd)
	print(stderr)

	print('<img src="/map%s.png" alt="map">' % date)		
	
	
if form.getvalue('servaction') is not None:
	server_state_file = sql.get_setting('server_state_file')
	haproxy_sock = sql.get_setting('haproxy_sock')
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
			
	print(funct.ssh_command(serv, command, show_log="1"))
	action = 'edit.py ' + enable + ' ' + backend
	funct.logging(serv, action)


if act == "showCompareConfigs":
	import glob
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
	template = env.get_template('ajax/show_compare_configs.html')
	left = form.getvalue('left')
	right = form.getvalue('right')
	
	if form.getvalue('service') == 'nginx':
		return_files=funct.get_files(funct.get_config_var('configs', 'nginx_save_configs_dir'), 'conf')
	else:
		return_files=funct.get_files()
	
	template = template.render(serv=serv, right=right, left=left, return_files=return_files)									
	print(template)
	
	
if serv is not None and form.getvalue('right') is not None:
	from jinja2 import Environment, FileSystemLoader
	left = form.getvalue('left')
	right = form.getvalue('right')
	if form.getvalue('service') == 'nginx':
		configs_dir = funct.get_config_var('configs', 'nginx_save_configs_dir')
	else:
		configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
	cmd='diff -ub %s%s %s%s' % (configs_dir, left, configs_dir, right)	
	env = Environment(loader=FileSystemLoader('templates/'), autoescape=True, extensions=["jinja2.ext.loopcontrols", "jinja2.ext.do"])
	template = env.get_template('ajax/compare.html')
	
	output, stderr = funct.subprocess_execute(cmd)
	template = template.render(stdout=output)	
	
	print(template)
	print(stderr)
	
	
if serv is not None and act == "configShow":
	if form.getvalue('service') == 'keepalived':
		configs_dir = funct.get_config_var('configs', 'kp_save_configs_dir')
	elif form.getvalue('service') == 'nginx':
		configs_dir = funct.get_config_var('configs', 'nginx_save_configs_dir')
	else:
		configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
	
	if form.getvalue('configver') is None:	
		cfg = configs_dir + serv + "-" + funct.get_data('config') + ".cfg"
		funct.get_config(serv, cfg)
	else: 
		cfg = configs_dir + form.getvalue('configver')
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Can\'t read config file</div>')
		
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True, trim_blocks=True, lstrip_blocks=True, extensions=["jinja2.ext.loopcontrols", "jinja2.ext.do"])
	template = env.get_template('config_show.html')
	
	template = template.render(conf=conf,
								serv=serv, 
								configver=form.getvalue('configver'), 
								role=funct.is_admin(level=2), 
								service=form.getvalue('service'))											
	print(template)
	
	if form.getvalue('configver') is None:
		os.system("/bin/rm -f " + cfg)	
		
		
if form.getvalue('master'):
	master = form.getvalue('master')
	slave = form.getvalue('slave')
	ETH = form.getvalue('interface')
	IP = form.getvalue('vrrpip')
	syn_flood = form.getvalue('syn_flood')
	script = "install_keepalived.sh"
	fullpath = funct.get_config_var('main', 'fullpath')
	proxy = sql.get_setting('proxy')
	ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(master)
	
	if ssh_enable == 0:
		ssh_key_name = ''
	
	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy 
	else:
		proxy_serv = ''		
		
	os.system("cp scripts/%s ." % script)
	
	if form.getvalue('hap') == "1":
		funct.install_haproxy(master)
		funct.install_haproxy(slave)
		
	if form.getvalue('nginx') == "1":
		funct.install_nginx(master)
		funct.install_nginx(slave)
		
	commands = [ "chmod +x "+script +" &&  ./"+script +" PROXY=" + proxy_serv+ 
				" ETH="+ETH+" IP="+str(IP)+" MASTER=MASTER"+" SYN_FLOOD="+syn_flood+" HOST="+str(master)+
				" USER="+str(ssh_user_name)+" PASS="+str(ssh_user_password)+" KEY="+str(ssh_key_name) ]
	
	output, error = funct.subprocess_execute(commands[0])
	
	if error:
		funct.logging('localhost', error, haproxywi=1)
		print('error: '+error)
	else:
		for l in output:
			if "msg" in l or "FAILED" in l:
				try:
					l = l.split(':')[1]
					l = l.split('"')[1]
					print(l+"<br>")
					break
				except:
					print(output)
					break
		else:
			print('success: Master Keepalived was installed<br>')
				
	ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(slave)
	
	if ssh_enable == 0:
		ssh_key_name = ''
		
	commands = [ "chmod +x "+script +" &&  ./"+script +" PROXY=" +proxy_serv+ 
				" ETH="+ETH+" IP="+IP+" MASTER=BACKUP"+" HOST="+str(slave)+
				" USER="+str(ssh_user_name)+" PASS="+str(ssh_user_password)+" KEY="+str(ssh_key_name) ]
	
	output, error = funct.subprocess_execute(commands[0])
	
	if error:
		funct.logging('localhost', error, haproxywi=1)
		print('error: '+error)
	else:
		for l in output:
			if "msg" in l or "FAILED" in l:
				try:
					l = l.split(':')[1]
					l = l.split('"')[1]
					print(l+"<br>")
					break
				except:
					print(output)
					break
		else:
			print('success: Slave Keepalived was installed<br>')
			
	os.system("rm -f %s" % script)
	sql.update_server_master(master, slave)
	sql.update_keepalived(master)
	sql.update_keepalived(slave)
	
	
if form.getvalue('masteradd'):
	master = form.getvalue('masteradd')
	slave = form.getvalue('slaveadd')
	ETH = form.getvalue('interfaceadd')
	IP = form.getvalue('vrrpipadd')
	kp = form.getvalue('kp')
	script = "install_keepalived.sh"
	proxy = sql.get_setting('proxy')	
	ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(master)
	
	if ssh_enable == 0:
		ssh_key_name = ''
		
	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy 
	else:
		proxy_serv = ''		
		
	os.system("cp scripts/%s ." % script)
		
	commands = [ "chmod +x "+script +" &&  ./"+script +" PROXY=" + proxy_serv+ 
				" ETH="+ETH+" IP="+str(IP)+" MASTER=MASTER"+" RESTART="+kp+" ADD_VRRP=1 HOST="+str(master)+
				" USER="+str(ssh_user_name)+" PASS="+str(ssh_user_password)+" KEY="+str(ssh_key_name) ]
	
	output, error = funct.subprocess_execute(commands[0])
	
	if error:
		funct.logging('localhost', error, haproxywi=1)
		print('error: '+error)
	else:
		for l in output:
			if "msg" in l or "FAILED" in l:
				try:
					l = l.split(':')[1]
					l = l.split('"')[1]
					print(l+"<br>")
					break
				except:
					print(output)
					break
		else:
			print('success: Master VRRP address was added<br>')
		
		
	ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(slave)
	
	if ssh_enable == 0:
		ssh_key_name = ''
	
	commands = [ "chmod +x "+script +" &&  ./"+script +" PROXY=" + proxy_serv+ 
				" ETH="+ETH+" IP="+str(IP)+" MASTER=BACKUP"+" RESTART="+kp+" ADD_VRRP=1 HOST="+str(slave)+
				" USER="+str(ssh_user_name)+" PASS="+str(ssh_user_password)+" KEY="+str(ssh_key_name) ]
	
	output, error = funct.subprocess_execute(commands[0])
	
	if error:
		funct.logging('localhost', error, haproxywi=1)
		print('error: '+error)
	else:
		for l in output:
			if "msg" in l or "FAILED" in l:
				try:
					l = l.split(':')[1]
					l = l.split('"')[1]
					print(l+"<br>")
					break
				except:
					print(output)
					break
		else:
			print('success: Slave VRRP address was added<br>')
			
	os.system("rm -f %s" % script)
	
	
if form.getvalue('backup') or form.getvalue('deljob') or form.getvalue('backupupdate'):
	server = form.getvalue('server')
	rpath = form.getvalue('rpath')
	time = form.getvalue('time')
	type = form.getvalue('type')
	rserver = form.getvalue('rserver')
	cred = form.getvalue('cred')
	deljob = form.getvalue('deljob')
	update = form.getvalue('backupupdate')
	description = form.getvalue('description')
	script = "backup.sh"	
	ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path('localhost', id=int(cred))	
	
	if deljob:
		time = ''
		rpath = ''
		type = ''
	elif update:
		deljob = ''
	else:
		deljob = ''	
		if sql.check_exists_backup(server):
			print('info: Backup job for %s already exists' % server)
			sys.exit()
		
	os.system("cp scripts/%s ." % script)
		
	commands = [ "chmod +x "+script +" &&  ./"+script +"  HOST="+rserver+"  SERVER="+server+" TYPE="+type+
				" TIME="+time+" RPATH="+rpath+" DELJOB="+deljob+" USER="+str(ssh_user_name)+" KEY="+str(ssh_key_name) ]
	
	output, error = funct.subprocess_execute(commands[0])
	
	if error:
		funct.logging('backup', error, haproxywi=1)
		print('error: '+error)
	else:
		for l in output:
			if "msg" in l or "FAILED" in l:
				try:
					l = l.split(':')[1]
					l = l.split('"')[1]
					print(l+"<br>")
					break
				except:
					print(output)
					break
		else:			
			if deljob == '' and update == '':
				if sql.insert_backup_job(server, rserver, rpath, type, time, cred, description):
					funct.logging('backup ', ' has created a new backup job for server '+server , haproxywi=1, login=1)
					import http.cookies
					from jinja2 import Environment, FileSystemLoader
					env = Environment(loader=FileSystemLoader('templates/ajax'))
					template = env.get_template('new_backup.html')
					template = template.render(backups=sql.select_backups(server=server, rserver=rserver), sshs=sql.select_ssh())											
					print(template)
					print('success: Backup job has created<br>')
				else:
					print('error: Cannot add job into DB<br>')
			elif deljob:
				sql.delete_backups(deljob)
				print('Ok')
				funct.logging('backup ', ' has deleted a backup job for server '+server, haproxywi=1, login=1)
			elif update:
				sql.update_backup(server, rserver, rpath, type, time, cred, description, update)
				print('Ok')
				funct.logging('backup ', ' has updated a backup job for server '+server, haproxywi=1, login=1)
				
				
if form.getvalue('install_nginx'):
	funct.install_nginx(form.getvalue('install_nginx'))
				
	
if form.getvalue('haproxyaddserv'):
	funct.install_haproxy(form.getvalue('haproxyaddserv'), syn_flood=form.getvalue('syn_flood'), hapver=form.getvalue('hapver'))
	
	
if form.getvalue('installwaf'):
	funct.waf_install(form.getvalue('installwaf'))
	
	
if form.getvalue('update_haproxy_wi'):
	funct.update_haproxy_wi()
	
	
if form.getvalue('metrics_waf'):
	sql.update_waf_metrics_enable(form.getvalue('metrics_waf'), form.getvalue('enable'))
	
		
if form.getvalue('table_metrics'):
	import http.cookies
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/ajax'))
	template = env.get_template('table_metrics.html')
		
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')	
	table_stat = sql.select_table_metrics(user_id.value)

	template = template.render(table_stat=sql.select_table_metrics(user_id.value))											
	print(template)
	
	
if form.getvalue('new_metrics'):
	serv = form.getvalue('server')
	metric = sql.select_metrics(serv)
	metrics = {}
	metrics['chartData'] = {}
	metrics['chartData']['labels'] = {}
	labels = ''
	curr_con = ''
	curr_ssl_con = ''
	sess_rate = ''

	for i in metric:
		label = str(i[5])
		label = label.split(' ')[1]
		labels += label+','
		curr_con += str(i[1])+','
		curr_ssl_con += str(i[2])+','
		sess_rate += str(i[3])+','
		server = str(i[0])
			
	metrics['chartData']['labels'] = labels
	metrics['chartData']['curr_con'] = curr_con
	metrics['chartData']['curr_ssl_con'] = curr_ssl_con
	metrics['chartData']['sess_rate'] = sess_rate
	metrics['chartData']['server'] = server
	
	import json
	print(json.dumps(metrics))
			

if form.getvalue('new_waf_metrics'):	
	serv = form.getvalue('server')
	metric = sql.select_waf_metrics(serv)
	metrics = {}
	metrics['chartData'] = {}
	metrics['chartData']['labels'] = {}
	labels = ''
	curr_con = ''

	for i in metric:
		label = str(i[2])
		label = label.split(' ')[1]
		labels += label[0]+','
		curr_con += str(i[1])+','
		
	metrics['chartData']['labels'] = labels
	metrics['chartData']['curr_con'] = curr_con
	metrics['chartData']['server'] = serv
	
	import json
	print(json.dumps(metrics))
	
	
if form.getvalue('get_hap_v'):
	output = funct.check_haproxy_version(serv)
	print(output)
	
	
if form.getvalue('get_nginx_v'):
	cmd = [ "/usr/sbin/nginx -v" ]
	print(funct.ssh_command(serv, cmd))
	
	
if form.getvalue('bwlists'):
	list = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')+"/"+form.getvalue('group')+"/"+form.getvalue('color')+"/"+form.getvalue('bwlists')
	try:
		file = open(list, "r")
		file_read = file.read()
		file.close
		print(file_read)
	except IOError:
		print('<div class="alert alert-danger" style="margin:0">Cat\'n read '+form.getvalue('color')+' list</div>')
		
		
if form.getvalue('bwlists_create'):
	color = form.getvalue('color')
	list_name = form.getvalue('bwlists_create').split('.')[0]
	list_name += '.lst'
	list = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')+"/"+form.getvalue('group')+"/"+color+"/"+list_name
	try:
		open(list, 'a').close()
		print('<div class="alert alert-success" style="margin-left:14px">'+form.getvalue('color')+' list was created</div>')
		funct.logging(server[1], 'has created  '+color+' list '+list_name, haproxywi=1, login=1)
	except IOError as e:
		print('<div class="alert alert-danger" style="margin-left:14px">Cat\'n create new '+form.getvalue('color')+' list. %s </div>' % e)
		
		
if form.getvalue('bwlists_save'):
	color = form.getvalue('color')
	bwlists_save = form.getvalue('bwlists_save')
	list = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')+"/"+form.getvalue('group')+"/"+color+"/"+bwlists_save
	try:
		with open(list, "w") as file:
			file.write(form.getvalue('bwlists_content'))
	except IOError as e:
		print('<div class="alert alert-danger" style="margin-left:14px">Cat\'n save '+color+' list. %s </div>' % e)
	
	servers = sql.get_dick_permit()
	path = sql.get_setting('haproxy_dir')+"/"+color
	
	for server in servers:
		funct.ssh_command(server[2], ["sudo mkdir "+path])
		funct.ssh_command(server[2], ["sudo chown $(whoami) "+path])
		error = funct.upload(server[2], path+"/"+bwlists_save, list, dir='fullpath')
		if error:
			print('<div class="alert alert-danger">Upload fail: %s</div>' % error)			
		else:
			print('<div class="alert alert-success" style="margin:10px; margin-left:14px">Edited '+color+' list was uploaded to '+server[1]+'</div>')
			funct.logging(server[1], 'has edited  '+color+' list '+bwlists_save, haproxywi=1, login=1)
			if form.getvalue('bwlists_restart') == 'restart':
				funct.ssh_command(server[2], ["sudo " + sql.get_setting('restart_command')])
			
			
if form.getvalue('get_lists'):
	list = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')+"/"+form.getvalue('group')+"/"+form.getvalue('color')
	lists = funct.get_files(dir=list, format="lst")
	for list in lists:
		print(list)
		
		
if form.getvalue('get_ldap_email'):
	username = form.getvalue('get_ldap_email')
	import ldap
	
	server = sql.get_setting('ldap_server')
	port = sql.get_setting('ldap_port')
	user = sql.get_setting('ldap_user')
	password = sql.get_setting('ldap_password')
	ldap_base = sql.get_setting('ldap_base')
	domain = sql.get_setting('ldap_domain')
	ldap_search_field = sql.get_setting('ldap_search_field')
	ldap_class_search = sql.get_setting('ldap_class_search')
	ldap_user_attribute = sql.get_setting('ldap_user_attribute')

	l = ldap.initialize(server+':'+port)
	try:
		l.protocol_version = ldap.VERSION3
		l.set_option(ldap.OPT_REFERRALS, 0)

		bind = l.simple_bind_s(user, password)

		criteria = "(&(objectClass="+ldap_class_search+")("+ldap_user_attribute+"="+username+"))"
		attributes = [ldap_search_field]
		result = l.search_s(ldap_base, ldap.SCOPE_SUBTREE, criteria, attributes)

		results = [entry for dn, entry in result if isinstance(entry, dict)]
		try:
			print('["'+results[0][ldap_search_field][0].decode("utf-8")+'","'+domain+'"]')
		except:
			print('error: user not found')
	finally:
		l.unbind()
		

if form.getvalue('change_waf_mode'):
	waf_mode = form.getvalue('change_waf_mode')
	server_hostname = form.getvalue('server_hostname')
	haproxy_dir  = sql.get_setting('haproxy_dir')
	serv = sql.select_server_by_name(server_hostname)
	commands = [ "sudo sed -i 's/^SecRuleEngine.*/SecRuleEngine %s/' %s/waf/modsecurity.conf " % (waf_mode, haproxy_dir) ]
	funct.ssh_command(serv, commands)
	funct.logging(serv, 'Was changed WAF mod to '+waf_mode, haproxywi=1, login=1)
	
	
error_mess = '<span class="alert alert-danger" id="error">All fields must be completed <a title="Close" id="errorMess"><b>X</b></a></span>'

	
if form.getvalue('newuser') is not None:
	email = form.getvalue('newemail')
	password = form.getvalue('newpassword')
	role = form.getvalue('newrole')
	group = form.getvalue('newgroupuser')
	new_user = form.getvalue('newusername')	
	page = form.getvalue('page')	
	activeuser = form.getvalue('activeuser')	
	role_id = sql.get_role_id_by_name(role)
	
	if sql.check_group(group, role_id):
		if funct.is_admin(level=role_id):
			if sql.add_user(new_user, email, password, role, group, activeuser):
				from jinja2 import Environment, FileSystemLoader
				env = Environment(loader=FileSystemLoader('templates/'))
				template = env.get_template('ajax/new_user.html')

				template = template.render(users=sql.select_users(user=new_user),
											groups=sql.select_groups(),
											page=page,
											roles=sql.select_roles())
				print(template)
				funct.logging('a new user '+new_user, ' has created ', haproxywi=1, login=1)
		else:
			funct.logging(new_user, ' tried to privilege escalation', haproxywi=1, login=1)
			
			
if form.getvalue('userdel') is not None:
	userdel = form.getvalue('userdel')
	user = sql.select_users(id=userdel)
	for u in user:
		username = u[1]
	if sql.delete_user(userdel):
		funct.logging(username, ' has deleted user ', haproxywi=1, login=1)
		print("Ok")
		
		
if form.getvalue('updateuser') is not None:
	email = form.getvalue('email')
	role = form.getvalue('role')
	group = form.getvalue('usergroup')
	new_user = form.getvalue('updateuser')	
	id = form.getvalue('id')	
	activeuser = form.getvalue('activeuser')	
	role_id = sql.get_role_id_by_name(role)
	
	if sql.check_group(group, role_id):			
		if funct.is_admin(level=role_id):
			sql.update_user(new_user, email, role, group, id, activeuser)
			funct.logging(new_user, ' has updated user ', haproxywi=1, login=1)
		else:
			funct.logging(new_user, ' tried to privilege escalation', haproxywi=1, login=1)
			
	
if form.getvalue('updatepassowrd') is not None:
	password = form.getvalue('updatepassowrd')
	id = form.getvalue('id')	
	user = sql.select_users(id=id)
	for u in user:
		username = u[1]
	sql.update_user_password(password, id)
	funct.logging('user '+username, ' has changed password ', haproxywi=1, login=1)
	print("Ok")
		
	
if form.getvalue('newserver') is not None:
	hostname = form.getvalue('servername')	
	ip = form.getvalue('newip')
	group = form.getvalue('newservergroup')
	typeip = form.getvalue('typeip')
	haproxy = form.getvalue('haproxy')
	nginx = form.getvalue('nginx')
	enable = form.getvalue('enable')
	master = form.getvalue('slave')
	cred = form.getvalue('cred')
	page = form.getvalue('page')
	page = page.split("#")[0]
	port = form.getvalue('newport')	
	desc = form.getvalue('desc')		

	if sql.add_server(hostname, ip, group, typeip, enable, master, cred, port, desc, haproxy, nginx):
		from jinja2 import Environment, FileSystemLoader
		env = Environment(loader=FileSystemLoader('templates/'))
		template = env.get_template('ajax/new_server.html')

		template = template.render(groups = sql.select_groups(),
									servers = sql.select_servers(server=ip),
									roles = sql.select_roles(),
									masters = sql.select_servers(get_master_servers=1),
									sshs = sql.select_ssh(),
									page = page)
		print(template)
		funct.logging('a new server '+hostname, ' has created  ', haproxywi=1, login=1)
		
		
if form.getvalue('updatehapwiserver') is not None:
	id = form.getvalue('updatehapwiserver')
	active = form.getvalue('active')
	alert = form.getvalue('alert_en')	
	metrics = form.getvalue('metrics')
	sql.update_hapwi_server(id, alert, metrics, active)
	funct.logging('the server '+name, ' has updated ', haproxywi=1, login=1)
		
	
if form.getvalue('updateserver') is not None:
	name = form.getvalue('updateserver')	
	group = form.getvalue('servergroup')	
	typeip = form.getvalue('typeip')		
	haproxy = form.getvalue('haproxy')		
	nginx = form.getvalue('nginx')		
	enable = form.getvalue('enable')		
	master = form.getvalue('slave')		
	id = form.getvalue('id')	
	cred = form.getvalue('cred')		
	port = form.getvalue('port')	
	desc = form.getvalue('desc')	
		
	if name is None or port is None:
		print(error_mess)
	else:
		sql.update_server(name, group, typeip, enable, master, id, cred, port, desc, haproxy, nginx)
		funct.logging('the server '+name, ' has updated ', haproxywi=1, login=1)
			
			
if form.getvalue('serverdel') is not None:
	serverdel = form.getvalue('serverdel')
	server = sql.select_servers(id=serverdel)
	for s in server:
		hostname = s[1]
	if sql.delete_server(serverdel):
		sql.delete_waf_server(serverdel)
		print("Ok")
		funct.logging(hostname, ' has deleted server with ', haproxywi=1, login=1)
		
		
if form.getvalue('newgroup') is not None:
	newgroup = form.getvalue('groupname')	
	desc = form.getvalue('newdesc')	
	if newgroup is None:
		print(error_mess)
	else:
		if sql.add_group(newgroup, desc):
			from jinja2 import Environment, FileSystemLoader
			env = Environment(loader=FileSystemLoader('templates/ajax/'))
			template = env.get_template('/new_group.html')

			output_from_parsed_template = template.render(groups = sql.select_groups(group=newgroup))
			print(output_from_parsed_template)
			funct.logging('a new group '+newgroup, ' created  ', haproxywi=1, login=1)


if form.getvalue('groupdel') is not None:
	groupdel = form.getvalue('groupdel')
	group = sql.select_groups(id=groupdel)
	for g in group:
		groupname = g[1]
	if sql.delete_group(groupdel):
		print("Ok")
		funct.logging(groupname, ' has deleted group ', haproxywi=1, login=1)

		
if form.getvalue('updategroup') is not None:
	name = form.getvalue('updategroup')
	descript = form.getvalue('descript')	
	id = form.getvalue('id')		
	if name is None:
		print(error_mess)
	else:
		group = sql.select_groups(id=id)
		for g in group:
			groupname = g[1]		
		sql.update_group(name, descript, id)	
		funct.logging('the group '+groupname, ' has update  ', haproxywi=1, login=1)
	
	
if form.getvalue('new_ssh'):
	name = form.getvalue('new_ssh')
	enable = form.getvalue('ssh_enable')	
	group = form.getvalue('new_group')	
	username = form.getvalue('ssh_user')		
	password = form.getvalue('ssh_pass')
	page = form.getvalue('page')
	page = page.split("#")[0]
	if username is None or name is None:
		print(error_mess)
	else:
		if sql.insert_new_ssh(name, enable, group, username, password):
			from jinja2 import Environment, FileSystemLoader
			env = Environment(loader=FileSystemLoader('templates/ajax'))
			template = env.get_template('/new_ssh.html')
			output_from_parsed_template = template.render(groups = sql.select_groups(), sshs = sql.select_ssh(name=name),page=page)
			print(output_from_parsed_template)
			funct.logging(name, ' has created a new SSH credentials  ', haproxywi=1, login=1)
			
			
if form.getvalue('sshdel') is not None:
	fullpath = funct.get_config_var('main', 'fullpath')
	sshdel = form.getvalue('sshdel')
	
	for sshs in sql.select_ssh(id=sshdel):
		ssh_enable = sshs[2]
		name = sshs[1]
		ssh_key_name = fullpath+'/keys/%s.pem' % sshs[1]
				
	if ssh_enable == 1:
		cmd = 'rm -f %s' % ssh_key_name
		try:
			funct.subprocess_execute(cmd)
		except:
			pass
	if sql.delete_ssh(sshdel):
		print("Ok")
		funct.logging(name, ' has deleted the SSH credentials  ', haproxywi=1, login=1)
			
			
if form.getvalue('updatessh'):
	id = form.getvalue('id')
	name = form.getvalue('name')
	enable = form.getvalue('ssh_enable')	
	group = form.getvalue('group')	
	username = form.getvalue('ssh_user')		
	password = form.getvalue('ssh_pass')

	if username is None:
		print(error_mess)
	else:

		fullpath = funct.get_config_var('main', 'fullpath')
		
		for sshs in sql.select_ssh(id=id):
			ssh_enable = sshs[2]
			ssh_key_name = fullpath+'/keys/%s.pem' % sshs[1]
			new_ssh_key_name = fullpath+'/keys/%s.pem' % name
					
		if ssh_enable == 1:
			cmd = 'mv %s %s' % (ssh_key_name, new_ssh_key_name)
			cmd1 = 'chmod 600 %s' % new_ssh_key_name
			try:
				funct.subprocess_execute(cmd)
				funct.subprocess_execute(cmd1)
			except:
				pass
		sql.update_ssh(id, name, enable, group, username, password)
		funct.logging('the SSH '+name, ' has updated credentials ', haproxywi=1, login=1)
		
		
if form.getvalue('ssh_cert'):
	name = form.getvalue('name')
	
	if not os.path.exists(os.getcwd()+'/keys/'):
		os.makedirs(os.getcwd()+'/keys/')
	
	ssh_keys = os.path.dirname(os.getcwd())+'/keys/'+name+'.pem'
	
	try:
		with open(ssh_keys, "w") as conf:
			conf.write(form.getvalue('ssh_cert'))
	except IOError:
		print('<div class="alert alert-danger">Can\'t save ssh keys file. Check ssh keys path in config</div>')
	else:
		print('<div class="alert alert-success">Ssh key was save into: %s </div>' % ssh_keys)
		
	try:
		cmd = 'chmod 600 %s' % ssh_keys
		funct.subprocess_execute(cmd)
	except IOError as e:
		funct.logging('localhost', e.args[0], haproxywi=1)
		
	funct.logging("localhost", " upload a new SSH cert %s" % ssh_keys, haproxywi=1, login=1)
	
	
if form.getvalue('newtelegram'):
	token = form.getvalue('newtelegram')
	channel = form.getvalue('chanel')	
	group = form.getvalue('telegramgroup')	
	page = form.getvalue('page')
	page = page.split("#")[0]

	if token is None or channel is None or group is None:
		print(error_mess)
	else:
		if sql.insert_new_telegram(token, channel, group):
			from jinja2 import Environment, FileSystemLoader
			env = Environment(loader=FileSystemLoader('templates/ajax'))
			template = env.get_template('/new_telegram.html')
			output_from_parsed_template = template.render(groups = sql.select_groups(), telegrams = sql.select_telegram(token=token),page=page)
			print(output_from_parsed_template)	
			funct.logging(channel, ' has created a new Telegram channel ', haproxywi=1, login=1)
			
			
if form.getvalue('telegramdel') is not None:
	telegramdel = form.getvalue('telegramdel')
	telegram = sql.select_telegram(id=telegramdel)
	for t in telegram:
		telegram_name = t[1]
	if sql.delete_telegram(telegramdel):
		print("Ok")
		funct.logging(telegram_name, ' has deleted the Telegram channel ', haproxywi=1, login=1)
		
		
if form.getvalue('updatetoken') is not None:
	token = form.getvalue('updatetoken')
	channel = form.getvalue('updategchanel')	
	group = form.getvalue('updategroup')	
	id = form.getvalue('id')	
	if token is None or channel is None or group is None:
		print(error_mess)
	else:		
		sql.update_telegram(token, channel, group, id)
		funct.logging('group '+group, ' telegram token has updated channel: '+channel, haproxywi=1, login=1)
		
		
if form.getvalue('updatesettings') is not None:
	settings = form.getvalue('updatesettings')
	val = form.getvalue('val')
	if sql.update_setting(settings, val):
		funct.logging('value '+val, ' changed settings '+settings, haproxywi=1, login=1)
		print("Ok")
	