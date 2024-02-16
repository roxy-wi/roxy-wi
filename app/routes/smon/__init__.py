from flask import Blueprint

bp = Blueprint('smon', __name__)

from app.routes.smon import routes
from app.routes.smon import agent_routes
