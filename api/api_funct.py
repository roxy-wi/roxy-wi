import os
import sys
os.chdir(os.path.dirname(__file__))
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app/'))

from bottle import route, run, template, hook, response, request
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
				'creds':s[7],
				'alert':s[8],
				'metrics':s[9]
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
		
		
	