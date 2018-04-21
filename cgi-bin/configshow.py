#!/usr/bin/env python3
import html
import cgi
import os
import funct
import paramiko
from configparser import ConfigParser, ExtendedInterpolation
from datetime import datetime
from pytz import timezone

form = cgi.FieldStorage()
serv = form.getvalue('serv')

funct.head("Show HAproxy config")
funct.check_config()
funct.check_login()

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)

ssh_keys = config.get('ssh', 'ssh_keys')
ssh_user_name = config.get('ssh', 'ssh_user_name')
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')
haproxy_config_path  = config.get('haproxy', 'haproxy_config_path')

funct.chooseServer("configshow.py", "Show HAproxy config", "n", onclick="showConfig()")

print('<div id="ajax">')
if serv is not None and form.getvalue('open') is not None :
	
	cfg = hap_configs_dir + serv + "-" + funct.get_data('config') + ".cfg"
	
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