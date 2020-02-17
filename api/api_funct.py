import os
import sys
os.chdir(os.path.dirname(__file__))
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app/'))

from bottle import route, run, template, hook, response, request, post
import sql
import funct


def return_dict_from_out(id, out):
	data = {}
	data[id] = {}
	for k in out:
		if "Ncat:" not in k:
			k = k.split(':')
			data[id][k[0]] = k[1].strip()
		else:
			data[id] = {"error":"Can\'t connect to HAproxy"}
			
	return data
	
	
def check_permit_to_server(id):
	servers = sql.select_servers(id_hostname=id)
	login = request.headers.get('login')
		
	for s in servers:		
		servers = sql.get_dick_permit(username=login, ip=s[2])
		
	return servers
	

def get_server(id):
	data = {}
	try:	
		servers = check_permit_to_server(id)
				
		for s in servers:
			data = {  
				'id':s[0],
				'hostname':s[1],
				'ip':s[2],
				'group':s[3],
				'virt':s[4],
				'enable':s[5],
				'master':s[6],
				'creds':s[7]
			}
	except:
		server = data
	return dict(server=data)
	
	
def get_status(id):
	try:
		servers = check_permit_to_server(id)
		
		for s in servers:
			cmd = 'echo "show info" |nc %s %s -w 1|grep -e "Ver\|CurrConns\|Maxco\|MB\|Uptime:"' % (s[2], sql.get_setting('haproxy_sock_port'))
			
		out = funct.subprocess_execute(cmd)
		data = return_dict_from_out(id, out[0])
		
	except:
		data = {}
		data[id] = {"error":"Cannot find the server"}
		return dict(error=data)
			
	return dict(status=data)
	
	
def get_all_statuses():
	data = {}
	try:
		servers = sql.select_servers()
		login = request.headers.get('login')
		sock_port = sql.get_setting('haproxy_sock_port')
			
		for s in servers:		
			servers = sql.get_dick_permit(username=login)
			
		for s in servers:
			cmd = 'echo "show info" |nc %s %s -w 1|grep -e "Ver\|CurrConns\|Maxco\|MB\|Uptime:"' % (s[2], sock_port)
			data[s[2]] = {}	
			out = funct.subprocess_execute(cmd)
			data[s[2]] = return_dict_from_out(s[1], out[0])
	except:
		data = {"error":"Cannot find the server"}
		return dict(error=data)
			
	return dict(status=data)
	
	
def actions(id, action):
	if action == 'start' or action == 'stop' or action == 'restart':
		try:			
			servers = check_permit_to_server(id)
				
			for s in servers:
				cmd = [ "sudo systemctl %s haproxy" % action ]
				error = funct.ssh_command(s[2], cmd)
				done = error if error else 'done'
					
				data = {'id':s[0],'ip':s[2],'action':action,'hostname':s[1],'status':done}
				
			return dict(status=data)
		except:
			return dict(status='error')
	else:
		return dict(status='wrong action')
		
		
	
def runtime(id):
	data = {}
	try:
		action = request.headers.get('action')
		haproxy_sock = sql.get_setting('haproxy_sock')
		servers = check_permit_to_server(id)	
		cmd = [ 'echo "%s" |sudo socat stdio %s' % (action, haproxy_sock) ]
		
		for s in servers:
			out = funct.ssh_command(s[2], cmd)
		
		data = {}
		data[id] = {}
		sep_data = out.split('\r\n')
		data[id] = {'ouput':sep_data}
		
		return dict(status=data)
	except:
		return dict(status='error')
		
		
def show_backends(id):
	data = {}
	try:
		servers = check_permit_to_server(id)
		
		for s in servers:
			out = funct.show_backends(s[2], ret=1)
			
		data = {id: out}
		
	except:
		data = {}
		data[id] = {"error":"Cannot find the server"}
		return dict(error=data)
			
	return dict(backends=data)		
	
	
def get_config(id):
	data = {}
	try:
		servers = check_permit_to_server(id)
		
		for s in servers:
			cfg = '/tmp/'+s[2]+'.cfg'
			out = funct.get_config(s[2], cfg)
			os.system("sed -i 's/\\n/\n/g' "+cfg)
		try:
			conf = open(cfg, "r")
			config_read = conf.read()
			conf.close
			
		except IOError:
			conf = '<br />Can\'t read import config file'
			
		data = {id: config_read}
		
	except:
		data = {}
		data[id] = {"error":"Cannot find the server"}
		return dict(error=data)
			
	return dict(config=data)
	
	
def upload_config(id):
	data = {}
	body = request.body.getvalue().decode('utf-8')
	save = request.headers.get('action')
	login = request.headers.get('login')
	
	if save == '':
		save = 'save'
	elif save == 'restart':
		save = ''
		
	try:
		servers = check_permit_to_server(id)
		
		for s in servers:
			ip = s[2]
		cfg = '/tmp/'+ip+'.cfg'
		cfg_for_save = hap_configs_dir + ip + "-" + funct.get_data('config') + ".cfg"
		
		try:
			with open(cfg, "w") as conf:
				conf.write(body)
			return_mess = 'config was uploaded'
			os.system("/bin/cp %s %s" % (cfg, cfg_for_save))
			out = funct.upload_and_restart(ip, cfg, just_save=save)
			funct.logging('localhost', " config was uploaded via REST API", login=login)
			
			if out:
				return_mess == out
		except IOError:
			return_mess = "cannot upload config"
			
		data = {id: return_mess}
	except:
		data = {}
		data[id] = {"error":"Cannot find the server"}
		return dict(error=data)
			
	return dict(config=data)	
	
	
def add_to_config(id):
	data = {}
	body = request.body.getvalue().decode('utf-8')
	save = request.headers.get('action')
	hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
	login = request.headers.get('login')
	
	if save == '':
		save = 'save'
	elif save == 'restart':
		save = ''
		
	try:
		servers = check_permit_to_server(id)
		
		for s in servers:
			ip = s[2]
		cfg = '/tmp/'+ip+'.cfg'
		cfg_for_save = hap_configs_dir + ip + "-" + funct.get_data('config') + ".cfg"
		out = funct.get_config(ip, cfg)
		try:
			with open(cfg, "a") as conf:
				conf.write('\n'+body+'\n')
			return_mess = 'section was added to the config'
			os.system("/bin/cp %s %s" % (cfg, cfg_for_save))
			funct.logging('localhost', " section was added via REST API", login=login)
			out = funct.upload_and_restart(ip, cfg, just_save=save)

			if out:
				return_mess = out
		except IOError:
			return_mess = "cannot upload config"
			
		data = {id: return_mess}
	except:
		data[id] = {"error":"Cannot find the server"}
		return dict(error=data)
			
	return dict(config=data)	
	
	
def show_log(id):
	data = {}
	rows = request.headers.get('rows')
	waf = request.headers.get('waf')
	grep = request.headers.get('grep')
	hour = request.headers.get('starthour')
	minut = request.headers.get('startminut')
	hour1 = request.headers.get('endhour')
	minut1 = request.headers.get('endminut')
	
	if rows is None:
		rows = '10'
	if waf is None:
		waf = '0'
	if hour is None:
		hour = '00'
	if minut is None:
		minut = '00'
	if hour1 is None:
		hour1 = '24'
	if minut1 is None:
		minut1 = '00'

	try:
		servers = check_permit_to_server(id)
		
		for s in servers:
			ip = s[2]
	except:
		
		data[id] = {"error":"Cannot find the server"}
		return dict(error=data)
		
	out = funct.show_haproxy_log(ip, rows=rows, waf=str(waf), grep=grep, hour=str(hour), minut=str(minut), hour1=str(hour1), minut1=str(minut1), html=0)
	data = {id: out}

	return dict(log=data)
		
	