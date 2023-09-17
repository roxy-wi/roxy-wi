from flask import Blueprint

bp = Blueprint('user', __name__)

from app.routes.user import routes
