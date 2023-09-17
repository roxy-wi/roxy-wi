from flask import Blueprint

bp = Blueprint('config', __name__)

from app.routes.config import routes
