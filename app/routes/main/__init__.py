from flask import Blueprint

bp = Blueprint('main', __name__)

from app.routes.main import routes
