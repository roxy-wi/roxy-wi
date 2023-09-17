from flask import Blueprint

bp = Blueprint('checker', __name__)

from app.routes.checker import routes
