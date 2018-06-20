import funct
import os
import cgi
import sql

cgi_path = funct.get_config_var('main', 'cgi_path')
fullpath = funct.get_config_var('main', 'fullpath')
stats_port= funct.get_config_var('haproxy', 'stats_port')
haproxy_config_path  = funct.get_config_var('haproxy', 'haproxy_config_path')
status_command = funct.get_config_var('haproxy', 'status_command')
hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
form = cgi.FieldStorage()

def get_overview():
	listhap = sql.get_dick_permit()
		
	commands = [ "ps -Af |grep [h]aproxy |wc -l" ]
	commands1 = [ "ls -l %s |awk '{ print $6\" \"$7\" \"$8}'" % haproxy_config_path ]

	for server in listhap:
		print('<tr><td class="padding10 first-collumn"><a href="#%s" title="Go to %s status" style="color: #000">%s</a></td><td  class="second-collumn">' % (server[1], server[1], server[1]))
		funct.ssh_command(server[2], commands, server_status="1")
		print('</td><td>')
		if funct.is_admin():
			print('<a id="%s" class="start" title="Start HAproxy service"><img src=/image/pic/start.png alt="start" class="icon"></a>' % server[2])
			print('<a id="%s" class="stop" title="Stop HAproxy service"><img src=/image/pic/stop.png alt="start" class="icon"></a>' % server[2])
			print('<a id="%s" class="restart" title="Restart HAproxy service"><img src=/image/pic/update.png alt="restart" class="icon"></a>' % server[2])
		if funct.is_admin(level = 2):
			print('<a href="/app/configshow.py?serv=%s&open=open#conf"  title="Show config"><img src=/image/pic/show.png alt="show" class="icon"></a>' % server[2])
			print('<a href="/app/config.py?serv=%s&open=open#conf"  title="Edit config"><img src=/image/pic/edit.png alt="edit" class="icon"></a>' % server[2])
			print('<a href="/app/diff.py?serv=%s&open=open#diff"  title="Compare config"><img src=/image/pic/compare.png alt="compare" class="icon"></a>' % server[2])
			print('<a href="/app/map.py?serv=%s&open=open#map"  title="Map listen/frontend/backend"><img src=/image/pic/map.png alt="map" class="icon"></a>' % server[2])
		print('</td><td>')
		funct.ssh_command(server[2], commands1)
		print('</td><td></td></tr>')

def get_overviewServers():
	listhap = sql.get_dick_permit()
	commands = [ "uname -smor", 
				"haproxy -v |head -1", 
				status_command + "|grep Active |awk -F':' '{print $2\":\"$3\":\"$4}' | sed 's/^[ \t]*//'" ]
	commands1 =  [ "top -u haproxy -b -n 1" ]
	for server in sorted(listhap):
		print('<tr><td class="overviewTr first-collumn"><a name="'+server[1]+'"></a><h3 title="IP ' + server[2] + '">' + server[1] + ':</h3></td>')
		print('<td class="overviewTd"><pre style="font-size: 12px;">')
		funct.ssh_command(server[2], commands)
		print('</pre></td><td><pre style="font-size: 12px;">')
		funct.ssh_command(server[2], commands1)
		print('</td><td style="padding: 10px;font-size: 13px;">')
		funct.show_backends(server[2])
		print('</pre></td><td></td></tr>')
	
def get_map(serv):
	from datetime import datetime
	from pytz import timezone
	import networkx as nx
	import matplotlib
	matplotlib.use('Agg')
	import matplotlib.pyplot as plt
	
	date = funct.get_data('config')
	cfg = hap_configs_dir + serv + "-" + date + ".cfg"
	
	print('<center>')
	print("<h3>Map from %s</h3><br />" % serv)
	
	G = nx.DiGraph()
	
	funct.get_config(serv, cfg)	
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Can\'t read import config file</div>')
	
	node = ""
	line_new2 = [1,""]
	i = 1200
	k = 1200
	j = 0
	m = 0
	for line in conf:
		if "listen" in line or "frontend" in line:
			if "stats" not in line:				
				node = line
				i = i - 500	
		if line.find("backend") == 0: 
			node = line
			i = i - 500	
			G.add_node(node,pos=(k,i),label_pos=(k,i+150))
		
		if "bind" in line:
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

		if "server " in line or "use_backend" in line or "default_backend" in line and "stats" not in line:
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
	os.chdir(cgi_path)

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
		
	commands = [ "rm -f "+fullpath+"/map*.png", "mv %s/map.png %s/map%s.png" % (cgi_path, fullpath, date) ]
	funct.ssh_command("localhost", commands)
	print('<img src="/map%s.png" alt="map">' % date)

def show_compare_configs(serv):
	import glob
	left = form.getvalue('left')
	right = form.getvalue('right')
	haproxy_configs_server = funct.get_config_var('configs', 'haproxy_configs_server')
	
	print('<form action="diff.py#diff" method="get">')
	print('<center><h3><span style="padding: 20px;">Choose left</span><span style="padding: 110px;">Choose right</span></h3>')
	
	print('<p><select autofocus required name="left" id="left">')
	print('<option disabled selected>Choose version</option>')
	
	os.chdir(hap_configs_dir)
	
	for files in sorted(glob.glob('*.cfg'), reverse=True):
		ip = files.split("-")
		if serv == ip[0]:
			if left == files:
				selected = 'selected'
			else:
				selected = ''
			print('<option value="%s" %s>%s</option>' % (files, selected, files))

	print('</select>')

	print('<select autofocus required name="right" id="right">')
	print('<option disabled selected>Choose version</option>')
	
	for files in sorted(glob.glob('*.cfg'), reverse=True):
		ip = files.split("-")
		if serv == ip[0]:
			if right == files:
				selected = 'selected'
			else:
				selected = ''
			print('<option value="%s" %s>%s</option>' % (files, selected, files))

	print('</select>')
	print('<input type="hidden" value="%s" name="serv">' % serv)
	print('<input type="hidden" value="open" name="open">')
	print('<a class="ui-button ui-widget ui-corner-all" id="show" title="Compare" onclick="showCompare()">Show</a></p></form></center></center>')
	
def comapre_show():
	import subprocess 
	left = form.getvalue('left')
	right = form.getvalue('right')
	haproxy_configs_server = funct.get_config_var('configs', 'haproxy_configs_server')
	cmd='diff -ub %s%s %s%s' % (hap_configs_dir, left, hap_configs_dir, right)
	
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
	stdout, stderr = p.communicate()
	output = stdout.splitlines()
	
	funct.compare(output)
	print(stderr)