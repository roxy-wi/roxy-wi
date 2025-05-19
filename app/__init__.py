from flask import Flask
from flask_caching import Cache
from flask_jwt_extended import JWTManager
from flask_apscheduler import APScheduler

from app.modules.common.common import set_correct_owner
from app.modules.roxywi import logger

app = Flask(__name__)
app.config.from_object('app.config.Configuration')
app.jinja_env.add_extension('jinja2.ext.do')
app.jinja_env.add_extension('jinja2.ext.loopcontrols')

# Initialize logger
logger.setup_logger(
    log_path=app.config.get('LOG_PATH', '/var/log/roxy-wi'),
    log_file=app.config.get('LOG_FILE', 'roxy-wi.log'),
    log_level=app.config.get('LOG_LEVEL', logger.INFO),
    console_logging=app.config.get('LOG_CONSOLE', False)
)
logger.info("Roxy-WI application starting up")

cache = Cache()
cache.init_app(app)

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

jwt = JWTManager(app)

from app.modules.db.db_model import create_tables
from app.create_db import default_values
from app.modules.db.migration_manager import migrate

create_tables()
default_values()
migrate()

set_correct_owner('/var/lib/roxy-wi')

from app.api.routes import bp as api_bp

app.register_blueprint(api_bp, url_prefix='/api')

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

# Register error handlers
from app.modules.roxywi.error_handler import register_error_handlers
register_error_handlers(app)
