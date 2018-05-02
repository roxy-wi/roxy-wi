#!/usr/bin/env python3
import html
import cgi
import funct
import sql
from configparser import ConfigParser, ExtendedInterpolation

funct.head("Installation HAProxy")
funct.check_login()
funct.page_for_admin()

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)	
proxy = config.get('main', 'proxy')
serv = ""

print('<script src="/inc/users.js"></script>'
		'<h2>Installation HAProxy</h2>'
		'<table class="overview">'
		'<tr class="overviewHead">'
			'<td class="padding10 first-collumn">Note</td>'
			'<td>Server</td>'
			'<td></td>'
		'</tr>'
		'<tr>'
		'<td class="padding10 first-collumn">'
			'<b>Haproxy-WI will try install haproxy-1.18.5, if it does not work then haproxy-1.15</b>'
		'</td>'
		'<td class="padding10 first-collumn">'
			'<select id="haproxyaddserv">'
				'<option disable selected>Choose server</option>')
funct.choose_only_select(serv)
print('</select>'
		'</td>'
		'<td>'
			'<a class="ui-button ui-widget ui-corner-all" id="install" title="Install HAProxy">Install</a>'
		'</td>'
		'</table>'
		'<div id="ajax"></div>')