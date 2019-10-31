#!/usr/bin/env python3
import subprocess
from subprocess import check_output, CalledProcessError
import time
import argparse
import os, sys
sys.path.append(os.path.join(sys.path[0], os.path.dirname(os.getcwd())))
sys.path.append(os.path.join(sys.path[0], os.getcwd()))
import sql
import signal

class GracefulKiller:
	kill_now = False
	def __init__(self):
		signal.signal(signal.SIGINT, self.exit_gracefully)
		signal.signal(signal.SIGTERM, self.exit_gracefully)
	
	def exit_gracefully(self,signum, frame):
		self.kill_now = True

def main(serv, port):
	port = str(port)
	firstrun = True
	readstats = ""
	killer = GracefulKiller()
	
	while True:
		try:			
			cmd = "echo 'show stat' |nc "+serv+" "+port+" | cut -d ',' -f 1-2,34 |grep waf |grep BACKEND |awk -F',' '{print $3}'"
			readstats = subprocess.check_output([cmd], shell=True)
		except CalledProcessError as e:
			print("Command error")
		except OSError as e:
			print(e)
			sys.exit()
		readstats = readstats.decode(encoding='UTF-8')	
		metric = readstats.splitlines()
		metrics = []
		
		if metric:
			for i in range(0,len(metric)):
				sql.insert_waf_mentrics(serv, metric[i])

		time.sleep(30)	
				
		if killer.kill_now:
			break

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Metrics HAProxy service.', prog='metrics_worker.py', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	
	parser.add_argument('IP', help='Start get metrics from HAProxy service at this ip', nargs='?', type=str)
	parser.add_argument('--port', help='Start get metrics from HAProxy service at this port', nargs='?', default=1999, type=int)
					
	args = parser.parse_args()
	if args.IP is None:
		parser.print_help()
		import sys
		sys.exit()
	else: 
		try:
			main(args.IP, args.port)
		except KeyboardInterrupt:
			pass