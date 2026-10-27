from flask import Blueprint

bp = Blueprint('pacemaker', __name__)

from app.routes.pacemaker import routes
