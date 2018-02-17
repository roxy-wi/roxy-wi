#!/usr/bin/env python3
import html
import cgi
import os
import funct
import configparser
from datetime import datetime
from pytz import timezone
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

form = cgi.FieldStorage()
serv = form.getvalue('serv')
servNew = form.getvalue('serNew')

funct.head("Show HAproxy config")
funct.check_config()
funct.check_login()

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)
time_zone = config.get('main', 'time_zone')
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')
haproxy_config_path  = config.get('haproxy', 'haproxy_config_path')
stats_port= config.get('haproxy', 'stats_port')
fullpath = config.get('main', 'fullpath')

if serv is not None:
	fmt = "%Y-%m-%d.%H:%M:%S"
	now_utc = datetime.now(timezone(time_zone))
	cfg = hap_configs_dir + serv + "-" + now_utc.strftime(fmt) + ".cfg"

funct.chooseServer("map.py", "Show HAproxy map", "n")

def is_neighbors(G, neighbor):
	for line in nx.generate_edgelist(G, data=False):
		if neighbor in line:
			return True
			break

if form.getvalue('serv') is not None and form.getvalue('open') is not None :	
	print('<a name="map"></a>')
	print("<h3>Map from %s</h3><br />" % serv)
	
	G = nx.DiGraph()
	
	funct.get_config(serv, cfg)	
	conf = open(cfg, "r")
	
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
			bind = line.split(":")
			if stats_port not in bind[1]:
				bind[1] = bind[1].strip(' ')
				bind = bind[1].split("crt")
				node = node.strip(' \t\n\r')
				node = node + ":" + bind[0]
				G.add_node(node,pos=(k,i),label_pos=(k,i+150))

		if "server " in line or "use_backend" in line or "default_backend" in line and "stats" not in line:
			if "timeout" not in line and "default-server" not in line and "#use_backend" not in line and "stats" not in line:
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
	os.chdir("%s/cgi-bin/" % fullpath)

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
		print("!!! There was an issue, " + str(e))
		
	commands = [ "mv %s/cgi-bin/map.png %s" % (fullpath, fullpath)]
	funct.ssh_command("localhost", commands)
	print('<img src="/map.png" alt="map">')
		
funct.footer()