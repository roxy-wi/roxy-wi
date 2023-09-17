from flask import Blueprint

bp = Blueprint('waf', __name__)

from app.routes.waf import routes
