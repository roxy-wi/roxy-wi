from flask import Blueprint

bp = Blueprint('overview', __name__)

from app.routes.overview import routes
