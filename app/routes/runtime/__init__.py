from flask import Blueprint

bp = Blueprint('runtime', __name__)

from app.routes.runtime import routes
