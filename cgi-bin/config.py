#!/usr/bin/env python3
import html
import cgi
import listserv as listhap
import os
import http.cookies
import configparser
import funct
import paramiko
from paramiko import SSHClient
from datetime import datetime
from pytz import timezone

form = cgi.FieldStorage()
serv = form.getvalue('serv')
servNew = form.getvalue('serNew')

funct.head("Edit HAproxy config")
funct.check_config()
funct.check_login()

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)

fullpath = config.get('main', 'fullpath')
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')
time_zone = config.get('main', 'time_zone')

if serv is not None:
	fmt = "%Y-%m-%d.%H:%M:%S"
	now_utc = datetime.now(timezone(time_zone))
	cfg = hap_configs_dir + serv + "-" + now_utc.strftime(fmt) + ".cfg"

funct.chooseServer("config.py#conf", "Edit HAproxy config", "y")

if form.getvalue('serv') is not None and form.getvalue('open') is not None :
	funct.logging(serv, "config.py open config")
	funct.get_config(serv, cfg)
	
	conf = open(cfg, "r")
	print('<a name="conf"></a>')
	print("<h3>Config from %s</h3>" % serv)
	print('<form action="config.py#top" method="post">')
	print('<input type="hidden" value="%s" name="serv">' % serv)
	print('<input type="hidden" value="%s.old" name="oldconfig">' % cfg)
	print('<textarea name="config" rows="35" cols="100">%s</textarea>' % conf.read())
	print('<p>')
	funct.mode_admin("Save and restart")
	print('</p></form>')
	conf.close

	os.system("/bin/sudo /bin/mv %s %s.old" % (cfg, cfg))	

if form.getvalue('serv') is not None and form.getvalue('config') is not None :
	funct.logging(serv, "config.py edited config and restarted service")
	config = form.getvalue('config')
	oldcfg = form.getvalue('oldconfig')

	try:
		with open(cfg, "a") as conf:
			conf.write(config)
	except IOError:
		print("Can't read import config file")

	print("<b>New config was saved as: %s </b></br></br>" % cfg)
	
	funct.upload_and_restart(serv, cfg)
	
	os.system("/bin/diff -ub %s %s >> %slog/config_edit.log" % (oldcfg, cfg, fullpath))
	os.system("/bin/sudo /bin/rm -f " + hap_configs_dir + "*.old")

	print('</br><a href="viewsttats.py?serv=%s" target="_blank" title="View stats">Go to view stats</a> <br />' % serv)
	
funct.footer()