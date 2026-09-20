import os

from flask import Flask
from flask_caching import Cache
from flask_jwt_extended import JWTManager
from flask_apscheduler import APScheduler
from werkzeug.middleware.proxy_fix import ProxyFix

from app.modules.common.common import set_correct_owner
from app.modules.roxywi import logger
from app.modules.common.lock_utils import acquire_file_lock

app = Flask(__name__)
app.config.from_object('app.config.Configuration')
if app.config['PROXY_FIX_ENABLED']:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=app.config['PROXY_FIX_X_FOR'],
        x_proto=app.config['PROXY_FIX_X_PROTO'],
        x_host=app.config['PROXY_FIX_X_HOST'],
        x_port=app.config['PROXY_FIX_X_PORT'],
        x_prefix=app.config['PROXY_FIX_X_PREFIX'],
    )
app.jinja_env.add_extension('jinja2.ext.do')
app.jinja_env.add_extension('jinja2.ext.loopcontrols')

# Initialize logger
logger.setup_logger(
    log_path=app.config.get('LOG_PATH', '/var/log/roxy-wi'),
    log_file=app.config.get('LOG_FILE', 'roxy-wi.log'),
    log_level=app.config.get('LOG_LEVEL', logger.INFO),
    console_logging=app.config.get('LOG_CONSOLE', False),
    file_logging=app.config.get('LOG_FILE_ENABLED', True),
)
logger.info("Roxy-WI application starting up")

cache = Cache()
cache.init_app(app)

scheduler = APScheduler()
scheduler.init_app(app)

jwt = JWTManager(app)

from app.modules.db.db_model import BaseModel, create_tables, close_database_connection
from app.create_db import default_values
from app.modules.db.migration_manager import mark_all_migrations_applied, migrate
from app.modules.db import token as token_sql


@app.teardown_appcontext
def close_request_database_connection(_exception=None):
    close_database_connection()


@jwt.token_in_blocklist_loader
def is_token_revoked(_jwt_header, jwt_payload):
    return token_sql.is_token_revoked(jwt_payload['jti'])

def initialize_database() -> None:
    """Create bootstrap data and apply migrations from a single process."""
    database = BaseModel._meta.database
    with database.connection_context():
        existing_tables = set(database.get_tables())
    fresh_database = not existing_tables.intersection({'user', 'servers', 'settings'})
    if fresh_database:
        create_tables()
        default_values()
        # create_tables() builds the current schema. Replaying historical
        # ALTER migrations on that schema would corrupt a fresh installation.
        mark_all_migrations_applied()
    else:
        # Existing installations may not yet have columns referenced by new
        # model indexes. Apply migrations before Peewee synchronizes indexes.
        if not migrate():
            raise RuntimeError('Database migration failed')
        create_tables()
        default_values()


def _initialize_runtime() -> None:
    """Initialize web/worker behavior only after database-command dispatch."""
    if app.config['TESTING']:
        initialize_database()
    elif app.config['AUTO_MIGRATE'] and not acquire_file_lock():
        initialize_database()

    if not app.config['TESTING'] and app.config['DEPLOYMENT_MODE'] == 'package':
        set_correct_owner('/var/lib/roxy-wi')

    from app.routes.main import bp as main_bp
    from app.routes.overview import bp as overview_bp
    from app.routes.service import bp as service_bp
    from app.routes.config import bp as config_bp
    from app.routes.waf import bp as waf_bp
    from app.routes.runtime import bp as runtime_bp
    from app.routes.user import bp as user_bp
    from app.routes.smon import bp as smon_bp
    from app.api.routes import bp as api_bp
    from app.routes.oidc import bp as oidc_bp
    from app.routes.change import bp as change_bp
    from app.routes.health import bp as health_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(overview_bp)
    app.register_blueprint(service_bp, url_prefix='/service')
    app.register_blueprint(config_bp, url_prefix='/config')
    app.register_blueprint(waf_bp, url_prefix='/waf')
    app.register_blueprint(runtime_bp, url_prefix='/runtimeapi')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(smon_bp, url_prefix='/smon')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(oidc_bp, url_prefix='/oidc')
    app.register_blueprint(change_bp, url_prefix='/changes')
    app.register_blueprint(health_bp)

    if app.config['TESTING']:
        # Register security-sensitive legacy blueprints in unit tests as well.
        # Heavy Linux-only dependencies are imported lazily by their handlers.
        from app.routes.add import bp as add_bp
        from app.routes.install import bp as install_bp
        from app.routes.server import bp as server_bp
        from app.routes.admin import bp as admin_bp

        app.register_blueprint(add_bp, url_prefix='/add')
        app.register_blueprint(install_bp, url_prefix='/install')
        app.register_blueprint(server_bp, url_prefix='/server')
        app.register_blueprint(admin_bp, url_prefix='/admin')
    else:
        from app.routes.add import bp as add_bp
        from app.routes.logs import bp as logs_bp
        from app.routes.metric import bp as metric_bp
        from app.routes.channel import bp as channel_bp
        from app.routes.checker import bp as checker_bp
        from app.routes.portscanner import bp as portscanner_bp
        from app.routes.install import bp as install_bp
        from app.routes.server import bp as server_bp
        from app.routes.admin import bp as admin_bp
        from app.routes.ha import bp as ha_bp
        from app.routes.udp import bp as udp_bp

        app.register_blueprint(add_bp, url_prefix='/add')
        app.register_blueprint(logs_bp, url_prefix='/logs')
        app.register_blueprint(metric_bp, url_prefix='/metrics')
        app.register_blueprint(checker_bp, url_prefix='/checker')
        app.register_blueprint(channel_bp, url_prefix='/channel')
        app.register_blueprint(portscanner_bp, url_prefix='/portscanner')
        app.register_blueprint(install_bp, url_prefix='/install')
        app.register_blueprint(server_bp, url_prefix='/server')
        app.register_blueprint(admin_bp, url_prefix='/admin')
        app.register_blueprint(ha_bp, url_prefix='/ha')
        app.register_blueprint(udp_bp)

    from app import login
    if not app.config['TESTING']:
        from app import jobs
        if app.config['SCHEDULER_ENABLED']:
            # Register every task before starting APScheduler. Starting it earlier can
            # leave the dedicated runner alive without the jobs imported below.
            scheduler.start()

    # Register error handlers
    from app.modules.roxywi.error_handler import register_error_handlers
    register_error_handlers(app)

    if not app.config['TESTING']:
        from app.modules.process_heartbeat import start_configured_process_heartbeat
        start_configured_process_heartbeat()


# A maintenance process must be able to import DB helpers before any tables
# exist. It must not run implicit migrations, routes, jobs or heartbeats.
if os.environ.get('ROXYWI_PROCESS_ROLE') not in {'migrate', 'wait-for-database', 'migrate-backup-cron', 'migrate-le-cron'}:
    try:
        _initialize_runtime()
    finally:
        # Route imports read settings before request threads exist. Request
        # teardown cannot close this bootstrap thread's SQLite connection.
        close_database_connection()
