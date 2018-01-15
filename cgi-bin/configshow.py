#!/usr/bin/env python3
import html
import cgi
import os
import funct
import paramiko
import configparser
from paramiko import SSHClient
from datetime import datetime
from pytz import timezone

form = cgi.FieldStorage()
serv = form.getvalue('serv')
servNew = form.getvalue('serNew')

funct.head("Show HAproxy config")
funct.check_config()

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)

ssh_keys = config.get('ssh', 'ssh_keys')
ssh_user_name = config.get('ssh', 'ssh_user_name')
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')
haproxy_config_path  = config.get('haproxy', 'haproxy_config_path')

if serv is not None:
	fmt = "%Y-%m-%d.%H:%M:%S"
	now_utc = datetime.now(timezone('Asia/Almaty'))
	cfg = hap_configs_dir + serv + "-" + now_utc.strftime(fmt) + ".cfg"

funct.chooseServer("configshow.py#conf", "Show HAproxy config", "n")

if form.getvalue('serv') is not None and form.getvalue('open') is not None :
	funct.get_config(serv, cfg)
	
	conf = open(cfg, "r")
	print('<a name="conf"></a>')
	print("<h3>Config from %s</h3>" % serv)
	print('<textarea class="ro" readonly name="config" rows="35" cols="100"> %s </textarea>' % conf.read())
	print('<center><h3><a href="#top" title="UP">UP</a></center>')
	conf.close

	os.system("/bin/sudo /bin/rm -f " + cfg)	
	
funct.footer()