from flask import current_app, jsonify

from app.modules.db.readiness import database_schema_ready
from app.routes.health import bp


@bp.get('/health/live')
def live():
    return jsonify({'status': 'ok'}), 200


@bp.get('/health/ready')
def ready():
    is_ready, detail = database_schema_ready()
    if not is_ready:
        current_app.logger.warning('Database readiness check failed: %s', detail)
        return jsonify({'status': 'unavailable', 'database': detail}), 503
    return jsonify({'status': 'ok', 'database': 'ok'}), 200
