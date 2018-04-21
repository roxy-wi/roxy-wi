#!/usr/bin/env python3
import html
import cgi
import sys
import os
import funct
from configparser import ConfigParser, ExtendedInterpolation

funct.head("Admin area: View settings")
funct.check_config()
funct.check_login()
funct.page_for_admin()

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)
fullpath = config.get('main', 'fullpath')

print('<h2>Admin area: View settings</h2>'
		'<div id="ajax">'
			'<h3 style="padding-left: 30px; width:inherit; margin: 0" class="overviewHead padding10">Only view, edit you can here: {fullpath}/haproxy-webintarface.config</h3>'
			'<pre>'.format(fullpath=fullpath))

for section_name in config.sections():
    print('Section:', section_name)
    #print('  Options:', config.options(section_name))
    for name, value in config.items(section_name):
        print('  {} = {}'.format(name, value))
    print()

print('</div>')

funct.footer()