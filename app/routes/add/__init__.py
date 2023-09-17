from flask import Blueprint

bp = Blueprint('add', __name__)

from app.routes.add import routes
