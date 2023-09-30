from flask import Blueprint

bp = Blueprint('logs', __name__)

from app.routes.logs import routes
