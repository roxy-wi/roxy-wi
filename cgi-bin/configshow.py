#!/usr/bin/env python3
import html
import cgi
import os
import funct
import paramiko
import configparser
from datetime import datetime
from pytz import timezone

form = cgi.FieldStorage()
serv = form.getvalue('serv')
servNew = form.getvalue('serNew')

funct.head("Show HAproxy config")
funct.check_config()
funct.check_login()

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)

ssh_keys = config.get('ssh', 'ssh_keys')
ssh_user_name = config.get('ssh', 'ssh_user_name')
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')
haproxy_config_path  = config.get('haproxy', 'haproxy_config_path')
time_zone = config.get('main', 'time_zone')

funct.chooseServer("configshow.py", "Show HAproxy config", "n", onclick="showConfig()")

print('<div id="ajax">')
if form.getvalue('serv') is not None and form.getvalue('open') is not None :
	fmt = "%Y-%m-%d.%H:%M:%S"
	now_utc = datetime.now(timezone(time_zone))
	cfg = hap_configs_dir + serv + "-" + now_utc.strftime(fmt) + ".cfg"
	
	funct.get_config(serv, cfg)
	
	print("<center><h3>Config from %s</h3>" % serv)
	print('<p class="accordion-expand-holder">'
			'<a class="accordion-expand-all ui-button ui-widget ui-corner-all" href="#">Expand all</a>'
		'</p>')
	print('</center>')
	funct.show_config(cfg)
	
	os.system("/bin/rm -f " + cfg)	
	
print('</div>')	
funct.footer()