#!/usr/bin/env python3
import subprocess
from subprocess import check_output, CalledProcessError
import time
import argparse
import os, sys
sys.path.append(os.path.join(sys.path[0], os.path.dirname(os.getcwd())))
sys.path.append(os.path.join(sys.path[0], os.getcwd()))
import funct
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
	currentstat = []
	oldstat = []
	readstats = ""
	killer = GracefulKiller()
	old_stat_service = ""
	
	while True:
		try:			
			readstats = subprocess.check_output(["echo show stat | nc "+serv+" "+port], shell=True)
		except CalledProcessError as e:
			if firstrun == False:	
				cur_stat_service = "error"
				if old_stat_service != cur_stat_service:
					alert = "Can't connect to HAProxy service at " + serv
					funct.telegram_send_mess(str(alert), ip=serv)
					funct.logging("localhost", " "+alert, alerting=1)

			firstrun = False				
			old_stat_service = cur_stat_service
			continue
		except OSError as e:
			print(e)
			sys.exit()
		else:
			cur_stat_service = "Ok"
			if firstrun == False:	
				if old_stat_service != cur_stat_service:
					alert = "Now UP HAProxy service at " + serv
					funct.telegram_send_mess(str(alert), ip=serv)
					funct.logging("localhost", " "+alert, alerting=1)
					firstrun = True
					time.sleep(5)	
			old_stat_service = cur_stat_service
			
		vips = readstats.splitlines()

		for i in range(0,len(vips)):
			if "UP" in str(vips[i]):		
				currentstat.append("UP")
			elif "DOWN" in str(vips[i]):
				currentstat.append("DOWN")
			elif "MAINT" in str(vips[i]):
				currentstat.append("MAINT")
			else:
				currentstat.append("none")

			if firstrun == False:
				if (currentstat[i] != oldstat[i] and currentstat[i]!="none") and ("FRONTEND" not in str(vips[i]) and "BACKEND" not in str(vips[i])):
					servername = str(vips[i])
					servername = servername.split(",")
					realserver = servername[0]
					server = servername[1]
					alert = "Backend: "+realserver[2:]+", server: "+server+"  has changed status and is now "+ currentstat[i] + " at " + serv 
					funct.telegram_send_mess(str(alert), ip=serv)
					funct.logging("localhost", " "+alert, alerting=1)
		firstrun = False
		oldstat = []
		oldstat = currentstat
		currentstat = []
		time.sleep(60)	
				
		if killer.kill_now:
			break
	
	funct.logging("localhost", " Worker shutdown for: "+serv, alerting=1)

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Check HAProxy servers state.', prog='check_haproxy.py', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	
	parser.add_argument('IP', help='Start check HAProxy server state at this ip', nargs='?', type=str)
	parser.add_argument('--port', help='Start check HAProxy server state at this port', nargs='?', default=1999, type=int)
					
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