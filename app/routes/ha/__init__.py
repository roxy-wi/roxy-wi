from flask import Blueprint

bp = Blueprint('ha', __name__)

from app.routes.ha import routes
