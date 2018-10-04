import funct
import os
import sql
import asyncio
import http.cookies
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/ajax'),extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'])
cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
user_id = cookie.get('uuid')
haproxy_sock_port = sql.get_setting('haproxy_sock_port')
listhap = sql.get_dick_permit()
servers = []
server_status = ()

async def async_get_overview(serv1, serv2):
	haproxy_config_path  = sql.get_setting('haproxy_config_path')
	commands = [ "ls -l %s |awk '{ print $6\" \"$7\" \"$8}'" % haproxy_config_path ]
	commands1 = [ "ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l" ]
	
	cmd = 'echo "show info" |nc %s %s |grep -e "Process_num"' % (serv2, haproxy_sock_port)
	server_status = (serv1, serv2, funct.server_status(funct.subprocess_execute(cmd)), funct.ssh_command(serv2, commands), funct.ssh_command(serv2, commands1))
	return server_status

async def get_runner_overview():
	template = env.get_template('overview.html')
	futures = [async_get_overview(server[1], server[2]) for server in listhap]
	for i, future in enumerate(asyncio.as_completed(futures)):
		result = await future
		servers.append(result)
	servers_sorted = sorted(servers, key=funct.get_key)
	template = template.render(service_status=servers_sorted, role=sql.get_user_role_by_uuid(user_id.value))
	print(template)

def get_overview():
	ioloop = asyncio.get_event_loop()
	ioloop.run_until_complete(get_runner_overview())
	ioloop.close()

async def async_get_overviewWaf(serv1, serv2):
	haproxy_dir  = sql.get_setting('haproxy_dir')
	commands = [ "ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l" ]
	commands1 = [ "cat %s/waf/modsecurity.conf  |grep SecRuleEngine |grep -v '#' |awk '{print $2}'" % haproxy_dir ]
	
	server_status = (serv1,serv2, funct.ssh_command(serv2, commands), funct.ssh_command(serv2, commands1).strip(), sql.select_waf_metrics_enable_server(serv2))
	return server_status

async def get_runner_overviewWaf(url):
	template = env.get_template('overivewWaf.html')
	
	futures = [async_get_overviewWaf(server[1], server[2]) for server in listhap]
	for i, future in enumerate(asyncio.as_completed(futures)):
		result = await future
		servers.append(result)
	servers_sorted = sorted(servers, key=funct.get_key)
	template = template.render(service_status=servers_sorted, role=sql.get_user_role_by_uuid(user_id.value), url=url)
	print(template)

def get_overviewWaf(url):
	ioloop = asyncio.get_event_loop()
	ioloop.run_until_complete(get_runner_overviewWaf(url))
	ioloop.close()

async def async_get_overviewServers(serv1, serv2, desc):
	commands =  [ "top -u haproxy -b -n 1" ]
	cmd = 'echo "show info" |nc %s %s |grep -e "Ver\|CurrConns\|SessRate\|Maxco\|MB\|Uptime:"' % (serv2, haproxy_sock_port)
	out = funct.subprocess_execute(cmd)
	out1 = ""
	
	for k in out:
		if "Ncat: Connection refused." not in k:
			for r in k:
				out1 += r
				out1 += "<br />"
		else:
			out1 = "Can\'t connect to HAproxy"
	server_status = (serv1,serv2, out1, funct.ssh_command(serv2, commands),funct.show_backends(serv2, ret=1), desc)
	return server_status
	
async def get_runner_overviewServers():
	template = env.get_template('overviewServers.html')	
	
	futures = [async_get_overviewServers(server[1], server[2], server[11]) for server in listhap]
	for i, future in enumerate(asyncio.as_completed(futures)):
		result = await future
		servers.append(result)
	servers_sorted = sorted(servers, key=funct.get_key)
	template = template.render(service_status=servers_sorted)
	print(template)	
	
def get_overviewServers():
	ioloop = asyncio.get_event_loop()
	ioloop.run_until_complete(get_runner_overviewServers())
	ioloop.close()
	
def get_map(serv):
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
	print("<h3>Map from %s</h3><br />" % serv)
	
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
	i,k  = 1200, 1200
	j, m = 0, 0
	for line in conf:
		if line.startswith('listen') or line.startswith('frontend'):
			if "stats" not in line:				
				node = line
				i = i - 500	
		if line.find("backend") == 0: 
			node = line
			i = i - 500	
			G.add_node(node,pos=(k,i),label_pos=(k,i+150))
		
		if "bind" in line or (line.startswith('listen') and ":" in line) or (line.startswith('frontend') and ":" in line):
			try:
				bind = line.split(":")
				if stats_port not in bind[1]:
					bind[1] = bind[1].strip(' ')
					bind = bind[1].split("crt")
					node = node.strip(' \t\n\r')
					node = node + ":" + bind[0]
					G.add_node(node,pos=(k,i),label_pos=(k,i+150))
			except:
				pass

		if "server " in line or "use_backend" in line or "default_backend" in line and "stats" not in line and "#" not in line:
			if "timeout" not in line and "default-server" not in line and "#" not in line and "stats" not in line:
				i = i - 300
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
					G.add_node(line_new[0],pos=(k+250,i-350),label_pos=(k+225,i-100))
				else:
					G.add_node(line_new[0],pos=(k-250,i-50),label_pos=(k-225,i+180))

				if line_new2[1] != "":	
					G.add_edge(node, line_new[0], port=line_new2[1])
				else:
					G.add_edge(node,line_new[0])

	os.system("/bin/rm -f " + cfg)	

	pos=nx.get_node_attributes(G,'pos')
	pos_label=nx.get_node_attributes(G,'label_pos')
	edge_labels = nx.get_edge_attributes(G,'port')
	
	try:
		plt.figure(10,figsize=(9.5,15))
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