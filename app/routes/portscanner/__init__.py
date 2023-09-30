from flask import Blueprint

bp = Blueprint('portscanner', __name__)

from app.routes.portscanner import routes
