from flask import Blueprint

bp = Blueprint('admin', __name__)

from app.routes.admin import routes
from app.routes.admin import oidc_routes
from app.routes.admin import connection_profiles
