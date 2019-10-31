import os, sys
sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app/'))
sys.path.append(os.path.dirname(__file__))
import api
import bottle
bottle.debug(True)

application = bottle.default_app()
application.catchall = False