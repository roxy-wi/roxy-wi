#!/usr/bin/env python3
import html
import cgi
import os
import http.cookies
from configparser import ConfigParser, ExtendedInterpolation
import funct
import sql

form = cgi.FieldStorage()
serv = form.getvalue('serv')
servNew = form.getvalue('serNew')

funct.head("Edit HAproxy config")
funct.check_config()
funct.check_login()
funct.page_for_admin(level = 1)

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)

log_path = config.get('main', 'log_path')
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')

funct.chooseServer("config.py", "Edit HAproxy config", "y")

if serv is not None:
	cfg = hap_configs_dir + serv + "-" + funct.get_data('config') + ".cfg"

if form.getvalue('serv') is not None and form.getvalue('open') is not None :
	
	try:
		funct.logging(serv, "config.py open config")
	except:
		pass
	funct.get_config(serv, cfg)
	
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Can\'t read import config file</div>')

	print("<center><h3>Config from %s</h3>" % serv)
	print('<form action="config.py" method="get">')
	print('<input type="hidden" value="%s" name="serv">' % serv)
	print('<input type="hidden" value="%s.old" name="oldconfig">' % cfg)
	print('<textarea name="config" class="config" rows="35" cols="100">%s</textarea>' % conf.read())
	print('<p>')
	funct.get_button("Just save", value="save")
	funct.get_button("Save and restart")
	print('</p></form>')
	conf.close

	os.system("/bin/mv %s %s.old" % (cfg, cfg))	

if form.getvalue('serv') is not None and form.getvalue('config') is not None:
	try:
		funct.logging(serv, "config.py edited config")
	except:
		pass
		
	config = form.getvalue('config')
	oldcfg = form.getvalue('oldconfig')
	save = form.getvalue('save')

	try:
		with open(cfg, "a") as conf:
			conf.write(config)
	except IOError:
		print("Can't read import config file")

	print('<center><div class="alert alert-info">New config was saved as: %s </div></center>' % cfg)
	
	
	MASTERS = sql.is_master(serv)
	for master in MASTERS:
		if master[0] != None:
			funct.upload_and_restart(master[0], cfg, just_save=save)
		
	funct.upload_and_restart(serv, cfg, just_save=save)
	
	
	os.system("/bin/diff -ub %s %s >> %s/config_edit-%s.log" % (oldcfg, cfg, log_path, funct.get_data('logs')))
	os.system("/bin/rm -f " + hap_configs_dir + "*.old")

	print('</br><a href="viewsttats.py?serv=%s" target="_blank" title="View stats">Go to view stats</a> <br />' % serv)
	
funct.footer()