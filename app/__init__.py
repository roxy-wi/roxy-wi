from flask import Flask
from flask_caching import Cache
from flask_login import LoginManager
from flask_apscheduler import APScheduler

app = Flask(__name__)
app.config.from_object('app.config.Configuration')
app.jinja_env.add_extension('jinja2.ext.do')
app.jinja_env.add_extension('jinja2.ext.loopcontrols')

cache = Cache()
cache.init_app(app)

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

login_manager = LoginManager(app)
login_manager.login_view = 'login_page'

from app.routes.main import bp as main_bp
from app.routes.overview import bp as overview_bp
from app.routes.add import bp as add_bp
from app.routes.service import bp as service_bp
from app.routes.config import bp as config_bp
from app.routes.logs import bp as logs_bp
from app.routes.metric import bp as metric_bp
from app.routes.waf import bp as waf_bp
from app.routes.runtime import bp as runtime_bp
from app.routes.smon import bp as smon_bp
from app.routes.channel import bp as channel_bp
from app.routes.checker import bp as checker_bp
from app.routes.portscanner import bp as portscanner_bp
from app.routes.install import bp as install_bp
from app.routes.user import bp as user_bp
from app.routes.server import bp as server_bp
from app.routes.admin import bp as admin_bp
from app.routes.ha import bp as ha_bp
from app.routes.udp import bp as udp_bp

app.register_blueprint(main_bp)
app.register_blueprint(overview_bp)
app.register_blueprint(add_bp, url_prefix='/add')
app.register_blueprint(service_bp, url_prefix='/service')
app.register_blueprint(config_bp, url_prefix='/config')
app.register_blueprint(logs_bp, url_prefix='/logs')
app.register_blueprint(metric_bp, url_prefix='/metrics')
app.register_blueprint(waf_bp, url_prefix='/waf')
app.register_blueprint(runtime_bp, url_prefix='/runtimeapi')
app.register_blueprint(smon_bp, url_prefix='/smon')
app.register_blueprint(checker_bp, url_prefix='/checker')
app.register_blueprint(channel_bp, url_prefix='/channel')
app.register_blueprint(portscanner_bp, url_prefix='/portscanner')
app.register_blueprint(install_bp, url_prefix='/install')
app.register_blueprint(user_bp, url_prefix='/user')
app.register_blueprint(server_bp, url_prefix='/server')
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(ha_bp, url_prefix='/ha')
app.register_blueprint(udp_bp)

from app import login
from app import jobs
