from flask import Blueprint

bp = Blueprint('udp', __name__)

from app.routes.udp import routes
