from flask import Blueprint


bp = Blueprint('health', __name__)

from app.routes.health import routes  # noqa: E402,F401
