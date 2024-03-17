from flask import Blueprint

bp = Blueprint('channel', __name__)

from app.routes.channel import routes
