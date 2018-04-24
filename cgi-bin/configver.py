#!/usr/bin/env python3
import html
import cgi
import os
import funct
import sql
from configparser import ConfigParser, ExtendedInterpolation

form = cgi.FieldStorage()
serv = form.getvalue('serv')
configver = form.getvalue('configver')

funct.head("Old Versions HAproxy config")
funct.check_config()
funct.check_login()
funct.page_for_admin(level = 2)

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)

hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')

funct.chooseServer("configver.py#conf", "Old Versions HAproxy config", "y")

if serv is not None and form.getvalue('open') is not None:
	
	print('<center><h3>Choose old version</h3>')
	print('<form action="configver.py#conf" method="get">')
	print('<p><select autofocus required name="configver">')
	print('<option disabled selected>Choose version</option>')
	
	import glob

	os.chdir(hap_configs_dir)

	for files in sorted(glob.glob('*.cfg')):
		ip = files.split("-")
		if serv == ip[0]:
			if configver == files:
				selected = 'selected'
			else:
				selected = ''
			print('<option value="%s" %s>%s</option>' % (files, selected, files))

	print('</select>')
	print('<input type="hidden" value="%s" name="serv">' % serv)
	print('<input type="hidden" value="open" name="open">')
	print('<button type="submit" value="Select" name="Select">Select</button></form>') 

	Select = form.getvalue('Select')

	if Select is not None:
		
		configver = form.getvalue('configver')
		funct.logging(serv, "open old config %s" % configver)

		print("<h3>Config from %s, and version is: %s</h3>" % (serv, configver))
		print('<form action="configver.py#conf" method="get">')
		print('<input type="hidden" value="%s" name="serv">' % serv)
		print('<input type="hidden" value="%s" name="configver">' % configver)
		print('<input type="hidden" value="1" name="config">')
		print('<a name="conf"></a>')
		print('<p class="accordion-expand-holder">'
				'<a class="accordion-expand-all ui-button ui-widget ui-corner-all" href="#">Expand all</a>'
			'</p></center>')
		funct.show_config(configver)
		print('<center><p>')
		funct.get_button("Just save", value="save")
		funct.get_button("Upload and restart")
		print('</p></form></center>')


if form.getvalue('serv') is not None and form.getvalue('config') is not None:
	configver = form.getvalue('configver')
	configver = hap_configs_dir + configver
	save = form.getvalue('save')
	
	funct.logging(serv, "configver.py upload old config %s" % configver)
	
	print("<center><b>Uploaded old config ver: %s </b></br></br></center>" % configver)

	MASTERS = sql.is_master(serv)
	for master in MASTERS:
		if master[0] != None:
			funct.upload_and_restart(master[0], configver, just_save=save)
			
	funct.upload_and_restart(serv, configver, just_save=save)

	print('</br><a href="viewsttats.py?serv=%s" target="_blank" title="View stats">Go to view stats</a> <br />' % serv)
	
funct.footer()
