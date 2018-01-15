#!/usr/bin/env python3
import os, sys 

from http.server import HTTPServer, CGIHTTPRequestHandler

sys.stderr = open('/opt/haproxy/log/haproxy-monitor.log', 'w')
webdir = "/opt/haproxy"
os.chdir(webdir)
server_address = ("", 8000)
httpd = HTTPServer(server_address, CGIHTTPRequestHandler)
httpd.serve_forever()
