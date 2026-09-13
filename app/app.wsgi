import os
import sys
sys.path.insert(0,"/var/www/haproxy-wi/")
os.environ['ROXYWI_PROCESS_ROLE'] = 'web'

from app import app as application
