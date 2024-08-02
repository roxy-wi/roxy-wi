from flask import Blueprint

bp = Blueprint('api', __name__)

from app.api.routes import routes
