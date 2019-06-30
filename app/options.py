#!/usr/bin/env python3
# -*- coding: utf-8 -*-"
import cgi
import os, sys
import funct
import sql
import ovw

form = cgi.FieldStorage()
serv = form.getvalue('serv')
act = form.getvalue('act')
	
print('Content-type: text/html\n')

if act == "checkrestart":
	servers = sql.get_dick_permit(ip=serv)
	for server in servers:
		if server != "":
			print("ok")
			sys.exit()
	sys.exit()

if form.getvalue('token') is None:
	print("What the fuck?! U r hacker Oo?!")
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
		funct.logging("local", "users.py#ssh upload new ssh cert %s" % ssh_keys)
	except:
		pass
			
if serv and form.getvalue('ssl_cert'):
	cert_local_dir = funct.get_config_var('main', 'cert_local_dir')
	cert_path = sql.get_setting('cert_path')
	
	if not os.path.exists(cert_local_dir):
		os.makedirs(cert_local_dir)
	
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
	
if form.getvalue('backend') is not None:
	funct.show_backends(serv)
	
if form.getvalue('ip') is not None and serv is not None:
	commands = [ "sudo ip a |grep inet |egrep -v  '::1' |awk '{ print $2  }' |awk -F'/' '{ print $1  }'" ]
	funct.ssh_command(serv, commands, ip="1")
	
if form.getvalue('showif'):
	commands = ["sudo ip link|grep 'UP' | awk '{print $2}'  |awk -F':' '{print $1}'"]
	funct.ssh_command(serv, commands, ip="1")
	
if form.getvalue('action_hap') is not None and serv is not None:
	action = form.getvalue('action_hap')
	
	if funct.check_haproxy_config(serv):
		commands = [ "sudo systemctl %s haproxy" % action ]
		funct.ssh_command(serv, commands)		
		print("HAproxy was %s" % action)
	else:
		print("Bad config, check please")
	
if form.getvalue('action_waf') is not None and serv is not None:
	serv = form.getvalue('serv')
	action = form.getvalue('action_waf')

	commands = [ "sudo systemctl %s waf" % action ]
	funct.ssh_command(serv, commands)		
	
if act == "overview":
	ovw.get_overview()
	
if act == "overviewwaf":
	ovw.get_overviewWaf(form.getvalue('page'))
	
if act == "overviewServers":
	ovw.get_overviewServers()
	
if form.getvalue('action'):
	import requests
	from requests_toolbelt.utils import dump
	
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
	from requests_toolbelt.utils import dump
	
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
	print(data.decode('utf-8'))

if serv is not None and form.getvalue('rows') is not None:
	rows = form.getvalue('rows')
	waf = form.getvalue('waf')
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

	syslog_server_enable = sql.get_setting('syslog_server_enable')
	if syslog_server_enable is None or syslog_server_enable == "0":
		local_path_logs = sql.get_setting('local_path_logs')
		syslog_server = serv	
		commands = [ "sudo cat %s| awk '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s  %s %s" % (local_path_logs, date, date1, rows, grep_act, grep) ]		
	else:
		commands = [ "sudo cat /var/log/%s/syslog.log | sed '/ %s:00/,/ %s:00/! d' |tail -%s  %s %s" % (serv, date, date1, rows, grep_act, grep) ]
		syslog_server = sql.get_setting('syslog_server')
	
	if waf == "1":
		local_path_logs = '/var/log/modsec_audit.log'
		commands = [ "sudo cat %s |tail -%s  %s %s" % (local_path_logs, rows, grep_act, grep) ]	
		
	funct.ssh_command(syslog_server, commands, show_log="1")
	
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

	funct.show_log(output)
	print(stderr)
		
if form.getvalue('viewlogs') is not None:
	viewlog = form.getvalue('viewlogs')
	log_path = funct.get_config_var('main', 'log_path')
	rows = form.getvalue('rows2')
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

	cmd="cat %s| awk '$3>\"%s:00\" && $3<\"%s:00\"' |tail -%s  %s %s" % (log_path + viewlog, date, date1, rows, grep_act, grep)
	output, stderr = funct.subprocess_execute(cmd)

	funct.show_log(output)
	print(stderr)
		
if serv is not None and act == "showMap":
	ovw.get_map(serv)
	
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
			
	funct.ssh_command(serv, command, show_log="1")
	action = 'edit.py ' + enable + ' ' + backend
	funct.logging(serv, action)

if act == "showCompareConfigs":
	import glob
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/ajax'))
	template = env.get_template('/show_compare_configs.html')
	left = form.getvalue('left')
	right = form.getvalue('right')
	
	template = template.render(serv=serv, right=right, left=left, return_files=funct.get_files())									
	print(template)
	
if serv is not None and form.getvalue('right') is not None:
	from jinja2 import Environment, FileSystemLoader
	left = form.getvalue('left')
	right = form.getvalue('right')
	hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
	cmd='diff -ub %s%s %s%s' % (hap_configs_dir, left, hap_configs_dir, right)	
	env = Environment(loader=FileSystemLoader('templates/ajax'),extensions=['jinja2.ext.loopcontrols', "jinja2.ext.do"])
	template = env.get_template('compare.html')
	
	output, stderr = funct.subprocess_execute(cmd)
	template = template.render(stdout=output)	
	
	print(template)
	print(stderr)
	
if serv is not None and act == "configShow":
	hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
	
	if form.getvalue('configver') is None:	
		cfg = hap_configs_dir + serv + "-" + funct.get_data('config') + ".cfg"
		funct.get_config(serv, cfg)
	else: 
		cfg = hap_configs_dir + form.getvalue('configver')
			
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Can\'t read import config file</div>')
		
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/ajax'),extensions=['jinja2.ext.loopcontrols'])
	template = env.get_template('config_show.html')
	
	template = template.render(conf=conf, view=form.getvalue('view'), serv=serv, configver=form.getvalue('configver'), role=funct.is_admin(level=2))											
	print(template)
	
	if form.getvalue('configver') is None:
		os.system("/bin/rm -f " + cfg)	
		
if form.getvalue('master'):
	master = form.getvalue('master')
	slave = form.getvalue('slave')
	interface = form.getvalue('interface')
	vrrpip = form.getvalue('vrrpip')
	tmp_config_path = sql.get_setting('tmp_config_path')
	script = "install_keepalived.sh"
	
	if form.getvalue('hap') == "1":
		funct.install_haproxy(master)
		funct.install_haproxy(slave)
		
	if form.getvalue('syn_flood') == "1":
		funct.syn_flood_protect(master)
		funct.syn_flood_protect(slave)
	
	os.system("cp scripts/%s ." % script)
		
	error = str(funct.upload(master, tmp_config_path, script))
	if error:
		print('error: '+error)
		sys.exit()
	funct.upload(slave, tmp_config_path, script)

	funct.ssh_command(master, ["sudo chmod +x "+tmp_config_path+script, tmp_config_path+script+" MASTER "+interface+" "+vrrpip])
	funct.ssh_command(slave, ["sudo chmod +x "+tmp_config_path+script, tmp_config_path+script+" BACKUP "+interface+" "+vrrpip])
			
	os.system("rm -f %s" % script)
	sql.update_server_master(master, slave)
	
if form.getvalue('masteradd'):
	master = form.getvalue('masteradd')
	slave = form.getvalue('slaveadd')
	interface = form.getvalue('interfaceadd')
	vrrpip = form.getvalue('vrrpipadd')
	kp = form.getvalue('kp')
	tmp_config_path = sql.get_setting('tmp_config_path')
	script = "add_vrrp.sh"
	
	os.system("cp scripts/%s ." % script)
		
	error = str(funct.upload(master, tmp_config_path, script))
	if error:
		print('error: '+error)
		sys.exit()
	funct.upload(slave, tmp_config_path, script)
	
	funct.ssh_command(master, ["sudo chmod +x "+tmp_config_path+script, tmp_config_path+script+" MASTER "+interface+" "+vrrpip+" "+kp])
	funct.ssh_command(slave, ["sudo chmod +x "+tmp_config_path+script, tmp_config_path+script+" BACKUP "+interface+" "+vrrpip+" "+kp])
			
	os.system("rm -f %s" % script)
	
if form.getvalue('haproxyaddserv'):
	funct.install_haproxy(form.getvalue('haproxyaddserv'), syn_flood=form.getvalue('syn_flood'))
	
if form.getvalue('installwaf'):
	funct.waf_install(form.getvalue('installwaf'))
	
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
		
if form.getvalue('metrics'):
	from datetime import timedelta
	from bokeh.plotting import figure, output_file, show
	from bokeh.models import ColumnDataSource, HoverTool, DatetimeTickFormatter, DatePicker
	from bokeh.layouts import widgetbox, gridplot
	from bokeh.models.widgets import Button, RadioButtonGroup, Select
	import pandas as pd
	import http.cookies
		
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')	
	servers = sql.select_servers_metrics(user_id.value)
	servers = sorted(servers)
	
	p = {}
	for serv in servers:
		serv = serv[0]
		p[serv] = {}
		metric = sql.select_metrics(serv)
		metrics = {}
		
		for i in metric:
			rep_date = str(i[5])
			metrics[rep_date] = {}
			metrics[rep_date]['server'] = str(i[0])
			metrics[rep_date]['curr_con'] = str(i[1])
			metrics[rep_date]['curr_ssl_con'] = str(i[2])
			metrics[rep_date]['sess_rate'] = str(i[3])
			metrics[rep_date]['max_sess_rate'] = str(i[4])

		df = pd.DataFrame.from_dict(metrics, orient="index")
		df = df.fillna(0)
		df.index = pd.to_datetime(df.index)
		df.index.name = 'Date'
		df.sort_index(inplace=True)
		source = ColumnDataSource(df)
		
		output_file("templates/metrics_out.html", mode='inline')
		
		x_min = df.index.min() - pd.Timedelta(hours=1)
		x_max = df.index.max() + pd.Timedelta(minutes=1)

		p[serv] = figure(
			tools="pan,box_zoom,reset,xwheel_zoom",		
			title=metric[0][0],
			x_axis_type="datetime", y_axis_label='Connections',
			x_range = (x_max.timestamp()*1000-60*100000, x_max.timestamp()*1000)
			)
			
		hover = HoverTool(
			tooltips=[
				("Connections", "@curr_con"),
				("SSL connections", "@curr_ssl_con"),
				("Sessions rate", "@sess_rate")
			],
			mode='mouse'
		)
		
		p[serv].ygrid.band_fill_color = "#f3f8fb"
		p[serv].ygrid.band_fill_alpha = 0.9
		p[serv].y_range.start = 0
		p[serv].y_range.end = int(df['curr_con'].max()) + 150
		p[serv].add_tools(hover)
		p[serv].title.text_font_size = "20px"						
		p[serv].line("Date", "curr_con", source=source, alpha=0.5, color='#5cb85c', line_width=2, legend="Conn")
		p[serv].line("Date", "curr_ssl_con", source=source, alpha=0.5, color="#5d9ceb", line_width=2, legend="SSL con")
		p[serv].line("Date", "sess_rate", source=source, alpha=0.5, color="#33414e", line_width=2, legend="Sessions")
		p[serv].legend.orientation = "horizontal"
		p[serv].legend.location = "top_left"
		p[serv].legend.padding = 5

	plots = []
	for key, value in p.items():
		plots.append(value)
		
	grid = gridplot(plots, ncols=2, plot_width=800, plot_height=250, toolbar_location = "left", toolbar_options=dict(logo=None))
	show(grid)
	
if form.getvalue('waf_metrics'):
	from datetime import timedelta
	from bokeh.plotting import figure, output_file, show
	from bokeh.models import ColumnDataSource, HoverTool, DatetimeTickFormatter, DatePicker
	from bokeh.layouts import widgetbox, gridplot
	from bokeh.models.widgets import Button, RadioButtonGroup, Select
	import pandas as pd
	import http.cookies
		
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')	
	servers = sql.select_waf_servers_metrics(user_id.value)
	servers = sorted(servers)
	
	p = {}
	for serv in servers:
		serv = serv[0]
		p[serv] = {}
		metric = sql.select_waf_metrics(serv)
		metrics = {}
		
		for i in metric:
			rep_date = str(i[2])
			metrics[rep_date] = {}
			metrics[rep_date]['conn'] = str(i[1])

		df = pd.DataFrame.from_dict(metrics, orient="index")
		df = df.fillna(0)
		df.index = pd.to_datetime(df.index)
		df.index.name = 'Date'
		df.sort_index(inplace=True)
		source = ColumnDataSource(df)
		
		output_file("templates/metrics_waf_out.html", mode='inline')
		
		x_min = df.index.min() - pd.Timedelta(hours=1)
		x_max = df.index.max() + pd.Timedelta(minutes=1)

		p[serv] = figure(
			tools="pan,box_zoom,reset,xwheel_zoom",
			title=metric[0][0],
			x_axis_type="datetime", y_axis_label='Connections',
			x_range = (x_max.timestamp()*1000-60*100000, x_max.timestamp()*1000)
			)
			
		hover = HoverTool(
			tooltips=[
				("Connections", "@conn"),
			],
			mode='mouse'
		)
		
		p[serv].ygrid.band_fill_color = "#f3f8fb"
		p[serv].ygrid.band_fill_alpha = 0.9
		p[serv].y_range.start = 0
		p[serv].y_range.end = int(df['conn'].max()) + 150
		p[serv].add_tools(hover)
		p[serv].title.text_font_size = "20px"				
		p[serv].line("Date", "conn", source=source, alpha=0.5, color='#5cb85c', line_width=2, legend="Conn")
		p[serv].legend.orientation = "horizontal"
		p[serv].legend.location = "top_left"
		p[serv].legend.padding = 5
		
	plots = []
	for key, value in p.items():
		plots.append(value)
		
	grid = gridplot(plots, ncols=2, plot_width=800, plot_height=250, toolbar_location = "left", toolbar_options=dict(logo=None))
	show(grid)
	
if form.getvalue('get_hap_v'):
	output = funct.check_haproxy_version(serv)
	print(output)
	
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
	list_name = form.getvalue('bwlists_create').split('.')[0]
	list_name += '.lst'
	list = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')+"/"+form.getvalue('group')+"/"+form.getvalue('color')+"/"+list_name
	try:
		open(list, 'a').close()
		print('<div class="alert alert-success" style="margin:0">'+form.getvalue('color')+' list was created</div>')
	except IOError as e:
		print('<div class="alert alert-danger" style="margin:0">Cat\'n create new '+form.getvalue('color')+' list. %s </div>' % e)
		
if form.getvalue('bwlists_save'):
	list = os.path.dirname(os.getcwd())+"/"+sql.get_setting('lists_path')+"/"+form.getvalue('group')+"/"+form.getvalue('color')+"/"+form.getvalue('bwlists_save')
	try:
		with open(list, "w") as file:
			file.write(form.getvalue('bwlists_content'))
	except IOError as e:
		print('<div class="alert alert-danger" style="margin:0">Cat\'n save '+form.getvalue('color')+' list. %s </div>' % e)
	
	servers = sql.get_dick_permit()
	path = sql.get_setting('haproxy_dir')+"/"+form.getvalue('color')
	
	for server in servers:
		funct.ssh_command(server[2], ["sudo mkdir "+path])
		error = funct.upload(server[2], path+"/"+form.getvalue('bwlists_save'), list, dir='fullpath')
		if error:
			print('<div class="alert alert-danger">Upload fail: %s</div>' % error)			
		else:
			print('<div class="alert alert-success" style="margin:10px">Edited '+form.getvalue('color')+' list was uploaded to '+server[1]+'</div>')
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

	l = ldap.initialize("ldap://"+server+':'+port)
	try:
		l.protocol_version = ldap.VERSION3
		l.set_option(ldap.OPT_REFERRALS, 0)

		bind = l.simple_bind_s(user, password)

		criteria = "(&(objectClass=user)(sAMAccountName="+username+"))"
		attributes = [ldap_search_field]
		result = l.search_s(ldap_base, ldap.SCOPE_SUBTREE, criteria, attributes)

		results = [entry for dn, entry in result if isinstance(entry, dict)]
		try:
			print('["'+results[0][ldap_search_field][0].decode("utf-8")+'","'+domain+'"]')
		except:
			print('error: user not found')
	finally:
		l.unbind()