#!/usr/bin/env python3
import os, sys 
import configparser

path_config = "/opt/haproxy/haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)
log_path = config.get('main', 'log_path')
fullpath = config.get('main', 'fullpath')
server_bind_ip = config.get('main', 'server_bind_ip')
server_port = config.getint('main', 'server_port')

from http.server import HTTPServer, CGIHTTPRequestHandler

sys.stderr = open(log_path + '/haproxy-monitor.log', 'w')
webdir = fullpath
os.chdir(webdir)
server_address = (server_bind_ip, server_port)
httpd = HTTPServer(server_address, CGIHTTPRequestHandler)
httpd.serve_forever()