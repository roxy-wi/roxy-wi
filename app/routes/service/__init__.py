from flask import Blueprint

bp = Blueprint('service', __name__)

from app.routes.service import routes
