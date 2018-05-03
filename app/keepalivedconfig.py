#!/usr/bin/env python3
# -*- coding: utf-8 -*-"
import html
import cgi
import os
import http.cookies
from configparser import ConfigParser, ExtendedInterpolation
import funct
import sql
import codecs

form = cgi.FieldStorage()
serv = form.getvalue('serv')
servNew = form.getvalue('serNew')

funct.head("Edit Running Keepalived config")
funct.check_config()
funct.check_login()
funct.page_for_admin(level = 1)

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)

log_path = config.get('main', 'log_path')
kp_save_configs_dir = config.get('configs', 'kp_save_configs_dir')

print('<h2>Edit Running Keepalived config</h2>'
		'<center>'
			'<h3>Choose server</h3>'
			'<form action="keepalivedconfig.py" method="get">'
				'<select name="serv">')
				
SERVERS = sql.is_master("123", master_slave=1)
for server in SERVERS:
	if serv == server[1]:
		selected = "selected"
	else:
		selected = ""
	print('<option value="%s" %s>%s</option>' % (server[1],selected, server[0]))
	if serv == server[3]:
		selected = "selected"
	else:
		selected = ""
	print('<option value="%s" %s>%s</option>' % (server[3], selected, server[2]))
	
print('</select>')
funct.get_button("Open", value="open")
print('</form>')

if serv is not None:
	cfg = kp_save_configs_dir+ serv + '-' + funct.get_data('config') + '.conf'

if form.getvalue('serv') is not None and form.getvalue('open') is not None :
	
	try:
		funct.logging(serv, "keepalivedconfig.py open config")
	except:
		pass
	funct.get_config(serv, cfg, keepalived=1)
	
	try:
		conf = open(cfg, "r",encoding='utf-8', errors='ignore')
	except IOError:
		print('<div class="alert alert-danger">Can\'t read import config file</div>')

	print("<center><h3>Config from %s</h3>" % serv)
	print('<form action="" method="get">')
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
		funct.logging(serv, "keepalivedconfig.py edited config")
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

	print('<center><br><div class="alert alert-info">New config was saved as: %s </div></center>' % cfg)
			
	funct.upload_and_restart(serv, cfg, just_save=save, keepalived=1)
	
	
	os.system("/bin/diff -ub %s %s >> %s/config_edit-%s.log" % (oldcfg, cfg, log_path, funct.get_data('logs')))
	os.system("/bin/rm -f kp_config/*.old")

	print('</br><a href="viewsttats.py?serv=%s" target="_blank" title="View stats">Go to view stats</a> <br />' % serv)
	
funct.footer()