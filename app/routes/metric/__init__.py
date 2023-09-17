from flask import Blueprint

bp = Blueprint('metric', __name__)

from app.routes.metric import routes
